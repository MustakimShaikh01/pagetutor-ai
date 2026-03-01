# ============================================================
# PageTutor AI - Pydantic Schemas (Request/Response Models)
# Author: Mustakim Shaikh (https://github.com/MustakimShaikh01)
#
# Used for:
#   - API request validation
#   - API response serialization
#   - Swagger UI documentation (via Field descriptions)
# ============================================================

from pydantic import BaseModel, EmailStr, Field, validator, HttpUrl
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


# ===========================================================
# ENUMS
# ===========================================================
class UserRole(str, Enum):
    user = "user"
    admin = "admin"
    moderator = "moderator"


class UserTier(str, Enum):
    free = "free"
    basic = "basic"
    pro = "pro"
    enterprise = "enterprise"


class JobType(str, Enum):
    full_pipeline = "full_pipeline"
    summarize = "summarize"
    segment = "segment"
    ppt = "ppt"
    tts = "tts"
    video = "video"
    flashcards = "flashcards"
    quiz = "quiz"
    chat = "chat"


class JobStatus(str, Enum):
    pending = "pending"
    queued = "queued"
    processing = "processing"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class JobPriority(str, Enum):
    high = "high"
    normal = "normal"
    low = "low"


class SupportedLanguage(str, Enum):
    en = "en"
    hi = "hi"
    fr = "fr"
    de = "de"
    es = "es"
    pt = "pt"
    zh = "zh"
    ar = "ar"
    ja = "ja"
    ko = "ko"


# ===========================================================
# AUTH SCHEMAS
# ===========================================================

class UserRegisterRequest(BaseModel):
    """Schema for new user registration."""
    full_name: str = Field(
        ..., min_length=2, max_length=255,
        description="Full name of the user",
        example="Mustakim Shaikh"
    )
    email: EmailStr = Field(
        ..., description="Valid email address",
        example="mustakim@pagetutor.ai"
    )
    password: str = Field(
        ..., min_length=8, max_length=128,
        description="Password (min 8 chars)",
        example="MyPassword123"
    )

    @validator("password")
    def password_strength(cls, v):
        """
        Enforce password complexity.

        Local dev mode: only minimum 8 characters required.
        Production: set STRICT_PASSWORD_VALIDATION=true in .env to enforce
        digit + special character requirements.
        """
        import os
        strict = os.getenv("STRICT_PASSWORD_VALIDATION", "false").lower() == "true"

        if strict:
            if not any(c.isdigit() for c in v):
                raise ValueError("Password must contain at least one digit (0-9)")
            if not any(c in "!@#$%^&*()_+-=[]{}|;':\",./<>?" for c in v):
                raise ValueError(
                    "Password must contain at least one special character "
                    "(!@#$%^&*()_+-=[]{}|;':\",./<>?)"
                )
        return v

    class Config:
        json_schema_extra = {
            "example": {
                "full_name": "Mustakim Shaikh",
                "email": "mustakim@pagetutor.ai",
                "password": "MyPassword123"
            }
        }


class UserLoginRequest(BaseModel):
    """Schema for user login."""
    email: EmailStr = Field(
        ..., description="Registered email address",
        example="mustakim@pagetutor.ai"
    )
    password: str = Field(
        ..., description="Account password",
        example="SecurePass@123"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "email": "mustakim@pagetutor.ai",
                "password": "SecurePass@123"
            }
        }


class TokenResponse(BaseModel):
    """Response returned after successful login."""
    access_token: str = Field(
        ..., description="JWT access token (also set in HttpOnly cookie)"
    )
    token_type: str = Field(default="bearer", description="Token type")
    expires_in: int = Field(
        ..., description="Access token expiry in seconds"
    )
    user: "UserPublicResponse" = Field(..., description="Authenticated user info")
    message: str = Field(
        default="Login successful. Token stored in HttpOnly cookie."
    )


class RefreshTokenRequest(BaseModel):
    """Request to refresh access token."""
    refresh_token: Optional[str] = Field(
        None,
        description="Optional refresh token (read from cookie automatically if not provided)"
    )


class PasswordResetRequest(BaseModel):
    email: EmailStr = Field(..., description="Email to send password reset link")


class PasswordResetConfirm(BaseModel):
    token: str = Field(..., description="Reset token from email")
    new_password: str = Field(..., min_length=8, description="New password")


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(..., description="Current password")
    new_password: str = Field(..., min_length=8, description="New password")


# ===========================================================
# USER SCHEMAS
# ===========================================================

class UserPublicResponse(BaseModel):
    """Public-facing user data (safe to expose in API)."""
    id: str
    email: EmailStr
    full_name: str
    avatar_url: Optional[str] = None
    role: UserRole
    tier: UserTier
    is_verified: bool
    created_at: datetime

    class Config:
        from_attributes = True


class UserDetailResponse(UserPublicResponse):
    """Extended user info for authenticated /me endpoint."""
    is_active: bool
    oauth_provider: Optional[str] = None
    last_login_at: Optional[datetime] = None
    quota: Optional[dict] = None  # Daily job quota status


class UserUpdateRequest(BaseModel):
    """Updatable user fields."""
    full_name: Optional[str] = Field(None, min_length=2, max_length=255)
    avatar_url: Optional[str] = None


class UserAdminUpdateRequest(BaseModel):
    """Admin-only user update fields."""
    role: Optional[UserRole] = None
    tier: Optional[UserTier] = None
    is_active: Optional[bool] = None
    is_verified: Optional[bool] = None


# ===========================================================
# DOCUMENT SCHEMAS
# ===========================================================

class DocumentUploadResponse(BaseModel):
    """Response after PDF upload."""
    document_id: str = Field(..., description="Unique document identifier")
    filename: str = Field(..., description="Original filename")
    page_count: int = Field(..., description="Number of pages detected")
    file_size_bytes: int = Field(..., description="File size in bytes")
    sha256_hash: str = Field(..., description="File SHA-256 hash for deduplication")
    is_duplicate: bool = Field(..., description="True if identical PDF was previously uploaded")
    expires_at: Optional[datetime] = Field(
        None, description="When the raw PDF will be deleted from storage"
    )
    status: str = Field(default="uploaded")
    message: str = Field(default="PDF uploaded successfully. Ready for processing.")

    class Config:
        from_attributes = True


class DocumentListResponse(BaseModel):
    """Paginated list of user documents."""
    documents: List["DocumentSummary"]
    total: int
    page: int
    page_size: int


class DocumentSummary(BaseModel):
    id: str
    original_filename: str
    page_count: int
    file_size_bytes: int
    status: str
    is_indexed: bool
    created_at: datetime
    language: str

    class Config:
        from_attributes = True


# ===========================================================
# JOB SCHEMAS
# ===========================================================

class JobCreateRequest(BaseModel):
    """Create a new processing job."""
    document_id: str = Field(
        ..., description="Document to process",
        example="550e8400-e29b-41d4-a716-446655440000"
    )
    job_type: JobType = Field(
        default=JobType.full_pipeline,
        description="Type of processing to run"
    )
    language: SupportedLanguage = Field(
        default=SupportedLanguage.en,
        description="Language for TTS narration"
    )
    config: Optional[Dict[str, Any]] = Field(
        None,
        description="Optional job-specific configuration",
        example={"include_quiz": True, "quiz_question_count": 10}
    )

    class Config:
        json_schema_extra = {
            "example": {
                "document_id": "550e8400-e29b-41d4-a716-446655440000",
                "job_type": "full_pipeline",
                "language": "en",
                "config": {"include_quiz": True, "quiz_question_count": 10}
            }
        }


class JobStatusResponse(BaseModel):
    """Current status of a processing job."""
    job_id: str
    job_type: str
    status: JobStatus
    progress: int = Field(..., ge=0, le=100, description="Progress percentage 0-100")
    error_message: Optional[str] = None
    tokens_used: int
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    estimated_remaining_seconds: Optional[int] = None

    class Config:
        from_attributes = True


class JobResultResponse(BaseModel):
    """Completed job outputs."""
    job_id: str
    document_id: str
    summary: Optional[str] = Field(None, description="Full document summary")
    learning_points: Optional[List[str]] = Field(None, description="Key learning points")
    segments: Optional[List[Dict]] = Field(None, description="Topic segments")
    ppt_url: Optional[str] = Field(None, description="Pre-signed URL to download PPT")
    audio_url: Optional[str] = Field(None, description="Pre-signed URL to download audio")
    video_url: Optional[str] = Field(None, description="Pre-signed URL to download video")
    flashcards: Optional[List[Dict]] = Field(None, description="Flashcard Q&A pairs")
    quiz: Optional[List[Dict]] = Field(None, description="Quiz questions with options")


# ===========================================================
# CHAT SCHEMAS
# ===========================================================

class ChatMessageRequest(BaseModel):
    """Send a message in PDF chat mode."""
    document_id: str = Field(..., description="Document to chat about")
    message: str = Field(
        ..., min_length=1, max_length=2000,
        description="User's question",
        example="What is the main concept explained on page 5?"
    )
    session_id: Optional[str] = Field(
        None, description="Existing chat session ID (omit for new session)"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "document_id": "550e8400-e29b-41d4-a716-446655440000",
                "message": "What is the main concept explained on page 5?",
                "session_id": None
            }
        }


class ChatMessageResponse(BaseModel):
    """AI response in chat mode."""
    session_id: str
    message: str = Field(..., description="AI response")
    sources: List[Dict] = Field(
        default=[], description="Source pages used for the answer"
    )
    tokens_used: int
    response_time_ms: int


# ===========================================================
# QUIZ / FLASHCARD SCHEMAS
# ===========================================================

class FlashcardResponse(BaseModel):
    """Single flashcard."""
    card_id: int
    front: str = Field(..., description="Question or term")
    back: str = Field(..., description="Answer or definition")
    page_reference: Optional[int] = None
    topic: Optional[str] = None


class QuizQuestionResponse(BaseModel):
    """Single quiz question."""
    question_id: int
    question: str
    question_type: str = Field(..., description="mcq | true_false | fill_blank")
    options: Optional[List[str]] = Field(None, description="Options for MCQ")
    correct_answer: str
    explanation: Optional[str] = None
    page_reference: Optional[int] = None


class QuizSubmitRequest(BaseModel):
    """Quiz answers submission."""
    job_id: str
    answers: Dict[int, str] = Field(
        ..., description="Map of question_id to user's answer"
    )


class QuizResultResponse(BaseModel):
    """Quiz result after submission."""
    score: float = Field(..., description="Score as percentage (0-100)")
    total_questions: int
    correct_answers: int
    wrong_answers: int
    per_question_feedback: List[Dict]


# ===========================================================
# ADMIN SCHEMAS
# ===========================================================

class SystemStatsResponse(BaseModel):
    """Admin dashboard system statistics."""
    total_users: int
    active_users_24h: int
    total_documents: int
    total_jobs: int
    pending_jobs: int
    processing_jobs: int
    failed_jobs_24h: int
    storage_used_gb: float
    gpu_utilization_percent: Optional[float] = None
    queue_depth: int


# ===========================================================
# COMMON SCHEMAS
# ===========================================================

class SuccessResponse(BaseModel):
    """Generic success response."""
    success: bool = True
    message: str


class ErrorResponse(BaseModel):
    """Standard error response format."""
    success: bool = False
    error: str
    detail: Optional[str] = None
    request_id: Optional[str] = None


class PaginatedResponse(BaseModel):
    """Generic paginated response wrapper."""
    items: List[Any]
    total: int
    page: int
    page_size: int
    has_next: bool
    has_prev: bool


class HealthCheckResponse(BaseModel):
    """System health check response."""
    status: str = Field(..., description="healthy | degraded | unhealthy")
    version: str
    environment: str
    services: Dict[str, bool] = Field(..., description="Status of each service")
    uptime_seconds: float
