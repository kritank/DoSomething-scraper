from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func

from app.core.config import settings
from app.core.crypto import decrypt_json, encrypt_json
from app.core.exceptions import YouTubeApiKeyNotFoundError
from app.core.logging import get_logger
from app.models.youtube_api_key import YouTubeApiKey
from app.scraper.youtube_client import next_midnight_pacific

logger = get_logger(__name__)


class YouTubeApiKeyRepo:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def _get_by_label(self, label: str) -> Optional[YouTubeApiKey]:
        result = await self.session.execute(
            select(YouTubeApiKey).where(YouTubeApiKey.label == label)
        )
        return result.scalar_one_or_none()

    async def get_all(self) -> list[YouTubeApiKey]:
        result = await self.session.execute(
            select(YouTubeApiKey).order_by(YouTubeApiKey.label)
        )
        return list(result.scalars().all())

    async def get_by_id(self, key_id: UUID) -> YouTubeApiKey:
        key = await self.session.get(YouTubeApiKey, key_id)
        if key is None:
            raise YouTubeApiKeyNotFoundError(str(key_id))
        return key

    async def create(self, label: str, api_key: str) -> YouTubeApiKey:
        """Register (or re-register) a key. Upserts by label, same pattern
        as InstagramAccountRepo.create -- rotating a key's raw value
        shouldn't require deleting and re-adding the row."""
        key = await self._get_by_label(label)
        if key is None:
            key = YouTubeApiKey(label=label)
            self.session.add(key)

        key.api_key_encrypted = encrypt_json({"key": api_key})
        key.status = "active"
        key.error_message = None
        key.failure_count = 0
        key.quota_used_today = 0
        key.quota_reset_at = None
        await self.session.commit()
        return key

    def decrypt_key(self, key: YouTubeApiKey) -> str:
        return decrypt_json(key.api_key_encrypted)["key"]

    async def _reset_if_due(self, key: YouTubeApiKey) -> None:
        if key.quota_reset_at is not None and key.quota_reset_at <= datetime.now(timezone.utc):
            key.quota_used_today = 0
            key.quota_reset_at = None
            if key.status == "quota_exhausted":
                key.status = "active"

    async def get_usable_key(self) -> Optional[YouTubeApiKey]:
        """Picks the active key with the most quota headroom.

        Unlike InstagramAccountRepo.acquire_healthy_account, this doesn't
        lease/lock the row -- a plain API key is safely shareable across
        concurrent jobs, so there's nothing to release afterwards. Callers
        just record usage via add_usage() as requests happen.
        """
        result = await self.session.execute(
            select(YouTubeApiKey).where(
                YouTubeApiKey.status.in_(("active", "quota_exhausted"))
            )
        )
        candidates = list(result.scalars().all())
        if not candidates:
            return None

        dirty = False
        for key in candidates:
            before = (key.status, key.quota_used_today)
            await self._reset_if_due(key)
            if (key.status, key.quota_used_today) != before:
                dirty = True
        if dirty:
            await self.session.commit()

        usable = [
            key
            for key in candidates
            if key.status == "active"
            and key.quota_used_today < settings.YOUTUBE_DAILY_QUOTA_PER_KEY - settings.YOUTUBE_QUOTA_SOFT_STOP
        ]
        if not usable:
            return None
        return min(usable, key=lambda k: k.quota_used_today)

    async def add_usage(self, key_id: UUID, units: int) -> None:
        """Atomic increment (not read-modify-write) -- safe under the
        concurrent requests a single job (or several jobs sharing this
        key) can issue at once.

        Also stamps quota_reset_at for a key that doesn't have one yet --
        previously that field was ONLY ever set by mark_exhausted(), i.e.
        after a real 403 quotaExceeded from Google. A key whose
        quota_used_today crept past get_usable_key()'s soft-stop line
        through ordinary usage (never actually hitting a hard error, since
        our local counter is just an estimate of Google's real one) still
        had status="active" but was silently excluded from every future
        get_usable_key() candidate pool forever -- nothing was watching
        quota_reset_at because it was still None. Stamping it on first use
        of a fresh day guarantees _reset_if_due always has a real deadline
        to compare against, regardless of how the key stops being usable."""
        await self.session.execute(
            update(YouTubeApiKey)
            .where(YouTubeApiKey.id == key_id)
            .values(
                quota_used_today=YouTubeApiKey.quota_used_today + units,
                quota_reset_at=func.coalesce(YouTubeApiKey.quota_reset_at, next_midnight_pacific()),
                last_used_at=func.now(),
                last_success_at=func.now(),
            )
        )
        await self.session.commit()

    async def mark_exhausted(self, key_id: UUID) -> None:
        key = await self.session.get(YouTubeApiKey, key_id)
        if key is None:
            return
        key.status = "quota_exhausted"
        key.quota_reset_at = next_midnight_pacific()
        key.last_failure_at = datetime.now(timezone.utc)
        await self.session.commit()

    async def mark_invalid(self, key_id: UUID, detail: str) -> None:
        key = await self.session.get(YouTubeApiKey, key_id)
        if key is None:
            return
        key.status = "invalid"
        key.error_message = detail
        key.failure_count += 1
        key.last_failure_at = datetime.now(timezone.utc)
        logger.error("YouTube API key marked invalid", label=key.label, detail=detail)
        await self.session.commit()

    async def update_status(self, key_id: UUID, status: str) -> YouTubeApiKey:
        key = await self.get_by_id(key_id)
        key.status = status
        await self.session.commit()
        return key

    async def delete(self, key_id: UUID) -> None:
        key = await self.session.get(YouTubeApiKey, key_id)
        if key is None:
            return
        await self.session.delete(key)
        await self.session.commit()
