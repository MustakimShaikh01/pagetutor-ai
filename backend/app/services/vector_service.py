# ============================================================
# PageTutor AI - Vector Search Service
# Author: Mustakim Shaikh (https://github.com/MustakimShaikh01)
#
# Provides semantic search over PageIndex vectors.
# Used by: Chat-with-PDF (RAG retrieval)
# ============================================================

import asyncio
from typing import List, Dict, Optional
import structlog

from app.core.config import settings

logger = structlog.get_logger(__name__)


async def search_similar_chunks(
    query: str,
    document_id: str,
    top_k: int = 5,
    score_threshold: float = 0.3,
) -> List[Dict]:
    """
    Search for semantically similar page chunks in Qdrant.

    Args:
        query: User's question
        document_id: Restrict search to this document
        top_k: Number of results to return
        score_threshold: Minimum cosine similarity score (0-1)

    Returns:
        List of matching chunks with metadata:
        [{page_number, topic, summary, score}]
    """
    # Embed the query using the same model as indexing
    # Run in executor to avoid blocking async event loop
    loop = asyncio.get_event_loop()

    def _embed_query():
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer(settings.EMBED_MODEL)
        return model.encode([query], normalize_embeddings=True)[0].tolist()

    query_vector = await loop.run_in_executor(None, _embed_query)

    # Search Qdrant with document filter
    def _search():
        from qdrant_client import QdrantClient
        from qdrant_client.models import Filter, FieldCondition, MatchValue

        client = QdrantClient(
            host=settings.QDRANT_HOST,
            port=settings.QDRANT_PORT,
            api_key=settings.QDRANT_API_KEY,
        )

        results = client.search(
            collection_name=settings.QDRANT_COLLECTION,
            query_vector=query_vector,
            query_filter=Filter(
                must=[
                    FieldCondition(
                        key="document_id",
                        match=MatchValue(value=document_id),
                    )
                ]
            ),
            limit=top_k,
            score_threshold=score_threshold,
            with_payload=True,
        )
        return results

    results = await loop.run_in_executor(None, _search)

    # Map Qdrant results to PageIndex data from PostgreSQL
    similar_chunks = []
    for hit in results:
        payload = hit.payload or {}

        # Enrich with full metadata from DB
        page_info = await _get_page_info(
            document_id=document_id,
            page_number=payload.get("page_number", 1),
        )

        similar_chunks.append({
            "page_number": payload.get("page_number"),
            "chunk_index": payload.get("chunk_index", 0),
            "topic": page_info.get("topic", ""),
            "summary": page_info.get("summary", payload.get("text_preview", "")),
            "score": hit.score,
        })

    logger.debug(
        "vector_search_completed",
        query=query[:50],
        document_id=document_id,
        results=len(similar_chunks),
    )

    return similar_chunks


async def _get_page_info(document_id: str, page_number: int) -> Dict:
    """Fetch PageIndex metadata from PostgreSQL."""
    from app.db.session import AsyncSessionLocal
    from app.models.models import PageIndex
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(PageIndex).where(
                PageIndex.document_id == document_id,
                PageIndex.page_number == page_number,
                PageIndex.chunk_index == 0,  # Get page-level entry
            )
        )
        page = result.scalar_one_or_none()

        if page:
            return {
                "topic": page.topic or "",
                "summary": page.summary or "",
                "importance_score": page.importance_score,
            }
        return {}
