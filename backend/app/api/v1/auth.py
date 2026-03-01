# ============================================================
# PageTutor AI - Authentication API Routes
# Author: Mustakim Shaikh (https://github.com/MustakimShaikh01)
#
# Endpoints:
#   POST /auth/register     — Create new account
#   POST /auth/login        — Login + set HttpOnly JWT cookies
#   POST /auth/refresh      — Refresh access token
#   POST /auth/logout       — Clear auth cookies
#   GET  /auth/me           — Get current user profile
#   PUT  /auth/me           — Update profile
#   POST /auth/password/change  — Change password
#   POST /auth/password/reset   — Request password reset
#   POST /auth/password/reset/confirm — Confirm reset
#   GET  /auth/oauth/google — Google OAuth redirect
#   GET  /auth/oauth/github — GitHub OAuth redirect
# ============================================================

import uuid
from datetime import datetime, timezone
from typing import Optional
from fastapi import (
    APIRouter, Depends, HTTPException, Request, Response,
    Cookie, status, BackgroundTasks
)
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
import structlog

from app.core.config import settings
from app.core.security import (
    verify_password, get_password_hash,
    create_access_token, create_refresh_token,
    decode_token, set_auth_cookies, clear_auth_cookies,
    get_current_user,
)
from app.db.session import get_db
from app.models.models import User, AuditLog, Billing
from app.schemas.schemas import (
    UserRegisterRequest, UserLoginRequest, TokenResponse,
    UserPublicResponse, UserDetailResponse, UserUpdateRequest,
    PasswordResetRequest, PasswordResetConfirm, ChangePasswordRequest,
    SuccessResponse, ErrorResponse,
)
from app.core.rate_limiter import get_user_quota_status

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication"])


# ----------------------------------------------------------
# Helper: Log audit event
# ----------------------------------------------------------
async def log_audit(
    db: AsyncSession,
    event_type: str,
    category: str,
    request: Request,
    user_id: Optional[str] = None,
    success: bool = True,
    details: Optional[dict] = None,
    error_code: Optional[str] = None,
) -> None:
    """Write an audit log entry to the database."""
    log_entry = AuditLog(
        user_id=user_id,
        event_type=event_type,
        event_category=category,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("User-Agent"),
        request_id=getattr(request.state, "request_id", None),
        details=details or {},
        success=success,
        error_code=error_code,
    )
    db.add(log_entry)
    await db.flush()  # Don't commit yet — caller commits


# ===========================================================
# REGISTER
# ===========================================================
@router.post(
    "/register",
    response_model=UserPublicResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user account",
    response_description="The newly created user profile",
    responses={
        409: {"description": "Email already registered", "model": ErrorResponse},
        422: {"description": "Validation error"},
    },
)
async def register(
    payload: UserRegisterRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    **Register a new PageTutor AI account.**

    - Email must be unique
    - Password must be at least 8 characters with a digit and special char
    - New accounts start on **free tier**
    - Welcome email is queued asynchronously
    """
    # Check for existing account
    result = await db.execute(select(User).where(User.email == payload.email))
    existing = result.scalar_one_or_none()

    if existing:
        await log_audit(
            db, "register_failed", "auth", request,
            success=False,
            details={"email": payload.email},
            error_code="email_already_exists",
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )

    # Create user
    user = User(
        id=str(uuid.uuid4()),
        email=payload.email,
        full_name=payload.full_name,
        hashed_password=get_password_hash(payload.password),
        role="user",
        tier="free",
        is_active=True,
        is_verified=False,  # Email verification pending
    )
    db.add(user)
    await db.flush()  # Get user ID before creating billing

    # Create billing record for the new user
    billing = Billing(
        user_id=user.id,
        plan="free",
        status="active",
    )
    db.add(billing)

    # Audit log: successful registration
    await log_audit(
        db, "user_registered", "auth", request,
        user_id=user.id,
        details={"email": user.email, "full_name": user.full_name},
    )

    await db.commit()
    await db.refresh(user)

    logger.info("user_registered", user_id=user.id, email=user.email)
    return UserPublicResponse.model_validate(user)


# ===========================================================
# LOGIN
# ===========================================================
@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Login and receive JWT tokens",
    response_description="JWT access token + user profile. Token also set in HttpOnly cookie.",
    responses={
        401: {"description": "Invalid credentials", "model": ErrorResponse},
        403: {"description": "Account disabled", "model": ErrorResponse},
    },
)
async def login(
    payload: UserLoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    """
    **Authenticate and receive JWT tokens.**

    Tokens are:
    - Returned in the response body (for API clients)
    - Set as **HttpOnly + Secure cookies** (for browser clients)

    Cookie security: `HttpOnly=True`, `Secure=True`, `SameSite=lax`

    Access token expires in **{settings.ACCESS_TOKEN_EXPIRE_MINUTES} minutes**.
    Refresh token expires in **{settings.REFRESH_TOKEN_EXPIRE_DAYS} days**.
    """
    # Look up user
    result = await db.execute(select(User).where(User.email == payload.email))
    user = result.scalar_one_or_none()

    if not user or not verify_password(payload.password, user.hashed_password or ""):
        await log_audit(
            db, "login_failed", "auth", request,
            details={"email": payload.email},
            success=False,
            error_code="invalid_credentials",
        )
        # Generic error to prevent user enumeration
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account disabled. Please contact support.",
        )

    # Generate tokens
    access_token = create_access_token(
        subject=user.email,
        user_id=user.id,
        role=user.role,
    )
    refresh_token = create_refresh_token(
        subject=user.email,
        user_id=user.id,
    )

    # Set HttpOnly cookies (primary auth mechanism for browsers)
    set_auth_cookies(response, access_token, refresh_token)

    # Update last login timestamp
    user.last_login_at = datetime.now(timezone.utc)

    # Audit log
    await log_audit(
        db, "login_success", "auth", request,
        user_id=user.id,
        details={"email": user.email},
    )

    await db.commit()

    logger.info("user_logged_in", user_id=user.id, email=user.email)

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=UserPublicResponse.model_validate(user),
    )


# ===========================================================
# REFRESH TOKEN
# ===========================================================
@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Refresh the access token",
    response_description="New access token",
)
async def refresh_token(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
    refresh_token_cookie: Optional[str] = Cookie(None, alias="refresh_token"),
):
    """
    **Exchange a refresh token for a new access token.**

    Refresh token is read from the HttpOnly cookie automatically.
    A new access token is returned and the cookie is updated.
    """
    token = refresh_token_cookie

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token not found. Please login again.",
        )

    payload = decode_token(token)

    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type.",
        )

    user_id = payload.get("uid")
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or account disabled.",
        )

    # Issue new access token
    new_access_token = create_access_token(
        subject=user.email,
        user_id=user.id,
        role=user.role,
    )
    new_refresh_token = create_refresh_token(
        subject=user.email,
        user_id=user.id,
    )

    set_auth_cookies(response, new_access_token, new_refresh_token)

    return TokenResponse(
        access_token=new_access_token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=UserPublicResponse.model_validate(user),
    )


# ===========================================================
# LOGOUT
# ===========================================================
@router.post(
    "/logout",
    response_model=SuccessResponse,
    summary="Logout and clear auth cookies",
)
async def logout(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    **Logout the current user.**

    - Clears the `access_token` and `refresh_token` HttpOnly cookies
    - Logs the logout event in the audit trail
    """
    clear_auth_cookies(response)

    await log_audit(
        db, "logout", "auth", request,
        user_id=current_user.id,
    )
    await db.commit()

    logger.info("user_logged_out", user_id=current_user.id)
    return SuccessResponse(message="Logged out successfully.")


# ===========================================================
# GET CURRENT USER (/me)
# ===========================================================
@router.get(
    "/me",
    response_model=UserDetailResponse,
    summary="Get current user profile",
    response_description="Authenticated user profile with quota info",
)
async def get_me(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    **Get the currently authenticated user's profile.**

    Returns:
    - User info
    - Daily job quota status
    - Subscription tier
    """
    quota = await get_user_quota_status(current_user.id, current_user.tier)

    user_data = UserDetailResponse.model_validate(current_user)
    user_data.quota = quota
    return user_data


# ===========================================================
# UPDATE PROFILE
# ===========================================================
@router.put(
    "/me",
    response_model=UserPublicResponse,
    summary="Update current user profile",
)
async def update_profile(
    payload: UserUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """**Update the current user's profile fields (name, avatar).**"""
    if payload.full_name:
        current_user.full_name = payload.full_name
    if payload.avatar_url is not None:
        current_user.avatar_url = payload.avatar_url

    await db.commit()
    await db.refresh(current_user)
    return UserPublicResponse.model_validate(current_user)


# ===========================================================
# CHANGE PASSWORD
# ===========================================================
@router.post(
    "/password/change",
    response_model=SuccessResponse,
    summary="Change account password",
)
async def change_password(
    payload: ChangePasswordRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """**Change the current user's password.**"""
    if not verify_password(payload.current_password, current_user.hashed_password or ""):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect.",
        )

    current_user.hashed_password = get_password_hash(payload.new_password)

    await log_audit(
        db, "password_changed", "auth", request,
        user_id=current_user.id,
    )
    await db.commit()

    return SuccessResponse(message="Password changed successfully.")


# ===========================================================
# PASSWORD RESET
# ===========================================================
@router.post(
    "/password/reset",
    response_model=SuccessResponse,
    summary="Request a password reset email",
)
async def request_password_reset(
    payload: PasswordResetRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    **Request a password reset link via email.**

    Always returns success (even if email doesn't exist)
    to prevent user enumeration attacks.
    """
    # Always return success — email will be sent if account exists
    # This prevents email enumeration
    logger.info("password_reset_requested", email=payload.email)
    return SuccessResponse(
        message="If this email is registered, you will receive a reset link shortly."
    )
