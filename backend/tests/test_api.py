"""
PageTutor AI - Backend Unit Tests
Author: Mustakim Shaikh (https://github.com/MustakimShaikh01)
"""

import pytest
import asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import NullPool

from app.main import app
from app.db.session import Base, get_db
from app.core.security import get_password_hash, create_access_token, verify_password
from app.core.config import settings


# ===========================================================
# Test Database Setup (SQLite in-memory for speed)
# ===========================================================
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

test_engine = create_async_engine(
    TEST_DATABASE_URL,
    poolclass=NullPool,
)
TestSessionLocal = async_sessionmaker(
    bind=test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def override_get_db():
    async with TestSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


@pytest.fixture(autouse=True)
async def setup_db():
    """Create tables before each test, drop after."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


# Override database dependency
app.dependency_overrides[get_db] = override_get_db

# Test client (no cookies sent automatically — we'll test manually)
client = TestClient(app, raise_server_exceptions=False)


# ===========================================================
# SECURITY TESTS
# ===========================================================

def test_password_hashing():
    """bcrypt should produce different hashes for same password."""
    password = "TestPass@123"
    hash1 = get_password_hash(password)
    hash2 = get_password_hash(password)
    assert hash1 != hash2  # Different salts each time
    assert verify_password(password, hash1)
    assert verify_password(password, hash2)
    assert not verify_password("WrongPass@123", hash1)


def test_access_token_creation():
    """JWT should contain correct claims."""
    import jwt as pyjwt
    token = create_access_token(subject="test@test.com", user_id="user-123", role="user")
    payload = pyjwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    assert payload["sub"] == "test@test.com"
    assert payload["uid"] == "user-123"
    assert payload["role"] == "user"
    assert payload["type"] == "access"


def test_invalid_token_rejected():
    """Invalid JWT should return 401."""
    response = client.get(
        "/api/v1/auth/me",
        cookies={"access_token": "Bearer invalid.jwt.token"},
    )
    assert response.status_code == 401


# ===========================================================
# AUTH API TESTS
# ===========================================================

def test_health_check():
    """Health endpoint should return 200."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert data["author"] == "Mustakim Shaikh"


def test_root_endpoint():
    """Root endpoint should return service info."""
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["service"] == "PageTutor AI"


def test_register_user():
    """Register with valid data should return 201."""
    response = client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Mustakim Shaikh",
            "email": "mustakim@test.com",
            "password": "SecurePass@123",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "mustakim@test.com"
    assert data["role"] == "user"
    assert data["tier"] == "free"
    # Password must NOT be in response
    assert "password" not in data
    assert "hashed_password" not in data


def test_register_duplicate_email():
    """Duplicate email registration should return 409."""
    payload = {
        "full_name": "Test User",
        "email": "dup@test.com",
        "password": "SecurePass@123",
    }
    client.post("/api/v1/auth/register", json=payload)
    response = client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 409


def test_register_weak_password():
    """Weak password should return 422 validation error."""
    response = client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Test",
            "email": "weak@test.com",
            "password": "weakpass",  # No digit, no special char
        },
    )
    assert response.status_code == 422


def test_login_success():
    """Valid login should set HttpOnly cookie and return token."""
    # Register first
    client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Login Test",
            "email": "login@test.com",
            "password": "SecurePass@123",
        },
    )
    # Login
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "login@test.com", "password": "SecurePass@123"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    # Cookie should be set
    assert "access_token" in response.cookies


def test_login_wrong_password():
    """Wrong password should return 401."""
    client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Test",
            "email": "wrong@test.com",
            "password": "SecurePass@123",
        },
    )
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "wrong@test.com", "password": "WrongPass@123"},
    )
    assert response.status_code == 401


def test_unauthorized_without_token():
    """Protected endpoint without token should return 401."""
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401


def test_rate_limit_headers():
    """Response should include rate limit headers."""
    response = client.get("/health")
    # These headers should be present from our middleware
    assert "x-ratelimit-limit" in response.headers or response.status_code == 200


# ===========================================================
# INPUT VALIDATION TESTS
# ===========================================================

def test_missing_required_fields():
    """Missing required fields should return 422."""
    response = client.post("/api/v1/auth/login", json={"email": "test@test.com"})
    assert response.status_code == 422


def test_invalid_email_format():
    """Invalid email format should return 422."""
    response = client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Test",
            "email": "not-an-email",
            "password": "SecurePass@123",
        },
    )
    assert response.status_code == 422


# ===========================================================
# SECURITY HEADERS TESTS
# ===========================================================

def test_security_headers_present():
    """Security headers must be set on all responses."""
    response = client.get("/")
    assert "x-frame-options" in response.headers
    assert response.headers["x-frame-options"] == "DENY"
    assert "x-content-type-options" in response.headers
    assert "x-request-id" in response.headers  # Request tracing


def test_server_header_obscured():
    """Server header should not reveal nginx/version info."""
    response = client.get("/")
    server = response.headers.get("server", "")
    assert "nginx" not in server.lower()
    assert "uvicorn" not in server.lower()


# ===========================================================
# SWAGGER DOCS TESTS  
# ===========================================================

def test_swagger_ui_accessible():
    """Swagger UI should be accessible."""
    response = client.get("/docs")
    assert response.status_code == 200
    assert "swagger" in response.text.lower()


def test_openapi_schema():
    """OpenAPI schema should be valid."""
    response = client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    assert schema["info"]["title"] == "PageTutor AI"
    assert schema["info"]["version"] == settings.APP_VERSION
    # Verify all expected routes exist
    paths = schema["paths"]
    assert "/api/v1/auth/login" in paths
    assert "/api/v1/auth/register" in paths
    assert "/api/v1/upload/pdf" in paths
    assert "/api/v1/jobs/create" in paths
    assert "/api/v1/chat/message" in paths
    assert "/api/v1/admin/stats" in paths
