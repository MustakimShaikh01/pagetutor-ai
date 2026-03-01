# ============================================================
# PageTutor AI - Main Celery Task Dispatcher
# Author: Mustakim Shaikh (https://github.com/MustakimShaikh01)
#
# dispatch_job is the entry point that:
#   1. Updates job status to "processing"
#   2. Dispatches sub-tasks to appropriate queues
#   3. Aggregates results when all sub-tasks complete
#   4. Handles retries and dead-letter queuing
#   5. Runs maintenance tasks (cleanup, log purge)
# ============================================================

import asyncio
from datetime import datetime, timezone, timedelta
from typing import Optional

from celery import chord, chain, group
import structlog

from app.workers.celery_app import celery_app
from app.core.config import settings

logger = structlog.get_logger(__name__)


# ----------------------------------------------------------
# Async helper: run async DB operations from sync Celery task
# ----------------------------------------------------------
def run_async(coro):
    """Execute an async coroutine from a synchronous Celery task."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def update_job_status(job_id: str, status: str, progress: int = 0,
                            error: Optional[str] = None, tokens: int = 0):
    """Update job status in PostgreSQL database."""
    from app.db.session import AsyncSessionLocal
    from app.models.models import Job
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Job).where(Job.id == job_id))
        job = result.scalar_one_or_none()
        if job:
            job.status = status
            job.progress = progress
            if error:
                job.error_message = error
            if tokens:
                job.tokens_used = tokens
            if status == "processing" and not job.started_at:
                job.started_at = datetime.now(timezone.utc)
            if status in ("completed", "failed", "cancelled"):
                job.completed_at = datetime.now(timezone.utc)
                if job.started_at:
                    job.processing_time_seconds = (
                        job.completed_at - job.started_at
                    ).total_seconds()
            await db.commit()


async def save_job_result(job_id: str, result_type: str,
                          content: Optional[dict] = None,
                          s3_url: Optional[str] = None):
    """Save a job result record to the database."""
    from app.db.session import AsyncSessionLocal
    from app.models.models import JobResult

    async with AsyncSessionLocal() as db:
        result = JobResult(
            job_id=job_id,
            result_type=result_type,
            content=content,
            s3_url=s3_url,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=48),
        )
        db.add(result)
        await db.commit()


# ===========================================================
# MAIN DISPATCHER TASK
# ===========================================================
@celery_app.task(
    name="app.workers.tasks.dispatch_job",
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    acks_late=True,
    reject_on_worker_lost=True,
)
def dispatch_job(
    self,
    job_id: str,
    job_type: str,
    document_id: str,
    user_id: str,
    config: dict = None,
    language: str = "en",
):
    """
    Main job dispatcher.

    Routes sub-tasks based on job_type:
    - full_pipeline: runs ALL sub-tasks sequentially/parallel
    - individual types: runs only the requested task

    Uses Celery chains for sequential deps and chords for parallel.
    """
    config = config or {}
    logger.info("dispatching_job", job_id=job_id, job_type=job_type)

    try:
        # Update status to processing
        run_async(update_job_status(job_id, "processing", progress=5))

        if job_type == "full_pipeline":
            _run_full_pipeline(job_id, document_id, user_id, config, language)
        elif job_type == "summarize":
            _run_summarize(job_id, document_id, config)
        elif job_type == "segment":
            _run_segment(job_id, document_id, config)
        elif job_type == "ppt":
            _run_ppt(job_id, document_id, config)
        elif job_type == "tts":
            _run_tts(job_id, document_id, language, config)
        elif job_type == "video":
            _run_video(job_id, document_id, language, config)
        elif job_type == "flashcards":
            _run_flashcards(job_id, document_id, config)
        elif job_type == "quiz":
            _run_quiz(job_id, document_id, config)
        else:
            raise ValueError(f"Unknown job_type: {job_type}")

        # Mark as completed
        run_async(update_job_status(job_id, "completed", progress=100))
        logger.info("job_completed", job_id=job_id)

    except Exception as exc:
        logger.error("job_failed", job_id=job_id, error=str(exc))

        # Retry with exponential backoff
        try:
            raise self.retry(exc=exc, countdown=30 * (2 ** self.request.retries))
        except self.MaxRetriesExceededError:
            # All retries failed → mark as permanently failed
            run_async(update_job_status(
                job_id, "failed",
                error=f"Job failed after {self.max_retries} retries: {str(exc)}"
            ))


# ----------------------------------------------------------
# Pipeline Runners
# ----------------------------------------------------------

def _run_full_pipeline(job_id, document_id, user_id, config, language):
    """Run all features for full_pipeline job type."""
    from app.workers.llm_tasks import (
        summarize_document, segment_topics,
        generate_flashcards, generate_quiz
    )
    from app.workers.media_tasks import generate_tts, generate_video, generate_ppt
    from app.workers.embed_tasks import index_document_pages

    # Step 1: Index pages (required for chat + all other tasks)
    run_async(update_job_status(job_id, "processing", progress=10))
    index_result = index_document_pages(job_id, document_id)

    # Step 2: LLM summarization (uses indexed page data)
    run_async(update_job_status(job_id, "processing", progress=25))
    summary, learning_points, tokens = summarize_document(job_id, document_id)
    run_async(save_job_result(job_id, "summary", {"text": summary}))
    run_async(save_job_result(job_id, "learning_points", {"points": learning_points}))

    # Step 3: Topic segmentation
    run_async(update_job_status(job_id, "processing", progress=40))
    segments = segment_topics(job_id, document_id)
    run_async(save_job_result(job_id, "segments", {"segments": segments}))

    # Step 4: Flashcards + Quiz (parallel — both use same LLM context)
    run_async(update_job_status(job_id, "processing", progress=55))
    flashcards = generate_flashcards(job_id, document_id, config.get("flashcard_count", 15))
    run_async(save_job_result(job_id, "flashcards", {"cards": flashcards}))

    quiz = generate_quiz(job_id, document_id, config.get("quiz_question_count", 10))
    run_async(save_job_result(job_id, "quiz", {"questions": quiz}))

    # Step 5: PPT generation (based on segments)
    run_async(update_job_status(job_id, "processing", progress=70))
    ppt_url = generate_ppt(job_id, document_id, segments, summary)
    run_async(save_job_result(job_id, "ppt_url", s3_url=ppt_url))

    # Step 6: TTS (narrate summary)
    run_async(update_job_status(job_id, "processing", progress=82))
    audio_url = generate_tts(job_id, summary, language)
    run_async(save_job_result(job_id, "audio_url", s3_url=audio_url))

    # Step 7: Video (combine PPT slides + audio)
    run_async(update_job_status(job_id, "processing", progress=92))
    video_url = generate_video(job_id, ppt_url, audio_url)
    run_async(save_job_result(job_id, "video_url", s3_url=video_url))


def _run_summarize(job_id, document_id, config):
    from app.workers.llm_tasks import summarize_document
    summary, points, tokens = summarize_document(job_id, document_id)
    run_async(save_job_result(job_id, "summary", {"text": summary}))
    run_async(save_job_result(job_id, "learning_points", {"points": points}))


def _run_segment(job_id, document_id, config):
    from app.workers.llm_tasks import segment_topics
    segments = segment_topics(job_id, document_id)
    run_async(save_job_result(job_id, "segments", {"segments": segments}))


def _run_ppt(job_id, document_id, config):
    from app.workers.llm_tasks import segment_topics, summarize_document
    from app.workers.media_tasks import generate_ppt
    summary, _, _ = summarize_document(job_id, document_id)
    segments = segment_topics(job_id, document_id)
    ppt_url = generate_ppt(job_id, document_id, segments, summary)
    run_async(save_job_result(job_id, "ppt_url", s3_url=ppt_url))


def _run_tts(job_id, document_id, language, config):
    from app.workers.llm_tasks import summarize_document
    from app.workers.media_tasks import generate_tts
    summary, _, _ = summarize_document(job_id, document_id)
    audio_url = generate_tts(job_id, summary, language)
    run_async(save_job_result(job_id, "audio_url", s3_url=audio_url))


def _run_video(job_id, document_id, language, config):
    from app.workers.llm_tasks import segment_topics, summarize_document
    from app.workers.media_tasks import generate_ppt, generate_tts, generate_video
    summary, _, _ = summarize_document(job_id, document_id)
    segments = segment_topics(job_id, document_id)
    ppt_url = generate_ppt(job_id, document_id, segments, summary)
    audio_url = generate_tts(job_id, summary, language)
    video_url = generate_video(job_id, ppt_url, audio_url)
    run_async(save_job_result(job_id, "video_url", s3_url=video_url))


def _run_flashcards(job_id, document_id, config):
    from app.workers.llm_tasks import generate_flashcards
    cards = generate_flashcards(job_id, document_id, config.get("count", 15))
    run_async(save_job_result(job_id, "flashcards", {"cards": cards}))


def _run_quiz(job_id, document_id, config):
    from app.workers.llm_tasks import generate_quiz
    questions = generate_quiz(job_id, document_id, config.get("count", 10))
    run_async(save_job_result(job_id, "quiz", {"questions": questions}))


# ===========================================================
# MAINTENANCE TASKS (Celery Beat Scheduler)
# ===========================================================

@celery_app.task(name="app.workers.tasks.cleanup_expired_documents")
def cleanup_expired_documents():
    """
    Scheduled task: Delete expired PDFs from S3 and mark
    the DB record as expired. Runs every 6 hours.

    This implements the 48-hour lifecycle policy:
    - Raw PDFs are deleted to minimize storage costs
    - Processed outputs (PPT, video) also deleted
    - PageIndex and summary are retained for chat functionality
    """
    from datetime import datetime, timezone

    async def _cleanup():
        from app.db.session import AsyncSessionLocal
        from app.models.models import Document
        from sqlalchemy import select, and_

        async with AsyncSessionLocal() as db:
            now = datetime.now(timezone.utc)
            result = await db.execute(
                select(Document).where(
                    and_(
                        Document.expires_at <= now,
                        Document.status != "expired",
                    )
                )
            )
            expired_docs = result.scalars().all()

            deleted_count = 0
            for doc in expired_docs:
                try:
                    # S3 deletion (will be handled by S3 lifecycle policy too)
                    # Just mark as expired in DB
                    doc.status = "expired"
                    deleted_count += 1
                except Exception as e:
                    logger.error("cleanup_error", doc_id=doc.id, error=str(e))

            await db.commit()
            logger.info(
                "cleanup_completed",
                expired_count=deleted_count,
            )

    run_async(_cleanup())


@celery_app.task(name="app.workers.tasks.purge_old_audit_logs")
def purge_old_audit_logs():
    """
    GDPR compliance: Delete audit logs older than retention policy.
    Runs daily at 2 AM UTC.
    """
    async def _purge():
        from app.db.session import AsyncSessionLocal
        from app.models.models import AuditLog
        from sqlalchemy import delete

        cutoff = datetime.now(timezone.utc) - timedelta(days=settings.AUDIT_LOG_RETENTION_DAYS)

        async with AsyncSessionLocal() as db:
            result = await db.execute(
                delete(AuditLog).where(AuditLog.created_at < cutoff)
            )
            await db.commit()
            logger.info(
                "audit_logs_purged",
                cutoff=cutoff.isoformat(),
                rows_deleted=result.rowcount,
            )

    run_async(_purge())


@celery_app.task(name="app.workers.tasks.monitor_queue_depth")
def monitor_queue_depth():
    """
    Monitor queue depth and alert if it exceeds threshold.
    Used for auto-scaling decisions.
    """
    import redis
    r = redis.from_url(settings.REDIS_URL)

    total_depth = 0
    for queue in ["high_priority", "normal_priority", "low_priority"]:
        depth = r.llen(f"celery:{queue}") or 0
        total_depth += depth

    if total_depth > 100:
        logger.warning(
            "high_queue_depth",
            total_depth=total_depth,
            alert="Consider scaling up workers",
        )
    else:
        logger.info("queue_depth_normal", total_depth=total_depth)
