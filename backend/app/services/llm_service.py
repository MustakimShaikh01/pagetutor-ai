"""
PageTutor AI — Offline LLM Service (Ollama)
============================================
Uses Ollama for 100% offline, zero-cost inference.

Recommended models (auto-selected by availability):
  1. qwen2.5:3b      — Best: 3B, long context (32k), fast, great quality
  2. llama3.2:3b     — Excellent: 3B, Meta latest, 128k context
  3. phi3.5:mini     — Good: 3.8B, Microsoft, great reasoning
  4. gemma2:2b       — Fast: 2B, Google, good summarisation
  5. tinyllama:1.1b  — Fastest: 1B fallback (low RAM)

Setup (one-time):
  brew install ollama          # Mac
  ollama serve                 # Start server (keep running)
  ollama pull qwen2.5:3b       # Download model (~2 GB)
"""

import json
import logging
import re
import time
from typing import Optional

import requests
import httpx
import structlog

from app.core.config import settings

logger = structlog.get_logger(__name__)

OLLAMA_BASE = "http://localhost:11434"

# Priority order: best quality first → fastest fallback last
PREFERRED_MODELS = [
    "qwen2.5:3b",
    "qwen2.5:1.5b",
    "llama3.2:3b",
    "llama3.2:1b",
    "phi3.5:mini",
    "phi3:mini",
    "gemma2:2b",
    "gemma:2b",
    "tinyllama:1.1b",
    "tinyllama",
]

_cached_model: Optional[str] = None


def _available_models() -> list:
    """Return list of models currently downloaded in Ollama."""
    try:
        r = requests.get(f"{OLLAMA_BASE}/api/tags", timeout=3)
        if r.ok:
            return [m["name"] for m in r.json().get("models", [])]
    except Exception:
        pass
    return []


def get_model() -> Optional[str]:
    """Return the best available Ollama model, or None if offline."""
    global _cached_model
    if _cached_model:
        return _cached_model

    available = _available_models()
    if not available:
        logger.warning("ollama_offline", hint="Run: ollama serve && ollama pull qwen2.5:3b")
        return None  # Do NOT cache None — retry on next call

    for pref in PREFERRED_MODELS:
        base = pref.split(":")[0]
        for avail in available:
            if avail.startswith(base):
                _cached_model = avail  # Cache only when found
                logger.info("llm_model_selected", model=avail)
                return avail

    # Any model available
    _cached_model = available[0]
    return _cached_model


def is_ollama_available() -> bool:
    """Check if Ollama is running with at least one model."""
    try:
        r = requests.get(f"{OLLAMA_BASE}/api/tags", timeout=2)
        return r.ok and bool(r.json().get("models"))
    except Exception:
        return False


def generate(
    prompt: str,
    system: str = "",
    model: Optional[str] = None,
    max_tokens: int = 1024,
    temperature: float = 0.3,
    timeout: int = 120,
) -> str:
    """
    Single-shot text generation via Ollama REST API.
    Raises RuntimeError if Ollama is unavailable.
    """
    m = model or get_model()
    if not m:
        raise RuntimeError("Ollama not available. Run: ollama serve && ollama pull qwen2.5:3b")

    payload = {
        "model": m,
        "prompt": prompt,
        "system": system,
        "stream": False,
        "options": {
            "temperature": temperature,
            "num_predict": max_tokens,
            "num_ctx": 4096,
            "repeat_penalty": 1.1,
            "stop": ["<|im_end|>", "</s>", "[INST]"],
        },
    }
    t0 = time.time()
    try:
        r = requests.post(
            f"{OLLAMA_BASE}/api/generate",
            json=payload,
            timeout=timeout,
        )
        r.raise_for_status()
        text = r.json().get("response", "").strip()
        logger.info("llm_generated", model=m, chars=len(text), elapsed=f"{time.time()-t0:.1f}s")
        return text
    except requests.exceptions.Timeout:
        raise RuntimeError(f"Ollama timeout after {timeout}s — try a smaller model")
    except Exception as e:
        raise RuntimeError(f"Ollama error: {e}")


# ──────────────────────────────────────────────────────────────
#  Existing vLLM-compat function kept for async chat endpoint
# ──────────────────────────────────────────────────────────────

SYSTEM_TUTOR = (
    "You are PageTutor AI, an expert educational assistant. "
    "Be concise, accurate, and format output as requested. "
    "Never add preamble. Output only what is asked."
)


async def generate_rag_answer(
    question: str,
    context: str,
    history: list,
    max_history_turns: int = 5,
):
    """
    Generate a grounded answer using page context.
    Falls back to Ollama if vLLM is not available.
    Returns: (answer_text, tokens_used)
    """
    system_prompt = (
        "You are PageTutor AI, an expert educational assistant.\n"
        "Answer questions based ONLY on the provided document context.\n"
        "If the answer is not in the context, say 'This information is not found in the document.'\n"
        "Be concise, accurate, and educational. Format answers clearly."
    )

    # Try vLLM (OpenAI-compatible) first
    if settings.LLM_BASE_URL and "localhost:8001" not in settings.LLM_BASE_URL:
        try:
            messages = [{"role": "system", "content": system_prompt}]
            messages.extend(history[-(max_history_turns * 2):])
            messages.append({"role": "user", "content": f"Context:\n{context}\n\nQuestion: {question}"})
            payload = {
                "model": settings.LLM_MODEL_NAME,
                "messages": messages,
                "max_tokens": 600,
                "temperature": 0.1,
                "stream": False,
            }
            async with httpx.AsyncClient(timeout=settings.LLM_TIMEOUT) as client:
                r = await client.post(
                    f"{settings.LLM_BASE_URL}/chat/completions",
                    json=payload,
                    headers={"Content-Type": "application/json"},
                )
                r.raise_for_status()
                data = r.json()
            answer = data["choices"][0]["message"]["content"].strip()
            tokens = data["usage"]["total_tokens"]
            return answer, tokens
        except Exception as e:
            logger.warning("vllm_unavailable_fallback_ollama", error=str(e))

    # Fallback: Ollama
    prompt = f"Context:\n{context}\n\nQuestion: {question}\nAnswer:"
    try:
        answer = generate(prompt, system=system_prompt, max_tokens=600, temperature=0.15)
        return answer, len(answer.split())
    except Exception as e:
        return f"[LLM unavailable: {e}]", 0


# ──────────────────────────────────────────────────────────────
#  Page-level AI tasks (no vector DB — pure SQLite page index)
# ──────────────────────────────────────────────────────────────

def summarise_page(page_text: str, page_num: int) -> str:
    """1-2 sentence summary of one PDF page."""
    prompt = (
        f"Summarise page {page_num} in 1-2 sentences (max 60 words). "
        "Be specific about the main idea.\n\n"
        f"{page_text[:1400]}"
    )
    return generate(prompt, system=SYSTEM_TUTOR, max_tokens=100, temperature=0.2)


def summarise_document(page_summaries: list, title: str = "") -> str:
    """Combine page summaries into a final document summary (3-5 paragraphs)."""
    combined = "\n".join(
        f"Page {i+1}: {s}" for i, s in enumerate(page_summaries) if s.strip()
    )
    prompt = (
        (f"Document: {title}\n\n" if title else "")
        + "Below are per-page summaries. Write a comprehensive summary in 3-5 paragraphs "
          "covering main topics, key insights, and conclusions.\n\n"
        + combined[:2800]
    )
    return generate(prompt, system=SYSTEM_TUTOR, max_tokens=600, temperature=0.3)


def extract_key_points(full_summary: str, page_summaries: list) -> list:
    """Extract 6-8 specific key learning points from the document."""
    context = full_summary + "\n\n" + "\n".join(
        f"- {s}" for s in page_summaries[:20] if s.strip()
    )
    prompt = (
        "Extract exactly 6 key learning points from this document.\n"
        "Format: one point per line, starting with '•'\n"
        "Each must be a specific, actionable insight (1 sentence).\n\n"
        f"{context[:2500]}"
    )
    raw = generate(prompt, system=SYSTEM_TUTOR, max_tokens=400, temperature=0.2)
    points = []
    for line in raw.splitlines():
        line = re.sub(r"^[•\-\*\d\.\)]+\s*", "", line).strip()
        if line and len(line) > 10:
            points.append(line)
    return points[:8] if points else [raw[:500]]


def generate_flashcards(page_texts: list, n: int = 8) -> list:
    """
    Generate flashcards from the document.
    page_texts: list of (page_num, text) tuples
    """
    # Use content-richest pages
    sorted_pages = sorted(page_texts, key=lambda x: len(x[1]), reverse=True)[:10]
    combined = "\n\n".join(f"[Page {p}]\n{t[:500]}" for p, t in sorted_pages)
    prompt = (
        f"Create {n} study flashcards from this document.\n"
        "Output each as a JSON object on its own line:\n"
        '{"front": "question testing understanding", "back": "clear answer", "topic": "topic name"}\n'
        "Make questions conceptual, not just factual recall.\n\n"
        f"{combined[:2600]}"
    )
    raw = generate(prompt, system=SYSTEM_TUTOR, max_tokens=900, temperature=0.4)

    cards = []
    for i, line in enumerate(raw.splitlines()):
        line = line.strip().lstrip("•-* 0123456789.)")
        if line.startswith("{") and '"front"' in line:
            try:
                card = json.loads(line)
                card["card_id"] = len(cards) + 1
                cards.append(card)
            except json.JSONDecodeError:
                pass
    if not cards:
        try:
            arr = json.loads(raw)
            if isinstance(arr, list):
                cards = [{"card_id": i+1, **c} for i, c in enumerate(arr)]
        except Exception:
            pass
    return cards[:n]


def generate_quiz(page_texts: list, n: int = 5) -> list:
    """
    Generate MCQ quiz questions.
    page_texts: list of (page_num, text) tuples
    """
    sorted_pages = sorted(page_texts, key=lambda x: len(x[1]), reverse=True)[:8]
    combined = "\n\n".join(f"[Page {p}]\n{t[:550]}" for p, t in sorted_pages)
    prompt = (
        f"Create {n} multiple-choice questions from this document.\n"
        "Each must have exactly 4 options and one correct answer.\n"
        "Output each as a JSON object on its own line:\n"
        '{"question": "...", "options": ["A) ...", "B) ...", "C) ...", "D) ..."], '
        '"correct_answer": "A", "explanation": "brief explanation"}\n\n'
        f"{combined[:2600]}"
    )
    raw = generate(prompt, system=SYSTEM_TUTOR, max_tokens=1000, temperature=0.4)

    questions = []
    for i, line in enumerate(raw.splitlines()):
        line = line.strip().lstrip("•-* 0123456789.)")
        if line.startswith("{") and '"question"' in line:
            try:
                q = json.loads(line)
                q["question_id"] = len(questions) + 1
                q["question_type"] = "mcq"
                questions.append(q)
            except json.JSONDecodeError:
                pass
    if not questions:
        try:
            arr = json.loads(raw)
            if isinstance(arr, list):
                questions = [{"question_id": i+1, "question_type": "mcq", **q}
                             for i, q in enumerate(arr)]
        except Exception:
            pass
    return questions[:n]
