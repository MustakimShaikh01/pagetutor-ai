# ============================================================
# PageTutor AI - Admin Dashboard API Routes
# Author: Mustakim Shaikh (https://github.com/MustakimShaikh01)
#
# All routes require admin role.
# Endpoints:
#   GET  /admin/stats          — System statistics
#   GET  /admin/users          — List all users
#   GET  /admin/users/{id}     — Get user details
#   PUT  /admin/users/{id}     — Update user (role/tier/status)
#   GET  /admin/jobs           — All jobs (any user)
#   GET  /admin/audit-logs     — Audit log viewer
#   POST /admin/users/{id}/ban — Ban a user
#   GET  /admin/queue-status   — Celery queue health
# ============================================================

from typing import List, Optional
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc, and_
import structlog

from app.core.security import get_current_admin_user
from app.db.session import get_db
from app.models.models import User, Document, Job, AuditLog, Billing
from app.schemas.schemas import (
    UserPublicResponse, UserAdminUpdateRequest,
    SystemStatsResponse, SuccessResponse, ErrorResponse,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/admin", tags=["Admin Dashboard"])


# ===========================================================
# SYSTEM STATISTICS
# ===========================================================
@router.get(
    "/stats",
    response_model=SystemStatsResponse,
    summary="[Admin] Get system-wide statistics",
    response_description="Counts of users, jobs, storage, queue depth",
)
async def get_system_stats(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin_user),  # Admin only
):
    """
    **Admin: Get real-time system statistics.**

    Aggregates:
    - Total users + active in last 24h
    - Total documents
    - Job counts by status
    - Queue depth from Redis
    """
    now = datetime.now(timezone.utc)
    yesterday = now - timedelta(hours=24)

    # Total users
    total_users = (await db.execute(select(func.count(User.id)))).scalar_one()

    # Active users in last 24h
    active_users = (await db.execute(
        select(func.count(User.id)).where(User.last_login_at >= yesterday)
    )).scalar_one()

    # Total documents
    total_docs = (await db.execute(select(func.count(Document.id)))).scalar_one()

    # Total jobs
    total_jobs = (await db.execute(select(func.count(Job.id)))).scalar_one()

    # Pending jobs
    pending_jobs = (await db.execute(
        select(func.count(Job.id)).where(Job.status == "pending")
    )).scalar_one()

    # Processing jobs
    processing_jobs = (await db.execute(
        select(func.count(Job.id)).where(Job.status == "processing")
    )).scalar_one()

    # Failed jobs in last 24h
    failed_jobs = (await db.execute(
        select(func.count(Job.id)).where(
            and_(Job.status == "failed", Job.created_at >= yesterday)
        )
    )).scalar_one()

    # Storage stats
    total_storage_result = await db.execute(
        select(func.coalesce(func.sum(Document.file_size_bytes), 0))
    )
    total_storage_bytes = total_storage_result.scalar_one()
    storage_gb = round(total_storage_bytes / (1024 ** 3), 2)

    # Queue depth from Redis
    from app.core.rate_limiter import get_redis
    try:
        redis = await get_redis()
        queue_depth = 0
        for q in ["high_priority", "normal_priority", "low_priority"]:
            depth = await redis.llen(f"celery:{q}")
            queue_depth += depth or 0
    except Exception:
        queue_depth = -1  # Redis unavailable

    logger.info("admin_stats_accessed", admin_id=admin.id)

    return SystemStatsResponse(
        total_users=total_users,
        active_users_24h=active_users,
        total_documents=total_docs,
        total_jobs=total_jobs,
        pending_jobs=pending_jobs,
        processing_jobs=processing_jobs,
        failed_jobs_24h=failed_jobs,
        storage_used_gb=storage_gb,
        queue_depth=queue_depth,
    )


# ===========================================================
# LIST ALL USERS
# ===========================================================
@router.get(
    "/users",
    response_model=List[UserPublicResponse],
    summary="[Admin] List all registered users",
)
async def list_all_users(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, le=200),
    tier: Optional[str] = Query(None, description="Filter by tier: free|basic|pro|enterprise"),
    role: Optional[str] = Query(None, description="Filter by role: user|admin"),
    search: Optional[str] = Query(None, description="Search by email or name"),
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin_user),
):
    """**Admin: List all users with optional filtering and pagination.**"""
    query = select(User)

    if tier:
        query = query.where(User.tier == tier)
    if role:
        query = query.where(User.role == role)
    if search:
        query = query.where(
            User.email.ilike(f"%{search}%") | User.full_name.ilike(f"%{search}%")
        )

    query = query.order_by(desc(User.created_at)).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    users = result.scalars().all()

    return [UserPublicResponse.model_validate(u) for u in users]


# ===========================================================
# GET USER DETAILS (Admin)
# ===========================================================
@router.get(
    "/users/{user_id}",
    response_model=UserPublicResponse,
    summary="[Admin] Get detailed user info",
)
async def admin_get_user(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin_user),
):
    """**Admin: Get full details for a specific user.**"""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    return UserPublicResponse.model_validate(user)


# ===========================================================
# UPDATE USER (Admin)
# ===========================================================
@router.put(
    "/users/{user_id}",
    response_model=UserPublicResponse,
    summary="[Admin] Update user role, tier, or status",
)
async def admin_update_user(
    user_id: str,
    payload: UserAdminUpdateRequest,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin_user),
):
    """
    **Admin: Modify user account properties.**

    Can change:
    - `role`: user | admin | moderator
    - `tier`: free | basic | pro | enterprise
    - `is_active`: enable/disable account
    - `is_verified`: manually verify email
    """
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    # Prevent admin from demoting themselves
    if user_id == admin.id and payload.role and payload.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot change your own admin role.",
        )

    if payload.role is not None:
        user.role = payload.role.value
    if payload.tier is not None:
        user.tier = payload.tier.value
    if payload.is_active is not None:
        user.is_active = payload.is_active
    if payload.is_verified is not None:
        user.is_verified = payload.is_verified

    await db.commit()
    await db.refresh(user)

    logger.info(
        "admin_user_updated",
        admin_id=admin.id,
        target_user_id=user_id,
        changes=payload.model_dump(exclude_none=True),
    )

    return UserPublicResponse.model_validate(user)


# ===========================================================
# BAN USER
# ===========================================================
@router.post(
    "/users/{user_id}/ban",
    response_model=SuccessResponse,
    summary="[Admin] Ban (deactivate) a user account",
)
async def ban_user(
    user_id: str,
    reason: str = Query(..., description="Reason for banning the user"),
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin_user),
):
    """**Admin: Permanently deactivate a user account.**"""
    if user_id == admin.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot ban yourself.",
        )

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    user.is_active = False

    # Log ban event
    audit = AuditLog(
        user_id=admin.id,
        event_type="user_banned",
        event_category="admin",
        resource_type="user",
        resource_id=user_id,
        details={"reason": reason, "banned_email": user.email},
    )
    db.add(audit)
    await db.commit()

    logger.warning("user_banned", admin_id=admin.id, target_user=user_id, reason=reason)
    return SuccessResponse(message=f"User {user.email} has been banned.")


# ===========================================================
# VIEW AUDIT LOGS
# ===========================================================
@router.get(
    "/audit-logs",
    response_model=List[dict],
    summary="[Admin] View audit logs",
)
async def get_audit_logs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, le=200),
    event_type: Optional[str] = Query(None, description="Filter by event type"),
    user_id: Optional[str] = Query(None, description="Filter by user ID"),
    category: Optional[str] = Query(None, description="Filter by category: auth|upload|job|billing"),
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin_user),
):
    """
    **Admin: View system-wide audit logs.**

    GDPR Note: Logs containing PII are flagged with `contains_pii=true`.
    Logs are retained for {settings.AUDIT_LOG_RETENTION_DAYS} days by policy.
    """
    query = select(AuditLog)

    if event_type:
        query = query.where(AuditLog.event_type == event_type)
    if user_id:
        query = query.where(AuditLog.user_id == user_id)
    if category:
        query = query.where(AuditLog.event_category == category)

    query = query.order_by(desc(AuditLog.created_at)).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    logs = result.scalars().all()

    return [
        {
            "id": log.id,
            "user_id": log.user_id,
            "event_type": log.event_type,
            "event_category": log.event_category,
            "ip_address": log.ip_address,
            "success": log.success,
            "error_code": log.error_code,
            "details": log.details,
            "created_at": log.created_at.isoformat() if log.created_at else None,
        }
        for log in logs
    ]


# ===========================================================
# QUEUE STATUS
# ===========================================================
@router.get(
    "/queue-status",
    summary="[Admin] Get Celery queue status",
    response_model=dict,
)
async def queue_status(
    admin: User = Depends(get_current_admin_user),
):
    """**Admin: Get Celery worker and queue status.**"""
    from app.core.rate_limiter import get_redis
    redis = await get_redis()

    status_data = {}
    for queue in ["high_priority", "normal_priority", "low_priority"]:
        length = await redis.llen(f"celery:{queue}") or 0
        status_data[queue] = {"queue_depth": length}

    return {
        "queues": status_data,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
