# ============================================================
# PageTutor AI - Chat with PDF API Routes
# Author: Mustakim Shaikh (https://github.com/MustakimShaikh01)
#
# Implements RAG (Retrieval Augmented Generation) based chat.
#
# Endpoints:
#   POST /chat/message       — Send message, get AI response
#   GET  /chat/sessions      — List active chat sessions
#   GET  /chat/sessions/{id} — Get chat history
#   DELETE /chat/sessions/{id} — Clear session
# ============================================================

import time
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.core.security import get_current_user
from app.db.session import get_db
from app.models.models import User, Document
from app.schemas.schemas import (
    ChatMessageRequest, ChatMessageResponse, SuccessResponse
)
from app.services.vector_service import search_similar_chunks
from app.services.llm_service import generate_rag_answer
from app.core.rate_limiter import get_redis

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/chat", tags=["Chat with PDF"])

# Chat session history TTL: 24 hours in Redis
SESSION_TTL = 86400
MAX_HISTORY_MESSAGES = 20  # Keep last 20 messages per session


# ----------------------------------------------------------
# Session Helpers (stored in Redis for speed)
# ----------------------------------------------------------

async def get_session_history(session_id: str) -> List[dict]:
    """Load chat history from Redis."""
    redis = await get_redis()
    import json
    history_raw = await redis.get(f"chat_session:{session_id}")
    if not history_raw:
        return []
    return json.loads(history_raw)


async def save_session_history(session_id: str, history: List[dict]) -> None:
    """Save chat history to Redis with TTL."""
    redis = await get_redis()
    import json
    # Keep only last N messages to prevent unbounded growth
    trimmed = history[-MAX_HISTORY_MESSAGES:]
    await redis.setex(
        f"chat_session:{session_id}",
        SESSION_TTL,
        json.dumps(trimmed),
    )


async def create_session(document_id: str, user_id: str) -> str:
    """Create a new chat session, return session ID."""
    redis = await get_redis()
    import json
    session_id = str(uuid.uuid4())
    metadata = {
        "document_id": document_id,
        "user_id": user_id,
        "created_at": time.time(),
    }
    await redis.setex(
        f"chat_meta:{session_id}",
        SESSION_TTL,
        json.dumps(metadata),
    )
    return session_id


# ===========================================================
# SEND CHAT MESSAGE
# ===========================================================
@router.post(
    "/message",
    response_model=ChatMessageResponse,
    summary="Chat with your PDF document",
    response_description="AI-generated answer with source page references",
    responses={
        200: {"description": "AI response with sources"},
        404: {"description": "Document not found"},
        503: {"description": "LLM service unavailable"},
    },
)
async def chat_message(
    payload: ChatMessageRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    **Chat with your uploaded PDF using AI (RAG mode).**

    How it works:
    1. User's question is embedded into a vector
    2. Top-K most relevant page chunks are retrieved from Qdrant
    3. Retrieved context + conversation history → LLM
    4. LLM generates a grounded answer with source references

    **Conversation memory:** Last 20 messages kept per session (24h TTL).

    The PageIndex-based retrieval ensures answers are grounded
    in the actual document content, not hallucinated.
    """
    start_time = time.perf_counter()

    # Verify document belongs to user
    from sqlalchemy import select
    doc_result = await db.execute(
        select(Document).where(
            Document.id == payload.document_id,
            Document.owner_id == current_user.id,
        )
    )
    document = doc_result.scalar_one_or_none()

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found or access denied.",
        )

    if not document.is_indexed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Document not yet indexed. Please wait for indexing to complete.",
        )

    # Get or create session
    session_id = payload.session_id
    if not session_id:
        session_id = await create_session(payload.document_id, current_user.id)
        history = []
    else:
        history = await get_session_history(session_id)

    # --- Step 1: Semantic search for relevant page chunks ---
    try:
        similar_chunks = await search_similar_chunks(
            query=payload.message,
            document_id=payload.document_id,
            top_k=5,  # Retrieve 5 most relevant chunks
        )
    except Exception as e:
        logger.error("vector_search_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Search service temporarily unavailable.",
        )

    # Build context from retrieved chunks
    context_parts = []
    sources = []
    for chunk in similar_chunks:
        context_parts.append(
            f"[Page {chunk['page_number']}]: {chunk['summary']}"
        )
        sources.append({
            "page_number": chunk["page_number"],
            "topic": chunk.get("topic", ""),
            "relevance_score": round(chunk.get("score", 0), 3),
        })

    context = "\n\n".join(context_parts)

    # --- Step 2: Generate RAG answer using LLM ---
    try:
        answer, tokens_used = await generate_rag_answer(
            question=payload.message,
            context=context,
            history=history,
        )
    except Exception as e:
        logger.error("llm_inference_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI service temporarily unavailable. Please try again.",
        )

    # --- Step 3: Update conversation history ---
    history.append({"role": "user", "content": payload.message})
    history.append({"role": "assistant", "content": answer})
    await save_session_history(session_id, history)

    response_time_ms = int((time.perf_counter() - start_time) * 1000)

    logger.info(
        "chat_response_generated",
        user_id=current_user.id,
        document_id=payload.document_id,
        session_id=session_id,
        tokens=tokens_used,
        response_ms=response_time_ms,
    )

    return ChatMessageResponse(
        session_id=session_id,
        message=answer,
        sources=sources,
        tokens_used=tokens_used,
        response_time_ms=response_time_ms,
    )


# ===========================================================
# LIST CHAT SESSIONS
# ===========================================================
@router.get(
    "/sessions",
    summary="List active chat sessions",
    response_model=List[dict],
)
async def list_sessions(
    current_user: User = Depends(get_current_user),
):
    """**List all active chat sessions for the current user.**"""
    redis = await get_redis()

    # Find all session metadata keys for this user
    pattern = "chat_meta:*"
    import json
    sessions = []

    cursor = 0
    while True:
        cursor, keys = await redis.scan(cursor, match=pattern, count=100)
        for key in keys:
            data = await redis.get(key)
            if data:
                meta = json.loads(data)
                if meta.get("user_id") == current_user.id:
                    session_id = key.replace("chat_meta:", "")
                    sessions.append({
                        "session_id": session_id,
                        "document_id": meta.get("document_id"),
                        "created_at": meta.get("created_at"),
                    })
        if cursor == 0:
            break

    return sessions


# ===========================================================
# GET SESSION HISTORY
# ===========================================================
@router.get(
    "/sessions/{session_id}",
    summary="Get chat session history",
    response_model=List[dict],
)
async def get_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
):
    """**Retrieve the full message history of a chat session.**"""
    redis = await get_redis()
    import json

    # Verify ownership
    meta_raw = await redis.get(f"chat_meta:{session_id}")
    if not meta_raw:
        raise HTTPException(status_code=404, detail="Session not found or expired.")

    meta = json.loads(meta_raw)
    if meta.get("user_id") != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied.")

    history = await get_session_history(session_id)
    return history


# ===========================================================
# DELETE SESSION
# ===========================================================
@router.delete(
    "/sessions/{session_id}",
    response_model=SuccessResponse,
    summary="Delete a chat session",
)
async def delete_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
):
    """**Clear a chat session's history.**"""
    redis = await get_redis()
    import json

    meta_raw = await redis.get(f"chat_meta:{session_id}")
    if not meta_raw:
        raise HTTPException(status_code=404, detail="Session not found.")

    meta = json.loads(meta_raw)
    if meta.get("user_id") != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied.")

    await redis.delete(f"chat_session:{session_id}")
    await redis.delete(f"chat_meta:{session_id}")

    return SuccessResponse(message="Chat session cleared.")
