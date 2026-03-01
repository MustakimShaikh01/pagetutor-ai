# ============================================================
# PageTutor AI - Celery Application Configuration
# Author: Mustakim Shaikh (https://github.com/MustakimShaikh01)
#
# Job Queue Architecture:
#   - high_priority: Paid users, realtime requests
#   - normal_priority: Basic tier users
#   - low_priority: Free tier users
#   - llm_queue: Routed to GPU workers
#   - media_queue: Routed to CPU workers
#
# Worker Types:
#   - llm_worker: Handles LLM inference (GPU-accelerated)
#   - media_worker: Handles TTS, video, PPT generation (CPU)
#   - embed_worker: Handles embedding + PageIndex creation (CPU/GPU)
# ============================================================

from celery import Celery
from celery.signals import task_prerun, task_postrun, task_failure
from kombu import Queue, Exchange
import structlog

from app.core.config import settings

logger = structlog.get_logger(__name__)

# ----------------------------------------------------------
# Create Celery app
# ----------------------------------------------------------
celery_app = Celery(
    "pagetutor_ai",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=[
        "app.workers.tasks",       # Main dispatch task
        "app.workers.llm_tasks",   # LLM inference tasks
        "app.workers.media_tasks", # TTS + video tasks
        "app.workers.embed_tasks", # Embedding + indexing tasks
    ],
)

# ----------------------------------------------------------
# Celery Configuration
# ----------------------------------------------------------
celery_app.conf.update(
    # Serialization — JSON for security (no pickle)
    task_serializer=settings.CELERY_TASK_SERIALIZER,
    result_serializer=settings.CELERY_RESULT_SERIALIZER,
    accept_content=["json"],

    # Timezone
    timezone="UTC",
    enable_utc=True,

    # Task behavior
    task_acks_late=True,           # Ack only after completion (safe retry on crash)
    task_reject_on_worker_lost=True, # Requeue if worker crashes
    worker_prefetch_multiplier=1,  # Prevent thundering herd: 1 task at a time

    # Result expiry
    result_expires=86400,          # Keep results for 24 hours

    # Retry configuration
    task_max_retries=3,
    task_default_retry_delay=30,   # 30 seconds between retries

    # Timeout — kill stuck tasks
    task_soft_time_limit=600,      # Soft limit: 10 minutes (raises exception)
    task_time_limit=700,           # Hard limit: kill after 11.6 minutes

    # Dynamic batching for LLM tasks
    # Tasks accumulate in queue, worker pulls batch
    worker_max_tasks_per_child=100,  # Restart worker after 100 tasks (memory cleanup)

    # Priority queues (0=low, 9=high)
    task_queue_max_priority=10,
    task_default_priority=5,

    # Dead Letter Queue — failed tasks after max retries
    # These go to a DLQ in Redis for manual inspection
    task_routes={
        # LLM tasks → GPU worker pool
        "app.workers.llm_tasks.*": {"queue": "llm_queue"},

        # Media tasks → CPU worker pool
        "app.workers.media_tasks.*": {"queue": "media_queue"},

        # Embed tasks → embed worker pool
        "app.workers.embed_tasks.*": {"queue": "embed_queue"},

        # Main dispatcher → routes to above based on priority
        "app.workers.tasks.dispatch_job": {"queue": "normal_priority"},
    },
)

# ----------------------------------------------------------
# Queue Definitions with Priority Support
# ----------------------------------------------------------
default_exchange = Exchange("pagetutor", type="direct")
priority_exchange = Exchange("priority", type="direct")

celery_app.conf.task_queues = (
    # Priority queues (all tasks enter here based on user tier)
    Queue(
        "high_priority",
        default_exchange,
        routing_key="high_priority",
        queue_arguments={"x-max-priority": 10},
    ),
    Queue(
        "normal_priority",
        default_exchange,
        routing_key="normal_priority",
        queue_arguments={"x-max-priority": 5},
    ),
    Queue(
        "low_priority",
        default_exchange,
        routing_key="low_priority",
        queue_arguments={"x-max-priority": 1},
    ),

    # Worker-type queues
    Queue("llm_queue", default_exchange, routing_key="llm"),      # GPU workers
    Queue("media_queue", default_exchange, routing_key="media"),   # CPU workers
    Queue("embed_queue", default_exchange, routing_key="embed"),   # Embed workers

    # Dead letter queue
    Queue("dead_letter", default_exchange, routing_key="dlq"),
)

# ----------------------------------------------------------
# Scheduled Tasks (Celery Beat)
# ----------------------------------------------------------
from celery.schedules import crontab

celery_app.conf.beat_schedule = {
    # Cleanup expired documents from S3 (every 6 hours)
    "cleanup-expired-documents": {
        "task": "app.workers.tasks.cleanup_expired_documents",
        "schedule": crontab(minute=0, hour="*/6"),
    },

    # GDPR: Purge old audit logs (daily at 2 AM)
    "purge-old-audit-logs": {
        "task": "app.workers.tasks.purge_old_audit_logs",
        "schedule": crontab(minute=0, hour=2),
    },

    # Monitor queue depth and alert if too high (every 5 minutes)
    "monitor-queue-depth": {
        "task": "app.workers.tasks.monitor_queue_depth",
        "schedule": crontab(minute="*/5"),
    },
}


# ----------------------------------------------------------
# Task Lifecycle Hooks (for audit logging)
# ----------------------------------------------------------

@task_prerun.connect
def task_started(task_id, task, args, kwargs, **extra):
    """Called just before a task starts executing."""
    logger.info(
        "task_started",
        task_id=task_id,
        task_name=task.name,
    )


@task_postrun.connect
def task_completed(task_id, task, args, kwargs, retval, state, **extra):
    """Called after a task completes (success or failure)."""
    logger.info(
        "task_completed",
        task_id=task_id,
        task_name=task.name,
        state=state,
    )


@task_failure.connect
def task_failed(task_id, exception, traceback, einfo, **extra):
    """Called when a task fails after all retries."""
    logger.error(
        "task_permanently_failed",
        task_id=task_id,
        error=str(exception),
    )
