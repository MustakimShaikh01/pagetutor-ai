# ============================================================
# PageTutor AI - Jobs API Routes
# Author: Mustakim Shaikh (https://github.com/MustakimShaikh01)
#
# Endpoints:
#   POST /jobs/create          — Create new processing job
#   GET  /jobs/{job_id}        — Get job status + progress
#   GET  /jobs/{job_id}/result — Get completed job results
#   GET  /jobs/                — List all user jobs
#   POST /jobs/{job_id}/cancel — Cancel a pending/queued job
#
# Local Dev Note:
#   - When Celery/Redis is not available, jobs run in a background thread
#   - This simulates the queue without any external services
# ============================================================

import uuid
import asyncio
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, BackgroundTasks, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
import structlog

from app.core.config import settings
from app.core.security import get_current_user
from app.db.session import get_db
from app.models.models import User, Document, Job, JobResult, AuditLog
from app.schemas.schemas import (
    JobCreateRequest, JobStatusResponse, JobResultResponse,
    SuccessResponse, ErrorResponse, JobStatus,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/jobs", tags=["Processing Jobs"])


# ----------------------------------------------------------
# Priority Mapping: free=low, paid=high
# ----------------------------------------------------------
TIER_PRIORITY_MAP = {
    "free": "low",
    "basic": "normal",
    "pro": "high",
    "enterprise": "high",
}

# ----------------------------------------------------------
# Estimated time per job type (seconds) — for ETA
# ----------------------------------------------------------
JOB_ESTIMATED_SECONDS = {
    "full_pipeline": 300,
    "summarize": 30,
    "segment": 20,
    "ppt": 45,
    "tts": 90,
    "video": 180,
    "flashcards": 25,
    "quiz": 25,
    "chat": 5,
}


# ----------------------------------------------------------
# Dispatch job: Celery if available, else background thread
# ----------------------------------------------------------
def _dispatch_job_background(
    job_id: str,
    job_type: str,
    document_id: str,
    user_id: str,
    config: dict,
    language: str,
):
    """
    Runs a job using Celery if available, otherwise falls back to
    running in a Python thread (local dev mode, no Redis needed).
    """
    try:
        from app.workers.tasks import dispatch_job
        # Try Celery first
        dispatch_job.apply_async(
            args=[job_id, job_type, document_id, user_id],
            kwargs={"config": config, "language": language},
        )
        logger.info("job_dispatched_celery", job_id=job_id)
    except Exception as e:
        logger.warning(
            "celery_not_available_using_thread",
            error=str(e),
            job_id=job_id,
        )
        # Fallback: run in thread using mock processor
        import threading
        thread = threading.Thread(
            target=_run_mock_job,
            args=(job_id, job_type, document_id),
            daemon=True,
        )
        thread.start()


def _run_mock_job(job_id: str, job_type: str, document_id: str):
    """
    Job processor — uses Ollama (offline LLM) when available,
    falls back to deterministic mock for dev/CI without Ollama.

    Steps:
    1. Extract PDF text page-by-page (pdfplumber)
    2. Build SQLite page index (no vector DB)
    3. Generate per-page summaries → combine into document summary
    4. Extract key learning points
    5. Generate flashcards + quiz (from richest pages)
    6. Save all results to job_results table
    """
    import time
    import sqlite3
    import json
    import os
    import uuid as _uuid

    # ── DB path ──────────────────────────────────────────────────
    _this_dir = os.path.dirname(os.path.abspath(__file__))
    _backend_root = os.path.abspath(os.path.join(_this_dir, "../../../"))
    db_url = os.path.join(_backend_root, "pagetutor_dev.db")
    if not os.path.exists(db_url):
        for c in ("pagetutor_dev.db", "./pagetutor_dev.db"):
            if os.path.exists(c):
                db_url = os.path.abspath(c)
                break
    upload_dir = os.path.join(_backend_root, "uploads", "pdfs")

    logger.info("job_processor_start", job_id=job_id, db=db_url)

    def _sql(q, p=()):
        conn = sqlite3.connect(db_url, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        try:
            conn.execute(q, p)
            conn.commit()
        finally:
            conn.close()

    def _fetch(q, p=()):
        conn = sqlite3.connect(db_url, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        try:
            return conn.execute(q, p).fetchone()
        finally:
            conn.close()

    def _save_result(result_type: str, content: dict):
        _sql(
            "INSERT INTO job_results (id, job_id, result_type, content, created_at) VALUES (?,?,?,?,?)",
            (str(_uuid.uuid4()), job_id, result_type,
             json.dumps(content), datetime.now(timezone.utc).isoformat())
        )

    def _progress(pct: int):
        _sql("UPDATE jobs SET progress=? WHERE id=? AND status='processing'", (pct, job_id))

    try:
        # ── Step 0: Mark as processing ───────────────────────────
        _sql("UPDATE jobs SET status='processing', started_at=? WHERE id=?",
             (datetime.now(timezone.utc).isoformat(), job_id))
        _progress(5)

        # ── Step 1: Locate PDF on disk ───────────────────────────
        row = _fetch("SELECT s3_key, original_filename FROM documents WHERE id=?", (document_id,))
        pdf_path = None
        doc_title = "Document"
        if row:
            s3_key, original_filename = row
            doc_title = original_filename or "Document"

            # Build the underscore-filename format used in local storage:
            # pattern: users_{uid}_docs_{doc_id}_{filename}
            uid_part = os.path.dirname(os.path.dirname(s3_key)).replace("/", "_").lstrip("_")
            # e.g. "users/uid/docs/docid/file.pdf" → basename = "file.pdf"
            basename = os.path.basename(s3_key)
            # The on-disk name uses: users_UID_docs_DOCID_FILENAME
            # Extract UID from s3_key: users/{uid}/docs/{docid}/file.pdf
            parts = s3_key.replace("\\", "/").split("/")
            # parts: ['users', uid, 'docs', doc_id, filename]
            uid = parts[1] if len(parts) >= 5 else ""
            did = parts[3] if len(parts) >= 5 else document_id
            underscore_name = f"users_{uid}_docs_{did}_{basename}"

            candidates = [
                s3_key,
                os.path.join(upload_dir, s3_key),
                os.path.join(upload_dir, basename),
                os.path.join(upload_dir, underscore_name),
                # glob fallback: any file ending with _DOCID_*
            ]
            # Also scan upload_dir for any file containing the document_id
            if upload_dir and os.path.isdir(upload_dir):
                for fname in os.listdir(upload_dir):
                    if document_id.replace("-", "") in fname.replace("-", "") or document_id in fname:
                        candidates.append(os.path.join(upload_dir, fname))

            for c in candidates:
                if c and os.path.exists(c):
                    pdf_path = c
                    break

        logger.info("pdf_path_resolved", path=pdf_path, doc=document_id[:8])
        _progress(10)


        # ── Step 2: Extract pages ────────────────────────────────
        page_texts = []
        if pdf_path:
            try:
                from app.services.pdf_extractor import extract_pages, build_page_index
                page_texts = extract_pages(pdf_path)
                _progress(20)
            except Exception as ex:
                logger.warning("pdf_extract_error", error=str(ex))

        has_content = len(page_texts) > 0
        logger.info("pages_extracted", count=len(page_texts))

        # ── Step 3: Try Ollama LLM ───────────────────────────────
        use_llm = False
        try:
            from app.services.llm_service import (
                is_ollama_available, summarise_page, summarise_document,
                extract_key_points, generate_flashcards, generate_quiz, get_model
            )
            use_llm = is_ollama_available() and has_content
            if use_llm:
                logger.info("ollama_active", model=get_model())
            else:
                logger.info("ollama_offline_mock_mode")
        except Exception as ex:
            logger.warning("llm_import_error", error=str(ex))

        # ── Step 4: Generate content ─────────────────────────────
        if use_llm and has_content:
            # 4a: Per-page summaries  (progress: 25→55)
            page_summaries = []
            total = len(page_texts)
            for i, (pnum, ptext) in enumerate(page_texts):
                try:
                    ps = summarise_page(ptext, pnum)
                    page_summaries.append(ps)
                except Exception:
                    page_summaries.append("")
                # Update progress proportionally
                pct = 25 + int((i + 1) / total * 30)
                _progress(pct)
                time.sleep(0.05)  # tiny yield

            _progress(57)

            # Build page index in SQLite (store raw text)
            try:
                from app.services.pdf_extractor import build_page_index
                build_page_index(
                    document_id,
                    pdf_path,
                    db_url,
                    list(zip([p for p, _ in page_texts], page_summaries)),
                )
            except Exception as ex:
                logger.warning("page_index_error", error=str(ex))

            # 4b: Document summary
            summary_text = summarise_document(page_summaries, doc_title)
            _progress(65)

            # 4c: Key points
            key_points = extract_key_points(summary_text, page_summaries)
            _progress(75)

            # 4d: Flashcards
            cards_raw = generate_flashcards(page_texts, n=8)
            _progress(85)

            # 4e: Quiz
            quiz_raw = generate_quiz(page_texts, n=5)
            _progress(93)

        else:
            # ── Deterministic mock ─────────────────────────────
            time.sleep(2)
            _progress(40)

            page_count = len(page_texts) if page_texts else "?"
            if not has_content:
                hint = (
                    "Install Ollama then run:\n"
                    "  ollama serve\n"
                    "  ollama pull qwen2.5:3b\n\n"
                    "Then upload a PDF and create a new job — real AI results will appear."
                )
            else:
                hint = (
                    f"PDF has {page_count} pages of content.\n\n"
                    "To get real AI results, start Ollama:\n"
                    "  brew install ollama\n"
                    "  ollama serve\n"
                    "  ollama pull qwen2.5:3b"
                )

            summary_text = (
                f"📄 **{doc_title}** — Mock Summary (No LLM)\n\n"
                + hint
            )
            key_points = [
                "Install Ollama for real AI-generated content (free, offline)",
                "Run: brew install ollama && ollama serve",
                "Pull model: ollama pull qwen2.5:3b (best quality, 3B params, ~2GB)",
                "Alternative: ollama pull llama3.2:3b or ollama pull gemma2:2b",
                "Once Ollama is running, create a new job to get real results",
            ]
            cards_raw = [
                {"card_id": 1, "front": "What is Ollama?",
                 "back": "Free tool to run LLMs locally on your Mac/PC with no internet or API keys",
                 "topic": "Setup"},
                {"card_id": 2, "front": "Which model should I use?",
                 "back": "qwen2.5:3b is recommended — best quality at 3B params, 32k context window",
                 "topic": "Setup"},
            ]
            quiz_raw = [
                {"question_id": 1, "question_type": "mcq",
                 "question": "Which command installs the recommended LLM for PageTutor AI?",
                 "options": [
                     "A) ollama pull qwen2.5:3b",
                     "B) pip install llama",
                     "C) npm install ollama",
                     "D) apt install llm",
                 ],
                 "correct_answer": "A",
                 "explanation": "qwen2.5:3b is the recommended model — 3B params, 32k context, best speed/quality ratio."},
            ]
            time.sleep(1)
            _progress(93)

        # ── Step 5: Save results ─────────────────────────────────
        _save_result("summary", {"text": summary_text})
        _save_result("learning_points", {"points": key_points})
        _save_result("flashcards", {"cards": cards_raw})
        _save_result("quiz", {"questions": quiz_raw})

        # ── Done ─────────────────────────────────────────────────
        _sql(
            "UPDATE jobs SET status='completed', progress=100, completed_at=? WHERE id=?",
            (datetime.now(timezone.utc).isoformat(), job_id)
        )
        logger.info("job_completed", job_id=job_id, used_llm=use_llm, pages=len(page_texts))

    except Exception as e:
        logger.error("job_failed", job_id=job_id, error=str(e))
        import traceback; traceback.print_exc()
        try:
            _sql("UPDATE jobs SET status='failed', error_message=? WHERE id=?", (str(e)[:500], job_id))
        except Exception:
            pass



def _UNUSED_async_update_and_save():
    """Old async version kept as reference — not used."""
    pass


def _run_mock_job_UNUSED(job_id: str, job_type: str, document_id: str):
    """Old async/thread version — replaced by sync sqlite3 above."""
    import time
    import asyncio

    async def _update_and_save():
        from app.db.session import AsyncSessionLocal
        from app.models.models import Job, JobResult
        from sqlalchemy import select

        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Job).where(Job.id == job_id))
            job = result.scalar_one_or_none()
            if not job:
                return
            job.status = "processing"
            job.started_at = datetime.now(timezone.utc)
            await db.commit()

        for progress in [10, 25, 40, 55, 70, 82, 92, 100]:
            await asyncio.sleep(1.5)
            async with AsyncSessionLocal() as db:
                result = await db.execute(select(Job).where(Job.id == job_id))
                job = result.scalar_one_or_none()
                if job and job.status == "processing":
                    job.progress = progress
                    await db.commit()

        async with AsyncSessionLocal() as db:
            db.add(JobResult(
                job_id=job_id,
                result_type="summary",
                content={
                    "text": (
                        "📄 **Mock Summary** (Local Dev Mode)\n\n"
                        "This is a placeholder summary generated in local dev mode "
                        "without an LLM server. In production, this would contain a "
                        "comprehensive AI-generated summary of your PDF document.\n\n"
                        "To get real AI summaries, start a vLLM server:\n"
                        "`vllm serve mistralai/Mistral-7B-Instruct-v0.2`"
                    )
                },
            ))
            # Mock learning points
            db.add(JobResult(
                job_id=job_id,
                result_type="learning_points",
                content={"points": [
                    "This is a mock learning point #1 (local dev mode)",
                    "Connect a real LLM server for actual AI-generated points",
                    "Set LLM_BASE_URL in your .env file to enable real inference",
                ]},
            ))
            # Mock flashcards
            db.add(JobResult(
                job_id=job_id,
                result_type="flashcards",
                content={"cards": [
                    {"card_id": 1, "front": "What is PageTutor AI?", "back": "An AI-powered PDF learning platform by Mustakim Shaikh", "topic": "Demo"},
                    {"card_id": 2, "front": "How does RAG work?", "back": "Retrieval Augmented Generation retrieves relevant context before generating answers", "topic": "Demo"},
                ]},
            ))
            # Mock quiz
            db.add(JobResult(
                job_id=job_id,
                result_type="quiz",
                content={"questions": [
                    {
                        "question_id": 1,
                        "question": "What does PageTutor AI do? (Mock Question)",
                        "question_type": "mcq",
                        "options": ["A) Converts PDFs to learning content", "B) Plays games", "C) Sends emails", "D) Edits images"],
                        "correct_answer": "A",
                        "explanation": "PageTutor AI transforms PDFs into summaries, quizzes, flashcards, and more.",
                    }
                ]},
            ))

            # Mark job as completed
            result = await db.execute(select(Job).where(Job.id == job_id))
            job = result.scalar_one_or_none()
            if job:
                job.status = "completed"
                job.progress = 100
                job.completed_at = datetime.now(timezone.utc)
                if job.started_at:
                    job.processing_time_seconds = (
                        job.completed_at - job.started_at
                    ).total_seconds()
            await db.commit()

        logger.info("mock_job_completed", job_id=job_id)

    # Run the async function in a new event loop
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(_update_and_save())
    finally:
        loop.close()


# ===========================================================
# CREATE JOB
# ===========================================================
@router.post(
    "/create",
    response_model=JobStatusResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Create a new PDF processing job",
    response_description="Job created and queued for async processing",
    responses={
        202: {"description": "Job accepted and queued"},
        404: {"description": "Document not found", "model": ErrorResponse},
        429: {"description": "Daily job quota exceeded", "model": ErrorResponse},
    },
)
async def create_job(
    payload: JobCreateRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    **Queue a PDF processing job.**

    In production: dispatches to Celery GPU/CPU workers.
    In local dev: simulates job with mock results (no LLM needed).

    Returns immediately with job ID. Poll `/jobs/{job_id}` for progress.
    Progress moves 0% → 100% over ~15 seconds in local dev mode.
    """
    # Verify document exists and belongs to user
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

    # Determine priority
    priority = TIER_PRIORITY_MAP.get(current_user.tier, "normal")

    # Create Job record
    job_id = str(uuid.uuid4())
    job = Job(
        id=job_id,
        owner_id=current_user.id,
        document_id=payload.document_id,
        job_type=payload.job_type.value,
        priority=priority,
        config=payload.config or {},
        status="queued",
        progress=0,
    )
    db.add(job)

    # Audit log
    audit = AuditLog(
        user_id=current_user.id,
        event_type="job_created",
        event_category="job",
        resource_type="job",
        resource_id=job_id,
        ip_address=request.client.host if request.client else None,
        request_id=getattr(request.state, "request_id", None),
        details={
            "job_type": payload.job_type.value,
            "document_id": payload.document_id,
            "priority": priority,
        },
    )
    db.add(audit)
    await db.commit()

    # Dispatch job in background (Celery or thread fallback)
    background_tasks.add_task(
        _dispatch_job_background,
        job_id,
        payload.job_type.value,
        payload.document_id,
        current_user.id,
        payload.config or {},
        payload.language.value if hasattr(payload.language, "value") else "en",
    )

    estimated_seconds = JOB_ESTIMATED_SECONDS.get(payload.job_type.value, 120)

    logger.info(
        "job_queued",
        job_id=job_id,
        job_type=payload.job_type.value,
        user_id=current_user.id,
    )

    return JobStatusResponse(
        job_id=job_id,
        job_type=payload.job_type.value,
        status=JobStatus.queued,
        progress=0,
        tokens_used=0,
        created_at=job.created_at,
        estimated_remaining_seconds=estimated_seconds,
    )


# ===========================================================
# GET JOB STATUS
# ===========================================================
@router.get(
    "/{job_id}",
    response_model=JobStatusResponse,
    summary="Get job status and progress",
)
async def get_job_status(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """**Poll job status and progress percentage.**"""
    result = await db.execute(
        select(Job).where(
            Job.id == job_id,
            Job.owner_id == current_user.id,
        )
    )
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")

    estimated_remaining = None
    if job.status == "processing" and job.progress > 0 and job.started_at:
        elapsed = (datetime.now(timezone.utc) - job.started_at).total_seconds()
        if job.progress > 0:
            estimated_remaining = int(
                (elapsed / job.progress) * (100 - job.progress)
            )

    return JobStatusResponse(
        job_id=job.id,
        job_type=job.job_type,
        status=JobStatus(job.status),
        progress=job.progress,
        error_message=job.error_message,
        tokens_used=job.tokens_used or 0,
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
        estimated_remaining_seconds=estimated_remaining,
    )


# ===========================================================
# GET JOB RESULT
# ===========================================================
@router.get(
    "/{job_id}/result",
    response_model=JobResultResponse,
    summary="Get completed job results",
)
async def get_job_result(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """**Get all outputs from a completed job.**"""
    result = await db.execute(
        select(Job).where(
            Job.id == job_id,
            Job.owner_id == current_user.id,
        )
    )
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")

    if job.status != "completed":
        raise HTTPException(
            status_code=status.HTTP_202_ACCEPTED,
            detail=f"Job is not yet complete. Current status: {job.status} ({job.progress}%)",
        )

    results_q = await db.execute(
        select(JobResult).where(JobResult.job_id == job_id)
    )
    results = results_q.scalars().all()

    response_data = {"job_id": job_id, "document_id": job.document_id}

    for r in results:
        if r.result_type == "summary":
            response_data["summary"] = r.content.get("text") if r.content else None
        elif r.result_type == "learning_points":
            response_data["learning_points"] = r.content.get("points", []) if r.content else []
        elif r.result_type == "segments":
            response_data["segments"] = r.content.get("segments", []) if r.content else []
        elif r.result_type == "ppt_url":
            response_data["ppt_url"] = r.s3_url
        elif r.result_type == "audio_url":
            response_data["audio_url"] = r.s3_url
        elif r.result_type == "video_url":
            response_data["video_url"] = r.s3_url
        elif r.result_type == "flashcards":
            response_data["flashcards"] = r.content.get("cards", []) if r.content else []
        elif r.result_type == "quiz":
            response_data["quiz"] = r.content.get("questions", []) if r.content else []

    return JobResultResponse(**response_data)


# ===========================================================
# LIST USER JOBS
# ===========================================================
@router.get(
    "/",
    response_model=List[JobStatusResponse],
    summary="List all jobs for current user",
)
async def list_jobs(
    status_filter: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """**List all processing jobs (paginated).**"""
    query = select(Job).where(Job.owner_id == current_user.id)

    if status_filter:
        query = query.where(Job.status == status_filter)

    query = query.order_by(desc(Job.created_at)).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    jobs = result.scalars().all()

    return [
        JobStatusResponse(
            job_id=j.id,
            job_type=j.job_type,
            status=JobStatus(j.status),
            progress=j.progress,
            error_message=j.error_message,
            tokens_used=j.tokens_used or 0,
            created_at=j.created_at,
            started_at=j.started_at,
            completed_at=j.completed_at,
        )
        for j in jobs
    ]


# ===========================================================
# CANCEL JOB
# ===========================================================
@router.post(
    "/{job_id}/cancel",
    response_model=SuccessResponse,
    summary="Cancel a pending or queued job",
)
async def cancel_job(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """**Cancel a job that is pending or queued.**"""
    result = await db.execute(
        select(Job).where(
            Job.id == job_id,
            Job.owner_id == current_user.id,
        )
    )
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")

    if job.status not in ("pending", "queued"):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot cancel job with status '{job.status}'.",
        )

    # Try to revoke Celery task (silently fails if Celery not available)
    if job.celery_task_id:
        try:
            from app.workers.celery_app import celery_app
            celery_app.control.revoke(job.celery_task_id, terminate=False)
        except Exception:
            pass  # Celery not running in local dev

    job.status = "cancelled"
    await db.commit()

    return SuccessResponse(message="Job cancelled successfully.")
