# ============================================================
# PageTutor AI - Application Configuration
# Author: Mustakim Shaikh (https://github.com/MustakimShaikh01)
#
# All settings are loaded from environment variables or .env file.
# Override any value by setting it in your .env file.
# ============================================================

from typing import List, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import AnyHttpUrl, field_validator
import secrets


class Settings(BaseSettings):
    """
    Central configuration class using Pydantic BaseSettings.
    All values are read from environment variables or .env file.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ----------------------------------------------------------
    # App Info
    # ----------------------------------------------------------
    APP_NAME: str = "PageTutor AI"
    APP_VERSION: str = "1.0.0"
    APP_AUTHOR: str = "Mustakim Shaikh"
    APP_GITHUB: str = "https://github.com/MustakimShaikh01"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True

    # ----------------------------------------------------------
    # API Routing
    # ----------------------------------------------------------
    API_V1_PREFIX: str = "/api/v1"
    OPENAPI_URL: str = "/openapi.json"

    # ----------------------------------------------------------
    # Security & JWT
    # ----------------------------------------------------------
    SECRET_KEY: str = secrets.token_urlsafe(64)
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # Cookie settings
    COOKIE_SECURE: bool = False      # True in production (HTTPS only)
    COOKIE_HTTPONLY: bool = True
    COOKIE_SAMESITE: str = "lax"

    # ----------------------------------------------------------
    # CORS (Cross-Origin Resource Sharing)
    # ----------------------------------------------------------
    CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://localhost:8000",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:8000",
        "https://pagetutor.ai",
    ]
    CORS_ALLOW_CREDENTIALS: bool = True

    # ----------------------------------------------------------
    # Database (SQLite for local dev, PostgreSQL for production)
    # ----------------------------------------------------------
    DATABASE_URL: str = "sqlite+aiosqlite:///./pagetutor_dev.db"

    # ----------------------------------------------------------
    # Redis (optional for local dev — rate limiting degrades gracefully)
    # ----------------------------------------------------------
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"
    CELERY_TASK_SERIALIZER: str = "json"
    CELERY_RESULT_SERIALIZER: str = "json"

    # ----------------------------------------------------------
    # S3-compatible Object Storage (local: uses filesystem fallback)
    # ----------------------------------------------------------
    S3_ENDPOINT_URL: str = "http://localhost:9000"
    S3_ACCESS_KEY: str = "minioadmin"
    S3_SECRET_KEY: str = "minioadmin123"
    S3_BUCKET_NAME: str = "pagetutor-uploads"
    S3_REGION: str = "us-east-1"
    S3_CDN_BASE_URL: str = "http://localhost:9000/pagetutor-uploads"
    USE_LOCAL_STORAGE: bool = True   # Fallback to local filesystem when S3 not available

    # ----------------------------------------------------------
    # LLM Service (vLLM or TGI — optional for local dev)
    # ----------------------------------------------------------
    LLM_BASE_URL: str = "http://localhost:8080/v1"
    LLM_MODEL_NAME: str = "mistralai/Mistral-7B-Instruct-v0.2"
    LLM_MAX_TOKENS: int = 2048
    LLM_TEMPERATURE: float = 0.2
    LLM_TIMEOUT: int = 120
    LLM_BATCH_SIZE: int = 8

    # ----------------------------------------------------------
    # Embedding Model (sentence-transformers, runs locally)
    # ----------------------------------------------------------
    EMBED_MODEL: str = "all-MiniLM-L6-v2"   # 80MB, runs on CPU
    VECTOR_DIMENSION: int = 384              # all-MiniLM-L6-v2 output dim

    # ----------------------------------------------------------
    # Qdrant Vector Database
    # ----------------------------------------------------------
    QDRANT_HOST: str = "localhost"
    QDRANT_PORT: int = 6333
    QDRANT_API_KEY: Optional[str] = None
    QDRANT_COLLECTION: str = "pagetutor_pages"
    USE_IN_MEMORY_VECTOR: bool = True        # Use in-memory FAISS fallback if Qdrant unavailable

    # ----------------------------------------------------------
    # Upload Limits
    # ----------------------------------------------------------
    MAX_FILE_SIZE_MB: int = 50
    MAX_PAGE_COUNT: int = 500
    ALLOWED_MIME_TYPES: List[str] = ["application/pdf"]

    # ----------------------------------------------------------
    # Rate Limiting
    # ----------------------------------------------------------
    RATE_LIMIT_REQUESTS: int = 100
    RATE_LIMIT_WINDOW: int = 60
    FREE_TIER_DAILY_JOBS: int = 5
    PAID_TIER_DAILY_JOBS: int = 100

    # ----------------------------------------------------------
    # TTS (Text-to-Speech)
    # ----------------------------------------------------------
    TTS_MODEL: str = "tts_models/en/ljspeech/tacotron2-DDC"
    TTS_ENABLED: bool = False   # Enable after installing Coqui TTS

    # ----------------------------------------------------------
    # OAuth (optional)
    # ----------------------------------------------------------
    GOOGLE_CLIENT_ID: Optional[str] = None
    GOOGLE_CLIENT_SECRET: Optional[str] = None
    GITHUB_CLIENT_ID: Optional[str] = None
    GITHUB_CLIENT_SECRET: Optional[str] = None

    # ----------------------------------------------------------
    # Email (optional)
    # ----------------------------------------------------------
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    EMAILS_FROM: str = "noreply@pagetutor.ai"

    # ----------------------------------------------------------
    # Logging
    # ----------------------------------------------------------
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"

    # ----------------------------------------------------------
    # Audit Logging (GDPR)
    # ----------------------------------------------------------
    AUDIT_LOG_RETENTION_DAYS: int = 90
    AUDIT_LOGGING_ENABLED: bool = True

    # ----------------------------------------------------------
    # Admin Bootstrap
    # ----------------------------------------------------------
    FIRST_SUPERUSER_EMAIL: str = "admin@pagetutor.ai"
    FIRST_SUPERUSER_PASSWORD: str = "AdminPass@123!"

    # ----------------------------------------------------------
    # Frontend
    # ----------------------------------------------------------
    FRONTEND_URL: str = "http://localhost:3000"


# Singleton — import this everywhere
settings = Settings()
