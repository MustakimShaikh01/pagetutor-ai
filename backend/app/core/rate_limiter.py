# ============================================================
# PageTutor AI - Rate Limiter (Redis-based, with graceful fallback)
# Author: Mustakim Shaikh (https://github.com/MustakimShaikh01)
#
# When Redis is NOT available (local dev without Docker):
#   - Rate limiting is silently skipped
#   - App continues to work normally
#
# When Redis IS available:
#   - Sliding window rate limiting per IP
#   - Daily job quotas per user (free vs paid)
# ============================================================

import time
from typing import Optional
import structlog

logger = structlog.get_logger(__name__)

# Cached Redis client (None if not available)
_redis_client = None
_redis_available = None   # None = not yet checked


async def get_redis():
    """
    Get Redis client. Returns None if Redis is not available.
    Checks availability once on first call, then caches result.
    """
    global _redis_client, _redis_available

    if _redis_available is False:
        return None  # Already know Redis is not available

    if _redis_client is not None:
        return _redis_client

    try:
        import redis.asyncio as aioredis
        from app.core.config import settings

        client = aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
            socket_connect_timeout=2,  # 2s timeout to fail fast
        )
        await client.ping()
        _redis_client = client
        _redis_available = True
        logger.info("redis_connected", url=settings.REDIS_URL)
        return _redis_client

    except Exception as e:
        _redis_available = False
        logger.warning(
            "redis_not_available",
            error=str(e),
            note="Rate limiting disabled. Install Redis for production use.",
        )
        return None


async def check_rate_limit(
    identifier: str,  # IP address or user ID
    limit: int = 100,
    window_seconds: int = 60,
) -> tuple[bool, int]:
    """
    Sliding window rate limit check.

    Args:
        identifier: IP or user ID string
        limit: Max requests per window
        window_seconds: Window duration in seconds

    Returns:
        (is_allowed, remaining_requests)
    """
    redis = await get_redis()
    if redis is None:
        # No Redis — allow everything (dev mode)
        return True, limit

    now = time.time()
    key = f"ratelimit:{identifier}"

    try:
        async with redis.pipeline() as pipe:
            # Remove expired entries
            await pipe.zremrangebyscore(key, 0, now - window_seconds)
            # Count current window
            await pipe.zcard(key)
            # Add this request
            await pipe.zadd(key, {str(now): now})
            # Set TTL on key
            await pipe.expire(key, window_seconds)
            results = await pipe.execute()

        current_count = results[1]

        if current_count >= limit:
            return False, 0

        remaining = limit - current_count - 1
        return True, max(remaining, 0)

    except Exception as e:
        logger.error("rate_limit_check_failed", error=str(e))
        return True, limit  # Fail open in case of Redis error


async def check_daily_quota(
    user_id: str,
    tier: str = "free",
) -> tuple[bool, int]:
    """
    Check and increment daily job quota for a user.

    Returns:
        (is_within_quota, remaining)
    """
    from app.core.config import settings

    redis = await get_redis()
    if redis is None:
        # No Redis — allow everything (dev mode)
        return True, 999

    daily_limit = settings.FREE_TIER_DAILY_JOBS if tier == "free" else settings.PAID_TIER_DAILY_JOBS

    # Key rotates daily
    today = time.strftime("%Y%m%d")
    key = f"quota:{user_id}:{today}"

    try:
        current = await redis.incr(key)
        if current == 1:
            # First use today — set expiry to end of day
            await redis.expire(key, 86400)

        if current > daily_limit:
            return False, 0

        return True, daily_limit - current
    except Exception as e:
        logger.error("quota_check_failed", error=str(e))
        return True, 999  # Fail open


async def check_daily_job_quota(user_id: str, tier: str = "free") -> tuple[bool, int]:
    """Alias for check_daily_quota — used by upload/jobs routes."""
    return await check_daily_quota(user_id, tier)


async def get_user_quota_status(user_id: str, tier: str = "free") -> dict:
    """
    Return quota status dict for a user.
    Used by auth and admin routes to display usage info.
    """
    from app.core.config import settings
    daily_limit = settings.FREE_TIER_DAILY_JOBS if tier == "free" else settings.PAID_TIER_DAILY_JOBS

    redis = await get_redis()
    if redis is None:
        return {
            "used": 0,
            "limit": daily_limit,
            "remaining": daily_limit,
            "tier": tier,
            "redis_available": False,
        }

    import time
    today = time.strftime("%Y%m%d")
    key = f"quota:{user_id}:{today}"

    try:
        current = int(await redis.get(key) or 0)
        return {
            "used": current,
            "limit": daily_limit,
            "remaining": max(daily_limit - current, 0),
            "tier": tier,
            "redis_available": True,
        }
    except Exception:
        return {"used": 0, "limit": daily_limit, "remaining": daily_limit, "tier": tier}


# ============================================================
# Middleware
# ============================================================
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from app.core.config import settings


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    IP-based rate limiting middleware.
    Skipped automatically when Redis is not available.
    """

    SKIP_PATHS = {"/health", "/metrics", "/docs", "/redoc", "/openapi.json", "/"}

    async def dispatch(self, request: Request, call_next):
        # Skip rate limiting for certain paths
        if request.url.path in self.SKIP_PATHS:
            return await call_next(request)

        # Get client IP
        client_ip = request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
        if not client_ip:
            client_ip = request.client.host if request.client else "unknown"

        # Check rate limit
        allowed, remaining = await check_rate_limit(
            identifier=f"ip:{client_ip}",
            limit=settings.RATE_LIMIT_REQUESTS,
            window_seconds=settings.RATE_LIMIT_WINDOW,
        )

        if not allowed:
            return JSONResponse(
                status_code=429,
                content={
                    "success": False,
                    "error": "rate_limit_exceeded",
                    "detail": f"Too many requests. Max {settings.RATE_LIMIT_REQUESTS}/min.",
                },
                headers={
                    "Retry-After": str(settings.RATE_LIMIT_WINDOW),
                    "X-RateLimit-Limit": str(settings.RATE_LIMIT_REQUESTS),
                    "X-RateLimit-Remaining": "0",
                },
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(settings.RATE_LIMIT_REQUESTS)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        return response
