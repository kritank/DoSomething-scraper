from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.app_setting import AppSetting

INSTAGRAM_BACKEND_KEY = "instagram_backend"


class AppSettingRepo:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, key: str) -> Optional[str]:
        result = await self.session.execute(select(AppSetting.value).where(AppSetting.key == key))
        return result.scalar_one_or_none()

    async def set(self, key: str, value: str) -> None:
        """Upsert -- one round trip, no read-then-write race between two
        concurrent callers flipping the same key."""
        stmt = pg_insert(AppSetting).values(key=key, value=value)
        stmt = stmt.on_conflict_do_update(index_elements=[AppSetting.key], set_={"value": value})
        await self.session.execute(stmt)
        await self.session.commit()

    async def get_all(self) -> dict[str, str]:
        result = await self.session.execute(select(AppSetting.key, AppSetting.value))
        return dict(result.all())
