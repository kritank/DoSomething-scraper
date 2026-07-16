from typing import Sequence
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from app.core.exceptions import CreatorNotFoundError, DuplicateCreatorError
from app.models.creator import Creator


class CreatorRepo:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_all_with_influencers(self) -> Sequence[Creator]:
        """Eager-loads Creator.influencers so the API layer can summarize
        which platforms each creator has a linked account on without an
        N+1 lazy-load per creator."""
        stmt = (
            select(Creator)
            .options(selectinload(Creator.influencers))
            .order_by(Creator.name)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_by_id(self, creator_id: UUID) -> Creator:
        creator = await self.session.get(Creator, creator_id)
        if not creator:
            raise CreatorNotFoundError(str(creator_id))
        return creator

    async def get_or_create_by_name(self, name: str) -> Creator:
        """Case-insensitive match on the trimmed name -- so registering a
        creator's second platform account under the same name links to the
        existing row instead of silently creating a near-duplicate
        ("MrBeast" vs "mrbeast"). Flushes (not commits) so it participates
        in the caller's transaction -- see InfluencerRepo.create/
        update_details, which set creator_id on the same Influencer insert/
        update this is called from.
        """
        clean_name = name.strip()
        stmt = select(Creator).where(func.lower(Creator.name) == clean_name.lower())
        result = await self.session.execute(stmt)
        existing = result.scalar_one_or_none()
        if existing:
            return existing

        creator = Creator(name=clean_name)
        self.session.add(creator)
        await self.session.flush()
        return creator

    async def rename(self, creator_id: UUID, name: str) -> Creator:
        creator = await self.get_by_id(creator_id)
        creator.name = name.strip()
        try:
            await self.session.commit()
        except IntegrityError:
            await self.session.rollback()
            raise DuplicateCreatorError(name)
        return creator

    async def delete(self, creator_id: UUID) -> None:
        """Unlinks (not deletes) every associated Influencer -- creator_id
        is ON DELETE SET NULL, so each platform account and all its
        scraped data survive untouched; only the cross-platform grouping
        goes away."""
        creator = await self.get_by_id(creator_id)
        await self.session.delete(creator)
        await self.session.commit()
