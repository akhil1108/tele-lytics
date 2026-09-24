"""Async engine/session wiring."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.config import settings


def _engine_kwargs(url: str) -> dict:
    if url.startswith("sqlite"):
        # Make sure the directory for a file-backed SQLite database exists.
        if ":memory:" not in url:
            db_path = url.split("///", 1)[-1]
            parent = Path(db_path).expanduser().resolve().parent
            os.makedirs(parent, exist_ok=True)
            return {"connect_args": {"check_same_thread": False}}
        # In-memory databases need one shared connection or each session sees
        # its own empty database.
        return {"connect_args": {"check_same_thread": False}, "poolclass": StaticPool}
    return {"pool_size": 10, "max_overflow": 20, "pool_pre_ping": True}


engine = create_async_engine(
    settings.database_url,
    echo=False,
    future=True,
    **_engine_kwargs(settings.database_url),
)

SessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding a session that rolls back on error."""
    async with SessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    """Standalone session for workers and scripts."""
    async with SessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def create_all() -> None:
    """Create tables directly. Used by tests and the dev bootstrap only —
    production schema changes go through Alembic."""
    from app.db import models  # noqa: F401  (registers mappers)
    from app.db.base import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
