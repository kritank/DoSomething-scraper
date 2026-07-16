"""Glue between YouTubeClient's callback interface and YouTubeApiKeyRepo.

Each function opens its own short-lived session rather than sharing one
with the caller's long-running scrape -- same reasoning as
JobProcessor._heartbeat: quota bookkeeping must never contend with (or be
rolled back by) whatever the main scrape transaction is doing, and a
YouTubeClient instance outlives any single session anyway.
"""

from uuid import UUID

from app.core.database import get_session
from app.core.exceptions import NoUsableYouTubeKeyError
from app.repositories.youtube_api_key_repo import YouTubeApiKeyRepo


async def provide_key() -> tuple[UUID, str]:
    async with get_session() as session:
        repo = YouTubeApiKeyRepo(session)
        key = await repo.get_usable_key()
        if key is None:
            raise NoUsableYouTubeKeyError()
        return key.id, repo.decrypt_key(key)


async def record_usage(key_id: UUID, units: int) -> None:
    async with get_session() as session:
        await YouTubeApiKeyRepo(session).add_usage(key_id, units)


async def mark_exhausted(key_id: UUID) -> None:
    async with get_session() as session:
        await YouTubeApiKeyRepo(session).mark_exhausted(key_id)


async def mark_invalid(key_id: UUID, detail: str) -> None:
    async with get_session() as session:
        await YouTubeApiKeyRepo(session).mark_invalid(key_id, detail)
