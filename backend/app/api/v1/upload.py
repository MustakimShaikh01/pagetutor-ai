# ============================================================
# PageTutor AI - Upload API Routes
# Author: Mustakim Shaikh (https://github.com/MustakimShaikh01)
#
# Endpoints:
#   POST /upload/pdf          — Upload PDF (with validation + dedup)
#   GET  /upload/documents    — List user's documents
#   GET  /upload/documents/{id} — Get document details
#   DELETE /upload/documents/{id} — Delete document
# ============================================================

import hashlib
import uuid
import io
import os
import aiofiles
from datetime import datetime, timezone, timedelta
from typing import Optional, List

from fastapi import (
    APIRouter, Depends, HTTPException, Request, UploadFile,
    File, Form, status, BackgroundTasks
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
import structlog
import pdfplumber

from app.core.config import settings
from app.core.security import get_current_user
from app.core.rate_limiter import check_daily_job_quota
from app.db.session import get_db
from app.models.models import User, Document, AuditLog
from app.schemas.schemas import (
    DocumentUploadResponse, DocumentListResponse, DocumentSummary,
    SuccessResponse, ErrorResponse,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/upload", tags=["Document Upload"])

LOCAL_UPLOAD_DIR = "uploads/pdfs"


# ----------------------------------------------------------
# Storage Helpers (S3 or local filesystem fallback)
# ----------------------------------------------------------
def get_s3_session():
    """Create an aioboto3 S3 session (only used if aioboto3 is installed)."""
    try:
        import aioboto3
        return aioboto3.Session()
    except ImportError:
        return None


async def upload_to_storage(file_bytes: bytes, s3_key: str, content_type: str) -> str:
    """
    Upload file to S3/MinIO if available, otherwise save locally.
    Returns the storage key on success.
    """
    if not settings.USE_LOCAL_STORAGE:
        session = get_s3_session()
        if session:
            async with session.client(
                "s3",
                endpoint_url=settings.S3_ENDPOINT_URL,
                aws_access_key_id=settings.S3_ACCESS_KEY,
                aws_secret_access_key=settings.S3_SECRET_KEY,
                region_name=settings.S3_REGION,
            ) as s3:
                await s3.put_object(
                    Bucket=settings.S3_BUCKET_NAME,
                    Key=s3_key,
                    Body=file_bytes,
                    ContentType=content_type,
                )
            return s3_key

    # Local filesystem fallback
    local_path = os.path.join(LOCAL_UPLOAD_DIR, s3_key.replace("/", "_"))
    os.makedirs(LOCAL_UPLOAD_DIR, exist_ok=True)
    async with aiofiles.open(local_path, "wb") as f:
        await f.write(file_bytes)
    logger.debug("file_saved_locally", path=local_path)
    return s3_key  # Return the logical S3 key, local path stored separately


# Keep old name as alias
upload_to_s3 = upload_to_storage


async def generate_presigned_url(s3_key: str, expires_in: int = 3600) -> str:
    """Generate URL. Returns local path URL in dev mode."""
    if settings.USE_LOCAL_STORAGE:
        return f"/uploads/{s3_key.replace('/', '_')}"
    return f"{settings.S3_CDN_BASE_URL}/{s3_key}"


async def delete_from_s3(s3_key: str) -> None:
    """Delete file from S3 or local storage."""
    if settings.USE_LOCAL_STORAGE:
        local_path = os.path.join(LOCAL_UPLOAD_DIR, s3_key.replace("/", "_"))
        try:
            os.remove(local_path)
        except FileNotFoundError:
            pass
        return

    session = get_s3_session()
    if session:
        async with session.client(
            "s3",
            endpoint_url=settings.S3_ENDPOINT_URL,
            aws_access_key_id=settings.S3_ACCESS_KEY,
            aws_secret_access_key=settings.S3_SECRET_KEY,
        ) as s3:
            await s3.delete_object(Bucket=settings.S3_BUCKET_NAME, Key=s3_key)


# ----------------------------------------------------------
# File Validation
# ----------------------------------------------------------
def validate_pdf(file_bytes: bytes, filename: str) -> None:
    """
    Validate uploaded file:
    1. Size limit
    2. MIME type detection
    3. PDF structure validation
    """
    # 1. Size check
    max_bytes = settings.MAX_FILE_SIZE_MB * 1024 * 1024
    if len(file_bytes) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large. Maximum allowed size is {settings.MAX_FILE_SIZE_MB}MB.",
        )

    # 2. Basic PDF header check (magic bytes)
    if not file_bytes.startswith(b"%PDF"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid file type. Only PDF files are accepted.",
        )


def count_pdf_pages(file_bytes: bytes) -> int:
    """Count pages in PDF using pdfplumber."""
    try:
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            return len(pdf.pages)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Could not parse PDF: {str(e)}",
        )


def compute_sha256(file_bytes: bytes) -> str:
    """Compute SHA-256 hash for deduplication."""
    return hashlib.sha256(file_bytes).hexdigest()

def compute_sha256(file_bytes: bytes) -> str:
    return hashlib.sha256(file_bytes).hexdigest()


# ===========================================================
# UPLOAD PDF
# ===========================================================
@router.post(
    "/pdf",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a PDF document for processing",
    response_description="Document metadata and upload confirmation",
    responses={
        400: {"description": "Invalid file type", "model": ErrorResponse},
        413: {"description": "File too large", "model": ErrorResponse},
        429: {"description": "Daily upload quota exceeded", "model": ErrorResponse},
    },
)
async def upload_pdf(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(
        ...,
        description="PDF file to upload. Max size: 50MB. Max pages: 500."
    ),
    language: str = Form(
        default="en",
        description="Document language (ISO 639-1 code)",
        example="en"
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    **Upload a PDF document to PageTutor AI.**

    - File is validated for type, size, and page count
    - SHA-256 hash is computed for deduplication
    - If identical PDF exists → reuses existing document record
    - Raw PDF is stored in S3 with **48-hour auto-deletion lifecycle**
    - Returns document ID for use in /jobs endpoint

    **Limits:**
    - Free tier: 50MB, 500 pages, 5 uploads/day
    - Paid tier: 50MB, 500 pages, 100 uploads/day
    """
    # Check daily quota (returns bool; doesn't raise)
    quota_ok, remaining = await check_daily_job_quota(current_user.id, current_user.tier)
    if not quota_ok:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Daily upload quota exceeded. Upgrade your plan for more uploads.",
        )

    # Read file bytes
    file_bytes = await file.read()

    # Validate file
    validate_pdf(file_bytes, file.filename)

    # Count pages
    page_count = count_pdf_pages(file_bytes)

    if page_count > settings.MAX_PAGE_COUNT:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"PDF has {page_count} pages. Maximum allowed is {settings.MAX_PAGE_COUNT}.",
        )

    # Compute hash for deduplication
    sha256_hash = compute_sha256(file_bytes)

    # Check for duplicate document by this user
    dup_result = await db.execute(
        select(Document).where(
            Document.sha256_hash == sha256_hash,
            Document.owner_id == current_user.id,
        )
    )
    existing_doc = dup_result.scalar_one_or_none()

    if existing_doc:
        # Return existing document info — no need to re-upload
        logger.info(
            "duplicate_upload_detected",
            user_id=current_user.id,
            document_id=existing_doc.id,
            hash=sha256_hash,
        )
        return DocumentUploadResponse(
            document_id=existing_doc.id,
            filename=existing_doc.original_filename,
            page_count=existing_doc.page_count,
            file_size_bytes=existing_doc.file_size_bytes,
            sha256_hash=sha256_hash,
            is_duplicate=True,
            expires_at=existing_doc.expires_at,
            status=existing_doc.status,
            message="Duplicate detected. Using existing document.",
        )

    # Unique S3 key: users/{user_id}/docs/{doc_id}/{filename}
    doc_id = str(uuid.uuid4())
    safe_filename = file.filename.replace(" ", "_").replace("/", "_")
    s3_key = f"users/{current_user.id}/docs/{doc_id}/{safe_filename}"

    # Upload to storage (S3 or local filesystem)
    try:
        await upload_to_storage(file_bytes, s3_key, "application/pdf")
    except Exception as e:
        logger.error("storage_upload_failed", user_id=current_user.id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Storage upload failed: {str(e)}",
        )

    # Calculate lifecycle expiry (48 hours from now)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=48)

    # Create DB record
    document = Document(
        id=doc_id,
        owner_id=current_user.id,
        original_filename=file.filename,
        s3_key=s3_key,
        sha256_hash=sha256_hash,
        file_size_bytes=len(file_bytes),
        page_count=page_count,
        mime_type="application/pdf",
        language=language,
        status="uploaded",
        is_indexed=False,
        expires_at=expires_at,
    )
    db.add(document)

    # Audit log
    audit = AuditLog(
        user_id=current_user.id,
        event_type="document_uploaded",
        event_category="upload",
        resource_type="document",
        resource_id=doc_id,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("User-Agent"),
        request_id=getattr(request.state, "request_id", None),
        details={
            "filename": file.filename,
            "file_size": len(file_bytes),
            "page_count": page_count,
            "language": language,
        },
    )
    db.add(audit)
    await db.commit()

    logger.info(
        "document_uploaded",
        user_id=current_user.id,
        document_id=doc_id,
        pages=page_count,
        size=len(file_bytes),
    )

    return DocumentUploadResponse(
        document_id=doc_id,
        filename=file.filename,
        page_count=page_count,
        file_size_bytes=len(file_bytes),
        sha256_hash=sha256_hash,
        is_duplicate=False,
        expires_at=expires_at,
        status="uploaded",
    )


# ===========================================================
# LIST DOCUMENTS
# ===========================================================
@router.get(
    "/documents",
    response_model=DocumentListResponse,
    summary="List all uploaded documents",
)
async def list_documents(
    page: int = 1,
    page_size: int = 20,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """**List all documents uploaded by the current user (paginated).**"""
    offset = (page - 1) * page_size

    result = await db.execute(
        select(Document)
        .where(Document.owner_id == current_user.id)
        .order_by(desc(Document.created_at))
        .offset(offset)
        .limit(page_size)
    )
    docs = result.scalars().all()

    # Count total
    from sqlalchemy import func
    count_result = await db.execute(
        select(func.count(Document.id)).where(Document.owner_id == current_user.id)
    )
    total = count_result.scalar_one()

    return DocumentListResponse(
        documents=[DocumentSummary.model_validate(d) for d in docs],
        total=total,
        page=page,
        page_size=page_size,
    )


# ===========================================================
# GET DOCUMENT DETAILS
# ===========================================================
@router.get(
    "/documents/{document_id}",
    response_model=DocumentSummary,
    summary="Get document details by ID",
)
async def get_document(
    document_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """**Get details of a specific document.**"""
    result = await db.execute(
        select(Document).where(
            Document.id == document_id,
            Document.owner_id == current_user.id,  # Ownership check
        )
    )
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found.",
        )

    return DocumentSummary.model_validate(document)


# ===========================================================
# DELETE DOCUMENT
# ===========================================================
@router.delete(
    "/documents/{document_id}",
    response_model=SuccessResponse,
    summary="Delete a document and all associated data",
)
async def delete_document(
    document_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    **Delete a document and all associated jobs/results.**

    - Deletes DB record (cascades to jobs, page indices)
    - Queues S3 deletion as a background task
    - Cannot be undone
    """
    result = await db.execute(
        select(Document).where(
            Document.id == document_id,
            Document.owner_id == current_user.id,
        )
    )
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found.",
        )

    s3_key = document.s3_key

    # Delete from DB (cascade deletes jobs/page_indices)
    await db.delete(document)

    # Audit log
    audit = AuditLog(
        user_id=current_user.id,
        event_type="document_deleted",
        event_category="upload",
        resource_type="document",
        resource_id=document_id,
        ip_address=request.client.host if request.client else None,
        request_id=getattr(request.state, "request_id", None),
    )
    db.add(audit)
    await db.commit()

    # Delete from S3 in background (non-blocking)
    background_tasks.add_task(delete_from_s3, s3_key)

    logger.info("document_deleted", user_id=current_user.id, document_id=document_id)
    return SuccessResponse(message="Document deleted successfully.")
