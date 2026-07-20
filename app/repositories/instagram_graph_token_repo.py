from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func

from app.core.crypto import decrypt_json, encrypt_json
from app.core.exceptions import InstagramGraphTokenNotFoundError
from app.models.instagram_graph_token import InstagramGraphToken


class InstagramGraphTokenRepo:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def _get_by_label(self, label: str) -> Optional[InstagramGraphToken]:
        result = await self.session.execute(
            select(InstagramGraphToken).where(InstagramGraphToken.label == label)
        )
        return result.scalar_one_or_none()

    async def get_all(self) -> list[InstagramGraphToken]:
        result = await self.session.execute(
            select(InstagramGraphToken).order_by(InstagramGraphToken.label)
        )
        return list(result.scalars().all())

    async def get_by_id(self, token_id: UUID) -> InstagramGraphToken:
        token = await self.session.get(InstagramGraphToken, token_id)
        if token is None:
            raise InstagramGraphTokenNotFoundError(str(token_id))
        return token

    async def create(self, label: str, access_token: str) -> InstagramGraphToken:
        token = await self._get_by_label(label)
        if token is None:
            token = InstagramGraphToken(label=label)
            self.session.add(token)

        token.access_token_encrypted = encrypt_json({"token": access_token})
        token.status = "active"
        token.error_message = None
        token.failure_count = 0
        token.last_used_at = None
        token.last_success_at = None
        token.last_failure_at = None
        token.cooldown_until = None
        await self.session.commit()
        return token

    def decrypt_token(self, token: InstagramGraphToken) -> str:
        return decrypt_json(token.access_token_encrypted)["token"]

    async def _reset_if_due(self, token: InstagramGraphToken) -> None:
        if token.cooldown_until is not None and token.cooldown_until <= datetime.now(timezone.utc):
            token.cooldown_until = None
            if token.status == "disabled":
                token.status = "active"

    async def get_usable_token(self) -> Optional[InstagramGraphToken]:
        result = await self.session.execute(
            select(InstagramGraphToken).where(InstagramGraphToken.status.in_(("active", "disabled")))
        )
        tokens = list(result.scalars().all())
        if not tokens:
            return None

        dirty = False
        for token in tokens:
            before = (token.status, token.cooldown_until)
            await self._reset_if_due(token)
            if (token.status, token.cooldown_until) != before:
                dirty = True
        if dirty:
            await self.session.commit()

        usable = [token for token in tokens if token.status == "active" and (token.cooldown_until is None)]
        if not usable:
            return None
        return min(usable, key=lambda t: t.last_used_at or datetime(1970, 1, 1, tzinfo=timezone.utc))

    async def update_status(self, token_id: UUID, status: str) -> InstagramGraphToken:
        token = await self.get_by_id(token_id)
        token.status = status
        await self.session.commit()
        return token

    async def mark_cooldown(self, token_id: UUID, cooldown_s: int = 3600, detail: str | None = None) -> None:
        token = await self.session.get(InstagramGraphToken, token_id)
        if token is None:
            return
        token.status = "disabled"
        token.cooldown_until = datetime.now(timezone.utc) + timedelta(seconds=cooldown_s)
        token.last_failure_at = datetime.now(timezone.utc)
        if detail:
            token.error_message = detail
        token.failure_count += 1
        await self.session.commit()

    async def delete(self, token_id: UUID) -> None:
        token = await self.session.get(InstagramGraphToken, token_id)
        if token is None:
            return
        await self.session.delete(token)
        await self.session.commit()
