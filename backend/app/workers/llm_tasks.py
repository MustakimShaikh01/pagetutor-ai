# ============================================================
# PageTutor AI - LLM Worker Tasks (GPU-accelerated)
# Author: Mustakim Shaikh (https://github.com/MustakimShaikh01)
#
# These tasks run on GPU workers via vLLM or TGI.
# Features:
#   - Dynamic batching (multiple requests coalesced per GPU call)
#   - Quantized model (4-bit) to minimize GPU memory
#   - Token limit enforcement
#   - Timeout control
#   - Context-aware prompts using PageIndex
# ============================================================

import asyncio
import json
import time
from typing import List, Tuple, Dict, Optional

import httpx
import structlog

from app.core.config import settings

logger = structlog.get_logger(__name__)

# ----------------------------------------------------------
# vLLM / TGI Client
# ----------------------------------------------------------
# Connects to vLLM server via OpenAI-compatible API.
# Dynamic batching is handled server-side by vLLM.
# Multiple concurrent API calls are batched automatically.

LLM_HEADERS = {
    "Content-Type": "application/json",
    # Add API key header if vLLM is configured with one:
    # "Authorization": f"Bearer {settings.LLM_API_KEY}"
}


def call_llm(
    prompt: str,
    system_prompt: str = "",
    max_tokens: int = None,
    temperature: float = None,
) -> Tuple[str, int]:
    """
    Call the LLM via vLLM OpenAI-compatible endpoint.

    Dynamic batching: vLLM automatically batches concurrent requests
    using continuous batching — up to {settings.LLM_BATCH_SIZE} requests
    share the same GPU forward pass.

    Returns (generated_text, tokens_used)
    """
    max_tokens = max_tokens or settings.LLM_MAX_TOKENS
    temperature = temperature or settings.LLM_TEMPERATURE

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    payload = {
        "model": settings.LLM_MODEL_NAME,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": False,
        # vLLM-specific options for efficiency
        "extra_body": {
            "guided_decoding_backend": "outlines",
        },
    }

    start_time = time.perf_counter()
    try:
        with httpx.Client(timeout=settings.LLM_TIMEOUT) as client:
            response = client.post(
                f"{settings.LLM_BASE_URL}/chat/completions",
                json=payload,
                headers=LLM_HEADERS,
            )
            response.raise_for_status()
            data = response.json()

        text = data["choices"][0]["message"]["content"].strip()
        tokens = data["usage"]["total_tokens"]
        elapsed = time.perf_counter() - start_time

        logger.info(
            "llm_inference_complete",
            tokens=tokens,
            elapsed_ms=round(elapsed * 1000),
            model=settings.LLM_MODEL_NAME,
        )
        return text, tokens

    except httpx.TimeoutException:
        logger.error("llm_timeout", timeout=settings.LLM_TIMEOUT)
        raise Exception("LLM request timed out. The model may be overloaded.")
    except Exception as e:
        logger.error("llm_error", error=str(e))
        raise


def get_document_pages_text(document_id: str) -> List[Dict]:
    """
    Retrieve page summaries and metadata from the database.
    This is more efficient than storing/loading full text repeatedly.
    """
    import asyncio
    from app.db.session import AsyncSessionLocal
    from app.models.models import PageIndex
    from sqlalchemy import select

    async def _fetch():
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(PageIndex)
                .where(PageIndex.document_id == document_id)
                .order_by(PageIndex.page_number)
            )
            pages = result.scalars().all()
            return [
                {
                    "page_number": p.page_number,
                    "topic": p.topic or "",
                    "summary": p.summary or "",
                    "importance_score": p.importance_score,
                    "token_count": p.token_count,
                }
                for p in pages
            ]

    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(_fetch())
    finally:
        loop.close()


def build_summary_context(pages: List[Dict], max_tokens: int = 6000) -> str:
    """
    Build a context string from page data within token budget.

    High-importance pages are included first to maximize
    information density within the token limit.
    """
    # Sort by importance score (most important first)
    sorted_pages = sorted(pages, key=lambda x: x["importance_score"], reverse=True)

    context_parts = []
    estimated_tokens = 0

    for page in sorted_pages:
        page_text = f"Page {page['page_number']} [{page['topic']}]: {page['summary']}"
        # Rough token estimate: 1 token ≈ 4 characters
        page_tokens = len(page_text) // 4

        if estimated_tokens + page_tokens > max_tokens:
            break

        context_parts.append(page_text)
        estimated_tokens += page_tokens

    # Re-sort by page number for coherent output
    return "\n\n".join(context_parts)


# ===========================================================
# SUMMARIZE DOCUMENT
# ===========================================================
def summarize_document(
    job_id: str,
    document_id: str,
) -> Tuple[str, List[str], int]:
    """
    Generate a structured summary and key learning points.

    Returns: (summary_text, learning_points_list, tokens_used)
    """
    logger.info("summarize_started", job_id=job_id, document_id=document_id)

    pages = get_document_pages_text(document_id)
    if not pages:
        return "No content available for summarization.", [], 0

    context = build_summary_context(pages)

    summary_prompt = f"""You are an expert educator. Analyze the following document content and provide:

1. A comprehensive summary (3-5 paragraphs) covering all major topics
2. A list of exactly 10 key learning points as bullet points

Document Content:
{context}

Format your response exactly as:
SUMMARY:
[Your summary here]

LEARNING POINTS:
• [Point 1]
• [Point 2]
...
• [Point 10]"""

    text, tokens = call_llm(
        prompt=summary_prompt,
        system_prompt="You are an expert academic content summarizer. Be precise, clear, and educational.",
        max_tokens=1500,
        temperature=0.2,
    )

    # Parse response
    summary = ""
    learning_points = []

    if "SUMMARY:" in text and "LEARNING POINTS:" in text:
        parts = text.split("LEARNING POINTS:")
        summary = parts[0].replace("SUMMARY:", "").strip()
        points_text = parts[1].strip()
        learning_points = [
            line.strip().lstrip("•-").strip()
            for line in points_text.split("\n")
            if line.strip() and (line.strip().startswith("•") or line.strip().startswith("-"))
        ]
    else:
        summary = text

    logger.info("summarize_completed", job_id=job_id, tokens=tokens)
    return summary, learning_points, tokens


# ===========================================================
# TOPIC SEGMENTATION
# ===========================================================
def segment_topics(job_id: str, document_id: str) -> List[Dict]:
    """
    Identify and segment document into logical topic blocks.

    Returns list of segment dicts:
    [{title, description, start_page, end_page, key_points}]
    """
    logger.info("segmentation_started", job_id=job_id)

    pages = get_document_pages_text(document_id)
    if not pages:
        return []

    # Build condensed page overview
    page_overview = "\n".join([
        f"Page {p['page_number']}: {p['topic'] or p['summary'][:100]}"
        for p in pages
    ])

    segment_prompt = f"""Analyze this document's page-by-page topics and group them into logical sections.

Pages:
{page_overview}

Return a JSON array of segments. Each element must have:
- "title": section title
- "description": 1-2 sentence description
- "start_page": first page number
- "end_page": last page number
- "key_points": list of 3 key points

Return ONLY valid JSON, no other text."""

    text, tokens = call_llm(
        prompt=segment_prompt,
        system_prompt="You are a document structure analyst. Return only valid JSON.",
        max_tokens=1000,
        temperature=0.1,
    )

    try:
        # Extract JSON from response
        json_start = text.find("[")
        json_end = text.rfind("]") + 1
        if json_start >= 0:
            segments = json.loads(text[json_start:json_end])
        else:
            segments = json.loads(text)
    except json.JSONDecodeError:
        logger.warning("segment_parse_failed", job_id=job_id)
        # Fallback: one segment for entire document
        segments = [{
            "title": "Full Document",
            "description": "Complete document content",
            "start_page": 1,
            "end_page": len(pages),
            "key_points": ["See summary for details"],
        }]

    logger.info("segmentation_completed", job_id=job_id, segments=len(segments))
    return segments


# ===========================================================
# FLASHCARD GENERATION
# ===========================================================
def generate_flashcards(
    job_id: str,
    document_id: str,
    count: int = 15,
) -> List[Dict]:
    """
    Generate spaced-repetition flashcards from document content.

    Returns list of {card_id, front, back, page_reference, topic}
    """
    logger.info("flashcard_generation_started", job_id=job_id)

    pages = get_document_pages_text(document_id)
    context = build_summary_context(pages, max_tokens=4000)

    flashcard_prompt = f"""Create {count} educational flashcards from this document content.

Document Content:
{context}

Return a JSON array. Each element must have:
- "card_id": integer starting from 1
- "front": question or term (max 100 chars)
- "back": answer or definition (max 200 chars)
- "topic": topic category
- "page_reference": most relevant page number or null

Return ONLY valid JSON array, no other text."""

    text, tokens = call_llm(
        prompt=flashcard_prompt,
        system_prompt="You are an expert flashcard creator for spaced repetition learning.",
        max_tokens=2000,
        temperature=0.3,
    )

    try:
        json_start = text.find("[")
        json_end = text.rfind("]") + 1
        cards = json.loads(text[json_start:json_end] if json_start >= 0 else text)
    except json.JSONDecodeError:
        logger.warning("flashcard_parse_failed", job_id=job_id)
        cards = []

    logger.info("flashcards_generated", job_id=job_id, count=len(cards))
    return cards


# ===========================================================
# QUIZ GENERATION
# ===========================================================
def generate_quiz(
    job_id: str,
    document_id: str,
    count: int = 10,
) -> List[Dict]:
    """
    Generate a multiple-choice quiz from document content.

    Returns list of question dicts with options, correct answer, and explanation.
    """
    logger.info("quiz_generation_started", job_id=job_id)

    pages = get_document_pages_text(document_id)
    context = build_summary_context(pages, max_tokens=4000)

    quiz_prompt = f"""Create {count} multiple-choice quiz questions from this document.

Document Content:
{context}

Return a JSON array. Each element must have:
- "question_id": integer starting from 1
- "question": the question text
- "question_type": "mcq"
- "options": array of exactly 4 options ["A) ...", "B) ...", "C) ...", "D) ..."]
- "correct_answer": the correct option (e.g., "A")
- "explanation": brief explanation of why the answer is correct
- "page_reference": most relevant page number or null

Return ONLY valid JSON array."""

    text, tokens = call_llm(
        prompt=quiz_prompt,
        system_prompt="You are an expert quiz question creator for educational assessment.",
        max_tokens=2000,
        temperature=0.3,
    )

    try:
        json_start = text.find("[")
        json_end = text.rfind("]") + 1
        questions = json.loads(text[json_start:json_end] if json_start >= 0 else text)
    except json.JSONDecodeError:
        logger.warning("quiz_parse_failed", job_id=job_id)
        questions = []

    logger.info("quiz_generated", job_id=job_id, count=len(questions))
    return questions
