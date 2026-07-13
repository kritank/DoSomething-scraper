from typing import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from app.core.exceptions import DuplicateInfluencerError, InfluencerNotFoundError
from app.models.influencer import Influencer
from app.schemas.influencer import (
    InfluencerActiveUpdate,
    InfluencerCreate,
    InfluencerDetailsUpdate,
    InfluencerScrapeSettingsUpdate,
)


class InfluencerRepo:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_all(self) -> Sequence[Influencer]:
        result = await self.session.execute(select(Influencer).order_by(Influencer.handle))
        return result.scalars().all()

    async def get_all_with_category(self) -> Sequence[Influencer]:
        """Eager-loads Influencer.category so the dashboard can read
        category_name without an N+1 lazy-load per influencer."""
        stmt = (
            select(Influencer)
            .options(selectinload(Influencer.category))
            .order_by(Influencer.handle)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def create(self, data: InfluencerCreate) -> Influencer:
        influencer = Influencer(
            handle=data.handle,
            category_id=data.category_id,
            scrape_posts_since=data.scrape_posts_since,
        )
        self.session.add(influencer)
        try:
            await self.session.commit()
            return influencer
        except IntegrityError:
            await self.session.rollback()
            raise DuplicateInfluencerError(data.handle)

    async def update_scrape_settings(
        self, influencer_id: UUID, data: InfluencerScrapeSettingsUpdate
    ) -> Influencer:
        influencer = await self.get_by_id(influencer_id)
        influencer.scrape_posts_since = data.scrape_posts_since
        await self.session.commit()
        return influencer

    async def update_active(self, influencer_id: UUID, data: InfluencerActiveUpdate) -> Influencer:
        """Pause/resume tracking without touching any scraped data -- the
        default, reversible "remove" action. run_daily_scrapes() and the
        dashboard's add-influencer flow already only consider is_active
        influencers."""
        influencer = await self.get_by_id(influencer_id)
        influencer.is_active = data.is_active
        await self.session.commit()
        return influencer

    async def update_details(self, influencer_id: UUID, data: InfluencerDetailsUpdate) -> Influencer:
        """Corrects a wrong handle or moves an influencer to a different
        category after creation -- neither was possible before (both were
        write-once at create() time), which is exactly what forced a manual
        SQL fix for a mistyped handle earlier."""
        influencer = await self.get_by_id(influencer_id)
        if data.handle is not None:
            influencer.handle = data.handle
        if data.category_id is not None:
            influencer.category_id = data.category_id
        try:
            await self.session.commit()
        except IntegrityError:
            await self.session.rollback()
            raise DuplicateInfluencerError(data.handle or influencer.handle)
        return influencer

    async def delete(self, influencer_id: UUID) -> None:
        """Hard delete -- cascades to posts/comments/snapshots/feature_store
        via DB-level ON DELETE CASCADE. Irreversible."""
        influencer = await self.get_by_id(influencer_id)
        await self.session.delete(influencer)
        await self.session.commit()

    async def get_by_id(self, influencer_id: UUID) -> Influencer:
        influencer = await self.session.get(Influencer, influencer_id)
        if not influencer:
            raise InfluencerNotFoundError(str(influencer_id))
        return influencer
    
    async def get_by_handle(self, handle: str) -> Influencer:
        result = await self.session.execute(select(Influencer).where(Influencer.handle == handle))
        influencer = result.scalar_one_or_none()
        if not influencer:
            raise InfluencerNotFoundError(handle)
        return influencer
