"""Glue between InstagramGraphClient's callback interface and
InstagramApiTokenRepo.

Each function opens its own short-lived session rather than sharing one
with the caller's long-running scrape -- same reasoning as
YouTubeKeyProvider/JobProcessor._heartbeat: usage bookkeeping must never
contend with (or be rolled back by) whatever the main scrape transaction
is doing, and an InstagramGraphClient instance outlives any single session
anyway.
"""

from datetime import datetime
from uuid import UUID

from app.core.database import get_session
from app.core.exceptions import NoUsableInstagramTokenError
from app.repositories.instagram_api_token_repo import InstagramApiTokenRepo


async def provide_token() -> tuple[UUID, str, str]:
    async with get_session() as session:
        repo = InstagramApiTokenRepo(session)
        token = await repo.get_usable_token()
        if token is None:
            raise NoUsableInstagramTokenError()
        return token.id, repo.decrypt_token(token), token.ig_user_id


async def record_usage(token_id: UUID, calls: int, buc_pct: float | None) -> None:
    async with get_session() as session:
        await InstagramApiTokenRepo(session).add_usage(token_id, calls, buc_pct)


async def mark_exhausted(token_id: UUID, cooldown_until: datetime) -> None:
    async with get_session() as session:
        await InstagramApiTokenRepo(session).mark_exhausted(token_id, cooldown_until)


async def mark_invalid(token_id: UUID, detail: str) -> None:
    async with get_session() as session:
        await InstagramApiTokenRepo(session).mark_invalid(token_id, detail)
