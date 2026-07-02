from __future__ import annotations
"""
Async SQLAlchemy 2.x engine, session factory, and FastAPI dependency.

Uses asyncpg driver. All ORM models inherit from Base defined here.
Alembic imports Base.metadata to autogenerate migrations.

Usage (FastAPI route):
    @router.get("/example")
    async def example(db: AsyncSession = Depends(get_db)):
        result = await db.execute(select(MyModel))
        ...

Usage (background job — no DI container):
    async with get_session() as session:
        result = await session.execute(...)
        await session.commit()
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings


# ─────────────────────────────────────────────────────────────────────────────
# Declarative base — all ORM models inherit from this
# ─────────────────────────────────────────────────────────────────────────────

class Base(DeclarativeBase):
    pass


# ─────────────────────────────────────────────────────────────────────────────
# Engine & session factory — lazy-initialised on first call to init_db()
# ─────────────────────────────────────────────────────────────────────────────

_engine = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _get_engine():
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            settings.DATABASE_URL,
            echo=settings.DEBUG,          # SQL logging in debug mode only
            pool_pre_ping=True,           # validate connections before use
            pool_size=10,
            max_overflow=20,
            pool_recycle=3600,            # recycle connections after 1 hour
        )
    return _engine


def _get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            bind=_get_engine(),
            expire_on_commit=False,       # avoid lazy-load errors post-commit
            class_=AsyncSession,
        )
    return _session_factory


# ─────────────────────────────────────────────────────────────────────────────
# Lifecycle hooks — called from FastAPI lifespan
# ─────────────────────────────────────────────────────────────────────────────

async def init_db() -> None:
    """Initialise the engine and session factory on startup."""
    _get_engine()
    _get_session_factory()


async def close_db() -> None:
    """Dispose the engine connection pool on shutdown."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None


# ─────────────────────────────────────────────────────────────────────────────
# FastAPI dependency
# ─────────────────────────────────────────────────────────────────────────────

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency that yields an async session per request.

    Commits on success, rolls back on any exception.
    """
    session_factory = _get_session_factory()
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# ─────────────────────────────────────────────────────────────────────────────
# Context manager — for background jobs (no DI container)
# ─────────────────────────────────────────────────────────────────────────────

@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Async context manager for use in background jobs, workers, and scripts.

    Example:
        async with get_session() as session:
            await session.execute(...)
            await session.commit()
    """
    session_factory = _get_session_factory()
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
