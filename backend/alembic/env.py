"""
PageTutor AI - Database Migrations (Alembic)
Author: Mustakim Shaikh (https://github.com/MustakimShaikh01)

Usage:
  alembic init migrations
  alembic revision --autogenerate -m "initial schema"
  alembic upgrade head
"""

# alembic/env.py content:

import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config
from alembic import context

# Import all models so Alembic can detect them
from app.db.session import Base
from app.models.models import (  # noqa: F401
    User, Document, PageIndex, Job, JobResult, Billing, AuditLog
)
from app.core.config import settings

config = context.config
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_online() -> None:
    """Run migrations in 'online' mode using async engine."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async def do_run_migrations(connection):
        await connection.run_sync(do_run_sync_migrations)

    def do_run_sync_migrations(connection):
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()

    async def run():
        async with connectable.connect() as connection:
            await do_run_migrations(connection)
        await connectable.dispose()

    asyncio.run(run())


run_migrations_online()
