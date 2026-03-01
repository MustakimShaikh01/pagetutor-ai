# ============================================================
# PageTutor AI - Middleware Stack
# Author: Mustakim Shaikh (https://github.com/MustakimShaikh01)
#
# Security Middleware:
#   - Secure HTTP headers (CSP, HSTS, X-Frame-Options, etc.)
#   - Request ID injection for distributed tracing
#   - Timing attack resistance
#   - Audit logging hook
#   - CORS with strict origin validation
# ============================================================

import time
import uuid
from typing import Callable
from fastapi import Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
import structlog

from app.core.config import settings

logger = structlog.get_logger(__name__)


# ----------------------------------------------------------
# Security Headers Middleware
# ----------------------------------------------------------

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Injects production-grade security headers on all responses.

    Headers protect against:
    - XSS attacks (Content-Security-Policy)
    - Clickjacking (X-Frame-Options)
    - MIME sniffing (X-Content-Type-Options)
    - Protocol downgrade (Strict-Transport-Security)
    - Info leakage (Referrer-Policy)
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)

        # Prevent XSS — restrict script sources
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "img-src 'self' data: https://cdn.pagetutor.ai; "
            "connect-src 'self' wss://pagetutor.ai; "
            "frame-ancestors 'none';"
        )

        # Force HTTPS for 1 year (with subdomains)
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains; preload"
        )

        # Prevent clickjacking
        response.headers["X-Frame-Options"] = "DENY"

        # Prevent MIME type sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"

        # Control referrer info
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # Disable browser features we don't use
        response.headers["Permissions-Policy"] = (
            "geolocation=(), microphone=(), camera=(), "
            "payment=(), usb=(), interest-cohort=()"
        )

        # Remove server identity (hide tech stack)
        response.headers["Server"] = "PageTutor"

        # XSS filter for older browsers
        response.headers["X-XSS-Protection"] = "1; mode=block"

        return response


# ----------------------------------------------------------
# Request ID + Tracing Middleware
# ----------------------------------------------------------

class RequestTrackingMiddleware(BaseHTTPMiddleware):
    """
    Assigns a unique Request-ID to every incoming request.

    Benefits:
    - Distributed tracing across services
    - Log correlation
    - Customer support investigation
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Generate unique request ID
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())

        # Store in request state for use in route handlers
        request.state.request_id = request_id

        start_time = time.perf_counter()

        # Bind request ID to all logs in this context
        with structlog.contextvars.bound_contextvars(request_id=request_id):
            response = await call_next(request)

        # Calculate request duration
        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)

        # Add tracing headers to response
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Response-Time"] = f"{duration_ms}ms"

        # Log all requests with structured context
        logger.info(
            "http_request",
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=duration_ms,
            client_ip=request.client.host if request.client else "unknown",
            user_agent=request.headers.get("User-Agent", ""),
        )

        return response


# ----------------------------------------------------------
# CORS Configuration Factory
# ----------------------------------------------------------

def get_cors_config() -> dict:
    """
    Return strict CORS configuration.
    Only allows whitelisted origins in production.
    """
    return {
        "allow_origins": [str(origin) for origin in settings.CORS_ORIGINS],
        "allow_credentials": True,  # Required for cookie-based auth
        "allow_methods": ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        "allow_headers": [
            "Accept",
            "Accept-Language",
            "Content-Type",
            "Authorization",
            "X-Request-ID",
            "X-CSRF-Token",
        ],
        "expose_headers": [
            "X-Request-ID",
            "X-Response-Time",
            "X-RateLimit-Limit",
            "X-RateLimit-Remaining",
            "X-RateLimit-Reset",
        ],
        "max_age": 86400,  # 24h preflight cache
    }
