from __future__ import annotations
"""
Separate async engine/session-factory for the SQL query console
(POST /admin/query) -- deliberately never shares a pool with the writable
engine in app/core/database.py. Bound to settings.DATABASE_URL_READONLY,
which points at a Postgres role with SELECT-only grants (see
infra/user_data.sh). The forced rollback in get_readonly_session() is extra
insurance on top of that role's own lack of write grants -- defense in
depth, not either/or.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings

_ro_engine = None
_ro_session_factory: async_sessionmaker[AsyncSession] | None = None


def _get_readonly_engine():
    global _ro_engine
    if _ro_engine is None:
        if not settings.DATABASE_URL_READONLY:
            raise RuntimeError("DATABASE_URL_READONLY is not configured")
        _ro_engine = create_async_engine(
            settings.DATABASE_URL_READONLY,
            echo=settings.DEBUG,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=5,
            pool_recycle=3600,
        )
    return _ro_engine


def _get_readonly_session_factory() -> async_sessionmaker[AsyncSession]:
    global _ro_session_factory
    if _ro_session_factory is None:
        _ro_session_factory = async_sessionmaker(
            bind=_get_readonly_engine(),
            expire_on_commit=False,
            class_=AsyncSession,
        )
    return _ro_session_factory


@asynccontextmanager
async def get_readonly_session() -> AsyncGenerator[AsyncSession, None]:
    """Always rolls back, never commits -- even for SELECT. Extra insurance
    on top of the DB role's own lack of write grants."""
    session_factory = _get_readonly_session_factory()
    async with session_factory() as session:
        try:
            yield session
        finally:
            await session.rollback()


async def close_readonly_db() -> None:
    global _ro_engine, _ro_session_factory
    if _ro_engine is not None:
        await _ro_engine.dispose()
        _ro_engine = None
        _ro_session_factory = None
