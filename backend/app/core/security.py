# ============================================================
# PageTutor AI - Security & Authentication Core
# Author: Mustakim Shaikh (https://github.com/MustakimShaikh01)
#
# Handles:
#   - JWT token creation (access + refresh)
#   - JWT cookie storage (HttpOnly, Secure, SameSite)
#   - Password hashing with bcrypt
#   - OAuth2 bearer scheme
#   - Current user extraction from cookies
# ============================================================

from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple
import uuid

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_db

# ----------------------------------------------------------
# Password Hashing
# ----------------------------------------------------------
# bcrypt with 12 rounds — strong, industry-standard
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# OAuth2 scheme — also supports Bearer tokens in Authorization header
oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_V1_PREFIX}/auth/login",
    auto_error=False,  # We'll check cookie first
)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Compare plaintext password against bcrypt hash."""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Hash a plaintext password using bcrypt."""
    return pwd_context.hash(password)


# ----------------------------------------------------------
# JWT Token Factory
# ----------------------------------------------------------

def create_access_token(
    subject: str,
    user_id: str,
    role: str = "user",
    expires_delta: Optional[timedelta] = None,
) -> str:
    """
    Create a short-lived JWT access token.

    Payload includes:
    - sub: user email (subject)
    - uid: user UUID
    - role: user | admin
    - type: access
    - jti: unique token ID (for revocation)
    - iat / exp: timestamps
    """
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    payload = {
        "sub": subject,
        "uid": user_id,
        "role": role,
        "type": "access",
        "jti": str(uuid.uuid4()),  # Unique ID for token revocation
        "iat": datetime.now(timezone.utc),
        "exp": expire,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_refresh_token(
    subject: str,
    user_id: str,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """
    Create a long-lived JWT refresh token.
    Used to obtain new access tokens without re-login.
    """
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    )
    payload = {
        "sub": subject,
        "uid": user_id,
        "type": "refresh",
        "jti": str(uuid.uuid4()),
        "iat": datetime.now(timezone.utc),
        "exp": expire,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_token(token: str) -> dict:
    """
    Decode and validate a JWT token.
    Raises HTTPException on invalid / expired tokens.
    """
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
        )
        return payload
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid or expired token: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )


# ----------------------------------------------------------
# Cookie Helpers
# ----------------------------------------------------------

def set_auth_cookies(response, access_token: str, refresh_token: str) -> None:
    """
    Store JWT tokens in HttpOnly cookies.

    Security properties:
    - HttpOnly: prevents JavaScript XSS access
    - Secure: HTTPS only in production
    - SameSite=lax: CSRF protection
    """
    # Access token cookie (short-lived)
    response.set_cookie(
        key="access_token",
        value=f"Bearer {access_token}",
        httponly=settings.COOKIE_HTTPONLY,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        path="/",
    )
    # Refresh token cookie (long-lived)
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=settings.COOKIE_HTTPONLY,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        path=f"{settings.API_V1_PREFIX}/auth/refresh",  # Restrict path
    )


def clear_auth_cookies(response) -> None:
    """Clear both auth cookies on logout."""
    response.delete_cookie("access_token", path="/")
    response.delete_cookie(
        "refresh_token",
        path=f"{settings.API_V1_PREFIX}/auth/refresh",
    )


# ----------------------------------------------------------
# Dependency — Extract Current User
# ----------------------------------------------------------

async def get_current_user_token(request: Request) -> str:
    """
    Extract JWT token from:
    1. HttpOnly cookie (preferred)
    2. Authorization: Bearer header (fallback for API clients)
    """
    # 1. Check HttpOnly cookie first
    cookie_token = request.cookies.get("access_token")
    if cookie_token:
        # Cookie value is stored as "Bearer <token>"
        if cookie_token.startswith("Bearer "):
            return cookie_token[7:]

    # 2. Fallback to Authorization header
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        return auth_header[7:]

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated. Please login.",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_current_user(
    token: str = Depends(get_current_user_token),
    db: AsyncSession = Depends(get_db),
):
    """
    FastAPI dependency: returns currently authenticated user.
    Validates token type = 'access'.
    """
    from app.models.models import User
    from sqlalchemy import select

    payload = decode_token(token)

    # Ensure this is an access token, not a refresh token
    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type. Please use access token.",
        )

    user_id: str = payload.get("uid")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token payload missing user ID.",
        )

    # Fetch user from DB
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found.",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is disabled. Contact support.",
        )

    return user


async def get_current_admin_user(
    current_user=Depends(get_current_user),
):
    """
    Dependency: validates the user has admin role.
    Use on admin-only routes.
    """
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required.",
        )
    return current_user
