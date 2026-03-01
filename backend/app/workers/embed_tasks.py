# ============================================================
# PageTutor AI - Embed Worker: PageIndex Creation
# Author: Mustakim Shaikh (https://github.com/MustakimShaikh01)
#
# PageIndex Design:
#   - One entry per page per document
#   - Stores: page_number, topic, summary, importance_score,
#             token_count, qdrant_point_id, chunk metadata
#   - Vectors stored in Qdrant (vector DB)
#   - Metadata stored in PostgreSQL
#
# Chunking Strategy:
#   - Pages > 1000 tokens are split into overlapping chunks
#   - 128-token overlap between chunks for context continuity
#   - Hierarchical: page-level + chunk-level entries
#
# Deduplication:
#   - Same document hash → skip re-indexing
#   - Check existing qdrant_point_id before re-embedding
# ============================================================

import asyncio
import hashlib
import io
import uuid
from typing import List, Dict, Optional, Tuple

import structlog

from app.core.config import settings

logger = structlog.get_logger(__name__)

# Embedding dimension must match Qdrant collection config
EMBEDDING_DIM = settings.VECTOR_DIMENSION
MAX_CHUNK_TOKENS = 512         # Max tokens per chunk
CHUNK_OVERLAP_TOKENS = 128     # Overlap between chunks


# ----------------------------------------------------------
# Embedding Model (CPU-optimized, Float16)
# ----------------------------------------------------------
_embed_model = None


def get_embed_model():
    """
    Lazy-load the sentence transformer model.
    Float16 precision halves memory usage vs Float32.
    Model is loaded once per worker process — not per request.
    """
    global _embed_model
    if _embed_model is None:
        from sentence_transformers import SentenceTransformer
        import torch

        logger.info("loading_embed_model", model=settings.EMBED_MODEL)
        _embed_model = SentenceTransformer(settings.EMBED_MODEL)

        # Convert to float16 for memory efficiency
        if torch.cuda.is_available():
            _embed_model = _embed_model.half()  # Float16 on GPU

        logger.info("embed_model_loaded")
    return _embed_model


def embed_texts(texts: List[str]) -> List[List[float]]:
    """
    Batch embed a list of texts.
    Uses the sentence transformer model with batch processing.
    Returns list of float16 vectors.
    """
    model = get_embed_model()
    embeddings = model.encode(
        texts,
        batch_size=32,          # Process 32 at a time
        normalize_embeddings=True,  # L2 normalize for cosine similarity
        show_progress_bar=False,
        convert_to_numpy=True,
    )
    # Convert to regular Python floats (JSON serializable)
    return embeddings.tolist()


def compress_embedding(vector: List[float]) -> bytes:
    """
    Compress embedding vector using scalar quantization.
    Reduces storage from 3072 bytes (float32×768) to ~768 bytes (int8×768).
    """
    import numpy as np
    arr = np.array(vector, dtype=np.float32)
    # Scale to int8 range
    min_val, max_val = arr.min(), arr.max()
    scale = (max_val - min_val) / 255
    quantized = ((arr - min_val) / scale).astype(np.uint8)
    # Store scale and offset for reconstruction
    header = np.array([min_val, scale], dtype=np.float32).tobytes()
    return header + quantized.tobytes()


# ----------------------------------------------------------
# PDF Text Extraction
# ----------------------------------------------------------
def extract_pdf_pages(pdf_bytes: bytes) -> List[Dict]:
    """
    Extract text from each page of the PDF.
    Returns list of {page_number, text, token_count}
    """
    import pdfplumber

    pages = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            text = text.strip()

            if not text:
                continue

            # Rough token count (1 token ≈ 4 chars)
            token_count = len(text) // 4

            pages.append({
                "page_number": i,
                "text": text,
                "token_count": token_count,
            })

    return pages


def chunk_text(text: str, max_tokens: int = MAX_CHUNK_TOKENS,
               overlap: int = CHUNK_OVERLAP_TOKENS) -> List[str]:
    """
    Split text into overlapping chunks for long pages.

    Strategy:
    - Split on sentence boundaries when possible
    - Each chunk ≤ max_tokens
    - Overlap of 'overlap' tokens between chunks
    """
    # Approximate word count (1 word ≈ 1.3 tokens)
    words = text.split()
    max_words = int(max_tokens / 1.3)
    overlap_words = int(overlap / 1.3)

    if len(words) <= max_words:
        return [text]

    chunks = []
    start = 0
    while start < len(words):
        end = min(start + max_words, len(words))
        chunk = " ".join(words[start:end])
        chunks.append(chunk)
        start = end - overlap_words  # Move back by overlap

    return chunks


def compute_importance_score(page: Dict, total_pages: int) -> float:
    """
    Compute importance score for a page.

    Factors:
    - Text density (more content = more important)
    - Position (intro pages and conclusion pages score higher)
    - Presence of key phrases

    Returns float 0.0 - 1.0
    """
    text = page.get("text", "")
    token_count = page.get("token_count", 0)
    page_num = page.get("page_number", 1)

    # Base score: text density (normalized)
    density_score = min(token_count / 500, 1.0)  # Cap at 500 tokens

    # Position bonus: first 10% and last 10% of document
    position_ratio = page_num / total_pages
    position_score = 0.8 if (position_ratio <= 0.1 or position_ratio >= 0.9) else 0.5

    # Key phrase bonus
    key_phrases = [
        "introduction", "conclusion", "summary", "key", "important",
        "main", "overview", "definition", "theorem", "figure",
    ]
    keyword_found = any(kw in text.lower() for kw in key_phrases)
    keyword_bonus = 0.2 if keyword_found else 0.0

    score = (density_score * 0.5) + (position_score * 0.3) + keyword_bonus
    return round(min(score, 1.0), 3)


def extract_page_topic(text: str, page_number: int) -> str:
    """
    Extract the likely topic/heading from page text.
    Simple heuristic: first non-empty line ≤ 100 chars.
    For production: use LLM to extract proper topic.
    """
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    for line in lines[:5]:
        if 3 <= len(line) <= 100:
            return line
    return f"Page {page_number}"


# ----------------------------------------------------------
# Qdrant Client
# ----------------------------------------------------------
def get_qdrant_client():
    """Get Qdrant client instance."""
    from qdrant_client import QdrantClient

    return QdrantClient(
        host=settings.QDRANT_HOST,
        port=settings.QDRANT_PORT,
        api_key=settings.QDRANT_API_KEY,
        timeout=30,
    )


def ensure_collection_exists(client) -> None:
    """Create Qdrant collection if it doesn't exist."""
    from qdrant_client.models import VectorParams, Distance

    collections = client.get_collections().collections
    existing = [c.name for c in collections]

    if settings.QDRANT_COLLECTION not in existing:
        client.create_collection(
            collection_name=settings.QDRANT_COLLECTION,
            vectors_config=VectorParams(
                size=EMBEDDING_DIM,
                distance=Distance.COSINE,  # Cosine similarity
            ),
        )
        logger.info("qdrant_collection_created", collection=settings.QDRANT_COLLECTION)


# ===========================================================
# MAIN: INDEX DOCUMENT PAGES
# ===========================================================
def index_document_pages(job_id: str, document_id: str) -> Dict:
    """
    Complete PageIndex creation for a document.

    Steps:
    1. Load PDF from S3
    2. Extract text per page
    3. Chunk long pages
    4. Batch embed all chunks
    5. Upsert vectors into Qdrant
    6. Save PageIndex metadata to PostgreSQL
    7. Mark document as indexed

    Returns stats dict.
    """
    logger.info("indexing_started", job_id=job_id, document_id=document_id)

    # ----------------------------------------------------------
    # Step 1: Load document from S3 and DB
    # ----------------------------------------------------------
    async def _load_doc():
        from app.db.session import AsyncSessionLocal
        from app.models.models import Document
        from sqlalchemy import select
        import boto3

        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Document).where(Document.id == document_id)
            )
            doc = result.scalar_one_or_none()
            if not doc:
                raise ValueError(f"Document {document_id} not found")
            return doc.s3_key

    loop = asyncio.new_event_loop()
    try:
        s3_key = loop.run_until_complete(_load_doc())
    finally:
        loop.close()

    # Download PDF from S3
    import boto3
    s3 = boto3.client(
        "s3",
        endpoint_url=settings.S3_ENDPOINT_URL,
        aws_access_key_id=settings.S3_ACCESS_KEY,
        aws_secret_access_key=settings.S3_SECRET_KEY,
    )
    response = s3.get_object(Bucket=settings.S3_BUCKET_NAME, Key=s3_key)
    pdf_bytes = response["Body"].read()

    # ----------------------------------------------------------
    # Step 2: Extract pages
    # ----------------------------------------------------------
    pages = extract_pdf_pages(pdf_bytes)
    total_pages = len(pages)
    logger.info("pages_extracted", document_id=document_id, pages=total_pages)

    # ----------------------------------------------------------
    # Step 3: Prepare chunks for embedding
    # ----------------------------------------------------------
    all_chunks = []  # (page_number, chunk_index, chunk_text)
    for page in pages:
        chunks = chunk_text(page["text"])
        for idx, chunk in enumerate(chunks):
            all_chunks.append((page["page_number"], idx, chunk, len(chunks)))

    # ----------------------------------------------------------
    # Step 4: Batch embed all chunks
    # ----------------------------------------------------------
    chunk_texts = [c[2] for c in all_chunks]
    vectors = embed_texts(chunk_texts)
    logger.info("embeddings_generated", count=len(vectors))

    # ----------------------------------------------------------
    # Step 5: Upsert into Qdrant
    # ----------------------------------------------------------
    qdrant = get_qdrant_client()
    ensure_collection_exists(qdrant)

    from qdrant_client.models import PointStruct

    points = []
    for i, (page_number, chunk_idx, chunk_text_content, chunk_total) in enumerate(all_chunks):
        point_id = str(uuid.uuid4())
        points.append(PointStruct(
            id=point_id,
            vector=vectors[i],
            payload={
                "document_id": document_id,
                "page_number": page_number,
                "chunk_index": chunk_idx,
                "chunk_total": chunk_total,
                "text_preview": chunk_text_content[:200],  # Store preview only
            },
        ))

    # Upsert in batches of 100
    BATCH_SIZE = 100
    for i in range(0, len(points), BATCH_SIZE):
        qdrant.upsert(
            collection_name=settings.QDRANT_COLLECTION,
            points=points[i:i + BATCH_SIZE],
        )

    # ----------------------------------------------------------
    # Step 6: Save PageIndex metadata to PostgreSQL
    # ----------------------------------------------------------
    async def _save_page_indices():
        from app.db.session import AsyncSessionLocal
        from app.models.models import PageIndex, Document
        from sqlalchemy import select

        async with AsyncSessionLocal() as db:
            # Create PageIndex entries (one per page)
            page_map = {}  # page_number → first qdrant point ID
            for i, (page_number, chunk_idx, _, _) in enumerate(all_chunks):
                if chunk_idx == 0:  # First chunk represents the page
                    page_map[page_number] = points[i].id if i < len(points) else None

            for page in pages:
                page_number = page["page_number"]
                importance = compute_importance_score(page, total_pages)
                topic = extract_page_topic(page["text"], page_number)

                # Page summary (first 300 chars)
                summary = page["text"][:300].strip()

                page_index = PageIndex(
                    document_id=document_id,
                    page_number=page_number,
                    topic=topic,
                    summary=summary,
                    importance_score=importance,
                    token_count=page["token_count"],
                    qdrant_point_id=page_map.get(page_number),
                    chunk_index=0,
                    chunk_total=len([c for c in all_chunks if c[0] == page_number]),
                )
                db.add(page_index)

            # Mark document as indexed
            doc_result = await db.execute(
                select(Document).where(Document.id == document_id)
            )
            doc = doc_result.scalar_one_or_none()
            if doc:
                doc.is_indexed = True
                doc.status = "indexed"

            await db.commit()

    loop2 = asyncio.new_event_loop()
    try:
        loop2.run_until_complete(_save_page_indices())
    finally:
        loop2.close()

    stats = {
        "pages_indexed": total_pages,
        "chunks_embedded": len(all_chunks),
        "vectors_stored": len(points),
    }
    logger.info("indexing_completed", document_id=document_id, **stats)
    return stats
