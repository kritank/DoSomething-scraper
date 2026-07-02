from typing import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.core.exceptions import DuplicateInfluencerError, InfluencerNotFoundError
from app.models.influencer import Influencer
from app.schemas.influencer import InfluencerCreate


class InfluencerRepo:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_all(self) -> Sequence[Influencer]:
        result = await self.session.execute(select(Influencer).order_by(Influencer.handle))
        return result.scalars().all()

    async def create(self, data: InfluencerCreate) -> Influencer:
        influencer = Influencer(handle=data.handle, category_id=data.category_id)
        self.session.add(influencer)
        try:
            await self.session.commit()
            return influencer
        except IntegrityError:
            await self.session.rollback()
            raise DuplicateInfluencerError(data.handle)

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
