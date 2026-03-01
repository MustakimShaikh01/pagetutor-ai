# ============================================================
# PageTutor AI - Main FastAPI Application
# Author: Mustakim Shaikh (https://github.com/MustakimShaikh01)
# GitHub: https://github.com/MustakimShaikh01
#
# Entry point for the FastAPI application.
# Designed to run WITH or WITHOUT Docker (graceful fallbacks).
# ============================================================

import time
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.openapi.docs import get_swagger_ui_html, get_redoc_html
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
from starlette.responses import Response
import structlog

from app.core.config import settings
from app.core.middleware import SecurityHeadersMiddleware, RequestTrackingMiddleware, get_cors_config
from app.core.rate_limiter import RateLimitMiddleware
from app.db.session import engine, Base, check_db_health, create_all_tables

# Import API routers
from app.api.v1 import auth, upload, jobs, chat, admin

logger = structlog.get_logger(__name__)

# ----------------------------------------------------------
# Prometheus Metrics
# ----------------------------------------------------------
REQUEST_COUNT = Counter(
    "pagetutor_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status"],
)
REQUEST_LATENCY = Histogram(
    "pagetutor_request_duration_seconds",
    "HTTP request latency",
    ["method", "endpoint"],
)

APP_START_TIME = time.time()


# ----------------------------------------------------------
# Lifespan: Startup + Shutdown
# ----------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    """
    Startup and shutdown lifecycle.
    Gracefully handles missing services (Redis, S3, Qdrant).
    """
    logger.info(
        "starting_pagetutor_ai",
        version=settings.APP_VERSION,
        environment=settings.ENVIRONMENT,
        author="Mustakim Shaikh",
        github="https://github.com/MustakimShaikh01",
        database=settings.DATABASE_URL.split("?")[0],
    )

    # Always create DB tables on startup (safe to run multiple times)
    try:
        await create_all_tables()
        logger.info("database_ready")
    except Exception as e:
        logger.error("database_init_failed", error=str(e))
        raise  # Cannot continue without DB

    # Create local upload directory (S3 fallback)
    if settings.USE_LOCAL_STORAGE:
        import os
        os.makedirs("uploads/pdfs", exist_ok=True)
        os.makedirs("uploads/outputs", exist_ok=True)
        logger.info("local_storage_ready", path="uploads/")

    # Check Redis (informational only — app works without it)
    from app.core.rate_limiter import get_redis
    redis = await get_redis()
    if redis:
        logger.info("redis_connected")
    else:
        logger.warning("redis_not_connected", note="Rate limiting disabled")

    logger.info("🚀 PageTutor AI is ready!", docs="http://localhost:8000/docs")

    yield  # ← Application runs here

    # Shutdown
    logger.info("shutting_down_pagetutor_ai")
    await engine.dispose()
    logger.info("database_connections_closed")


# ----------------------------------------------------------
# Create FastAPI Application
# ----------------------------------------------------------
app = FastAPI(
    title=settings.APP_NAME,
    description=f"""
## 🎓 {settings.APP_NAME}

**Enterprise AI-Powered PDF Learning Platform**

Built by **{settings.APP_AUTHOR}** | [GitHub](https://github.com/MustakimShaikh01)

---

### 🚀 Features

| Feature | Description |
|---------|-------------|
| 📄 **Summary** | AI-generated structured summaries |
| 🗂️ **Segments** | Auto-detected topic chapters |
| 📊 **PPT** | Exportable PowerPoint slides |
| 🗣️ **TTS** | Narration in 10+ languages |
| 🎥 **Video** | Full narrated video lecture |
| 🃏 **Flashcards** | Spaced-repetition cards |
| 📝 **Quiz** | MCQ quiz with explanations |
| 💬 **Chat** | RAG-based document Q&A |

---

### 🔑 Authentication

1. Register: `POST /api/v1/auth/register`
2. Login:    `POST /api/v1/auth/login`  
3. Token is set as HttpOnly cookie automatically

Use **🔐 Authorize** above to test with your token.

---

### 📊 Local Dev Mode
- **Database:** SQLite (no PostgreSQL needed)
- **Storage:** Local `uploads/` folder (no MinIO needed)
- **Redis:** Optional (rate limiting disabled if not running)
- **LLM:** API calls gracefully degrade to mock responses

*{settings.APP_NAME} v{settings.APP_VERSION} · by Mustakim Shaikh*
""",
    version=settings.APP_VERSION,
    contact={
        "name": "Mustakim Shaikh",
        "url": "https://github.com/MustakimShaikh01",
    },
    openapi_url=settings.OPENAPI_URL,
    docs_url=None,
    redoc_url=None,
    lifespan=lifespan,
)


# ----------------------------------------------------------
# Middleware Stack (order: outermost first)
# ----------------------------------------------------------
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestTrackingMiddleware)
app.add_middleware(RateLimitMiddleware)

cors_config = get_cors_config()
app.add_middleware(CORSMiddleware, **cors_config)


# ----------------------------------------------------------
# Register API Routers
# ----------------------------------------------------------
API_PREFIX = settings.API_V1_PREFIX

app.include_router(auth.router, prefix=API_PREFIX)
app.include_router(upload.router, prefix=API_PREFIX)
app.include_router(jobs.router, prefix=API_PREFIX)
app.include_router(chat.router, prefix=API_PREFIX)
app.include_router(admin.router, prefix=API_PREFIX)


# ----------------------------------------------------------
# Health Check
# ----------------------------------------------------------
@app.get("/health", tags=["System"], summary="System health check")
async def health_check():
    """Check health of all system components."""
    db_healthy = await check_db_health()

    # Redis check
    try:
        from app.core.rate_limiter import get_redis
        redis = await get_redis()
        redis_healthy = redis is not None
    except Exception:
        redis_healthy = False

    return {
        "status": "healthy" if db_healthy else "degraded",
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
        "author": "Mustakim Shaikh",
        "github": "https://github.com/MustakimShaikh01",
        "uptime_seconds": round(time.time() - APP_START_TIME, 2),
        "services": {
            "database": {"status": "up" if db_healthy else "down", "type": settings.DATABASE_URL.split("+")[0]},
            "redis": {"status": "up" if redis_healthy else "down (optional)"},
            "storage": {"status": "up", "type": "local" if settings.USE_LOCAL_STORAGE else "s3"},
        },
    }


# ----------------------------------------------------------
# Prometheus Metrics
# ----------------------------------------------------------
@app.get("/metrics", tags=["System"], include_in_schema=False)
async def prometheus_metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


# ----------------------------------------------------------
# Custom Swagger UI
# ----------------------------------------------------------
@app.get("/docs", include_in_schema=False)
async def custom_swagger_ui():
    return get_swagger_ui_html(
        openapi_url=settings.OPENAPI_URL,
        title=f"{settings.APP_NAME} — API Docs",
        swagger_favicon_url="https://fastapi.tiangolo.com/img/favicon.png",
        swagger_ui_parameters={
            "persistAuthorization": True,
            "displayRequestDuration": True,
            "tryItOutEnabled": True,
            "defaultModelsExpandDepth": -1,
        },
    )

@app.get("/redoc", include_in_schema=False)
async def custom_redoc():
    return get_redoc_html(
        openapi_url=settings.OPENAPI_URL,
        title=f"{settings.APP_NAME} — API Reference",
    )


# ----------------------------------------------------------
# Root
# ----------------------------------------------------------
@app.get("/", tags=["System"], summary="API root")
async def root():
    return {
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "author": "Mustakim Shaikh",
        "github": "https://github.com/MustakimShaikh01",
        "docs": "http://localhost:8000/docs",
        "health": "http://localhost:8000/health",
        "status": "🚀 PageTutor AI is running!",
        "mode": "local_dev" if settings.USE_LOCAL_STORAGE else "production",
    }


# ----------------------------------------------------------
# Global Exception Handler
# ----------------------------------------------------------
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(
        "unhandled_exception",
        path=request.url.path,
        method=request.method,
        error=str(exc),
        error_type=type(exc).__name__,
    )
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": "internal_server_error",
            "detail": str(exc) if settings.DEBUG else "An unexpected error occurred.",
            "request_id": getattr(request.state, "request_id", None),
        },
    )
