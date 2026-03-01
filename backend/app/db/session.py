# ============================================================
# PageTutor AI - Async Database Session
# Author: Mustakim Shaikh (https://github.com/MustakimShaikh01)
#
# Uses SQLite for local development (no Docker needed)
# Uses PostgreSQL in production (set DATABASE_URL env var)
#
# SQLite note: aiosqlite driver is used for async support
# ============================================================

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    create_async_engine,
    async_sessionmaker,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import StaticPool
import structlog

from app.core.config import settings

logger = structlog.get_logger(__name__)


# ----------------------------------------------------------
# Declarative Base — all ORM models extend this
# ----------------------------------------------------------
class Base(DeclarativeBase):
    pass


# ----------------------------------------------------------
# Engine Configuration
# ----------------------------------------------------------
def _get_engine_kwargs():
    """
    Return engine kwargs based on database backend.
    SQLite requires StaticPool for async + check_same_thread=False.
    """
    url = settings.DATABASE_URL

    if url.startswith("sqlite"):
        return {
            "connect_args": {"check_same_thread": False},
            "poolclass": StaticPool,  # Required for SQLite async
            "echo": settings.DEBUG,
        }
    else:
        # PostgreSQL / production settings
        return {
            "pool_size": 20,
            "max_overflow": 40,
            "pool_recycle": 3600,
            "pool_pre_ping": True,
            "echo": False,
        }


# Create async engine
engine = create_async_engine(
    settings.DATABASE_URL,
    **_get_engine_kwargs(),
)

# Session factory
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


# ----------------------------------------------------------
# FastAPI Dependency: Get DB Session
# ----------------------------------------------------------
async def get_db() -> AsyncSession:
    """
    Provide an async DB session for FastAPI dependency injection.
    Automatically handles commit, rollback, and close.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# ----------------------------------------------------------
# Health Check
# ----------------------------------------------------------
async def check_db_health() -> bool:
    """Verify database connectivity."""
    try:
        from sqlalchemy import text
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.error("db_health_check_failed", error=str(e))
        return False


# ----------------------------------------------------------
# Create all tables (development shortcut)
# ----------------------------------------------------------
async def create_all_tables():
    """Create all database tables (dev only — use Alembic in production)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("database_tables_created", dialect=engine.dialect.name)
