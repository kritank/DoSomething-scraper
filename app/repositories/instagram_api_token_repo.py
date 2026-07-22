from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func

from app.core.crypto import decrypt_json, encrypt_json
from app.core.exceptions import InstagramApiTokenNotFoundError
from app.core.logging import get_logger
from app.models.instagram_api_token import InstagramApiToken

logger = get_logger(__name__)


class InstagramApiTokenRepo:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def _get_by_label(self, label: str) -> Optional[InstagramApiToken]:
        result = await self.session.execute(
            select(InstagramApiToken).where(InstagramApiToken.label == label)
        )
        return result.scalar_one_or_none()

    async def get_all(self) -> list[InstagramApiToken]:
        result = await self.session.execute(
            select(InstagramApiToken).order_by(InstagramApiToken.label)
        )
        return list(result.scalars().all())

    async def get_by_id(self, token_id: UUID) -> InstagramApiToken:
        token = await self.session.get(InstagramApiToken, token_id)
        if token is None:
            raise InstagramApiTokenNotFoundError(str(token_id))
        return token

    async def create(
        self,
        label: str,
        access_token: str,
        ig_user_id: str,
        app_id: str,
        app_secret: str,
        auth_flavor: str,
        token_expires_at: Optional[datetime] = None,
    ) -> InstagramApiToken:
        """Register (or re-register) a token. Upserts by label, same
        pattern as YouTubeApiKeyRepo.create -- rotating a token's raw value
        shouldn't require deleting and re-adding the row."""
        token = await self._get_by_label(label)
        if token is None:
            token = InstagramApiToken(label=label)
            self.session.add(token)

        token.access_token_encrypted = encrypt_json({"token": access_token})
        token.ig_user_id = ig_user_id
        token.app_id = app_id
        token.app_secret_encrypted = encrypt_json({"secret": app_secret})
        token.auth_flavor = auth_flavor
        token.token_expires_at = token_expires_at
        token.status = "active"
        token.error_message = None
        token.failure_count = 0
        token.calls_today = 0
        token.cooldown_until = None
        token.buc_usage_pct = None
        await self.session.commit()
        return token

    def decrypt_token(self, token: InstagramApiToken) -> str:
        return decrypt_json(token.access_token_encrypted)["token"]

    def decrypt_app_secret(self, token: InstagramApiToken) -> str:
        return decrypt_json(token.app_secret_encrypted)["secret"]

    async def _reset_if_due(self, token: InstagramApiToken) -> None:
        """BUC is a rolling 24h window, not a fixed daily reset -- unlike
        YouTubeApiKeyRepo._reset_if_due (midnight Pacific), a token in
        cooldown just flips back to active once cooldown_until has passed;
        there is no quota counter to zero alongside it (calls_today is
        bookkeeping only, reset separately at UTC midnight by
        reset_daily_call_counts() below, not gating usability here)."""
        if token.cooldown_until is not None and token.cooldown_until <= datetime.now(timezone.utc):
            token.cooldown_until = None
            if token.status == "cooldown":
                token.status = "active"

    async def reset_daily_call_counts(self) -> None:
        """calls_today is a plain observability counter (BUC usage_pct is
        what actually gates rotation) -- previously never reset by
        anything despite this class's own docstring claiming it was,
        so it silently accumulated as a lifetime total instead of "today's"
        count. Run once a day by the scheduler (app/scheduler/runner.py),
        same UTC-midnight-ish cadence as YouTube key resets even though
        BUC itself doesn't have a fixed reset boundary -- this is purely
        for the dashboard's own daily-usage display, not for gating."""
        await self.session.execute(update(InstagramApiToken).values(calls_today=0))
        await self.session.commit()

    async def get_usable_token(self) -> Optional[InstagramApiToken]:
        """Round-robin by last_used_at among active tokens -- unlike
        InstagramAccountRepo.acquire_healthy_account, this doesn't
        lease/lock the row -- a bearer token is safely shareable across
        concurrent requests, so there's nothing to release afterwards.
        Callers record usage via add_usage() as requests happen."""
        result = await self.session.execute(
            select(InstagramApiToken).where(
                InstagramApiToken.status.in_(("active", "cooldown"))
            )
        )
        candidates = list(result.scalars().all())
        if not candidates:
            return None

        dirty = False
        for token in candidates:
            before = (token.status, token.cooldown_until)
            await self._reset_if_due(token)
            if (token.status, token.cooldown_until) != before:
                dirty = True
        if dirty:
            await self.session.commit()

        usable = [token for token in candidates if token.status == "active"]
        if not usable:
            return None
        return min(
            usable,
            key=lambda t: t.last_used_at or datetime.min.replace(tzinfo=timezone.utc),
        )

    async def add_usage(self, token_id: UUID, calls: int, buc_pct: Optional[float]) -> None:
        """Atomic increment (not read-modify-write) -- safe under the
        concurrent requests a single job (or several jobs sharing this
        token) can issue at once. buc_pct overwrites (not accumulates) --
        it's the last-seen header value, not a counter."""
        values: dict = {
            "calls_today": InstagramApiToken.calls_today + calls,
            "last_used_at": func.now(),
            "last_success_at": func.now(),
        }
        if buc_pct is not None:
            values["buc_usage_pct"] = buc_pct
        await self.session.execute(
            update(InstagramApiToken).where(InstagramApiToken.id == token_id).values(**values)
        )
        await self.session.commit()

    async def mark_exhausted(self, token_id: UUID, cooldown_until: datetime) -> None:
        token = await self.session.get(InstagramApiToken, token_id)
        if token is None:
            return
        token.status = "cooldown"
        token.cooldown_until = cooldown_until
        token.last_failure_at = datetime.now(timezone.utc)
        await self.session.commit()

    async def mark_invalid(self, token_id: UUID, detail: str) -> None:
        token = await self.session.get(InstagramApiToken, token_id)
        if token is None:
            return
        token.status = "invalid"
        token.error_message = detail
        token.failure_count += 1
        token.last_failure_at = datetime.now(timezone.utc)
        logger.error("Instagram API token marked invalid", label=token.label, detail=detail)
        await self.session.commit()

    async def update_token(
        self, token_id: UUID, access_token: str, token_expires_at: Optional[datetime]
    ) -> None:
        """Applies a refreshed access token (see the daily
        refresh_instagram_tokens scheduler job, PR2 2.5) without touching
        status/failure_count -- a refresh is independent of the token's
        current health."""
        token = await self.session.get(InstagramApiToken, token_id)
        if token is None:
            return
        token.access_token_encrypted = encrypt_json({"token": access_token})
        token.token_expires_at = token_expires_at
        await self.session.commit()

    async def update_status(self, token_id: UUID, status: str) -> InstagramApiToken:
        token = await self.get_by_id(token_id)
        token.status = status
        await self.session.commit()
        return token

    async def delete(self, token_id: UUID) -> None:
        token = await self.session.get(InstagramApiToken, token_id)
        if token is None:
            return
        await self.session.delete(token)
        await self.session.commit()
