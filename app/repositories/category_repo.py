from typing import Sequence
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.core.exceptions import DuplicateCategoryError, CategoryNotFoundError
from app.models.category import Category
from app.models.influencer import Influencer
from app.schemas.category import CategoryCreate, CategoryUpdate


class CategoryRepo:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_all(self) -> Sequence[Category]:
        result = await self.session.execute(select(Category).order_by(Category.name))
        return result.scalars().all()

    async def create(self, data: CategoryCreate) -> Category:
        category = Category(name=data.name)
        self.session.add(category)
        try:
            await self.session.commit()
            return category
        except IntegrityError:
            await self.session.rollback()
            raise DuplicateCategoryError(data.name)

    async def get_by_id(self, category_id: UUID) -> Category:
        category = await self.session.get(Category, category_id)
        if not category:
            raise CategoryNotFoundError(str(category_id))
        return category

    async def get_by_name(self, name: str) -> Category:
        """Case-insensitive exact match -- used by the influencer
        bulk-import flow (app/services/influencer_bulk_import.py), where a
        spreadsheet's free-text "category" column has to resolve to a real
        category without requiring the uploader to match capitalization
        exactly."""
        stmt = select(Category).where(func.lower(Category.name) == name.strip().lower())
        category = (await self.session.execute(stmt)).scalar_one_or_none()
        if not category:
            raise CategoryNotFoundError(name)
        return category

    async def update(self, category_id: UUID, data: CategoryUpdate) -> Category:
        category = await self.get_by_id(category_id)
        if data.name is not None:
            category.name = data.name
        # Cascades the category's own is_active flag to its influencers --
        # previously this column was purely cosmetic (an "(inactive)" label)
        # and the scheduler never looked at it, so "deactivating" a category
        # didn't actually stop anything under it from scraping.
        #
        # Deactivating: pauses every *currently active* influencer in the
        # category, tagging each as paused_by_category=true so a later
        # reactivate knows it's safe to resume them.
        #
        # Reactivating: resumes only influencers this category itself
        # paused (paused_by_category=true) -- one a user separately
        # deactivated for their own reason (e.g. a broken account) stays
        # off, matching InfluencerRepo.update_active's contract that a
        # manual toggle is always the explicit source of truth.
        if data.is_active is not None and data.is_active != category.is_active:
            category.is_active = data.is_active
            if data.is_active:
                stmt = (
                    update(Influencer)
                    .where(Influencer.category_id == category_id, Influencer.paused_by_category.is_(True))
                    .values(is_active=True, paused_by_category=False)
                )
            else:
                stmt = (
                    update(Influencer)
                    .where(Influencer.category_id == category_id, Influencer.is_active.is_(True))
                    .values(is_active=False, paused_by_category=True)
                )
            await self.session.execute(stmt)
        try:
            await self.session.commit()
        except IntegrityError:
            await self.session.rollback()
            raise DuplicateCategoryError(data.name or category.name)
        return category

    async def delete(self, category_id: UUID) -> None:
        """Hard delete -- cascades to every influencer in this category, and
        from there to their posts/comments/snapshots/feature_store rows via
        DB-level ON DELETE CASCADE. Irreversible; the API layer requires this
        to be called explicitly (not the default "remove" action)."""
        category = await self.get_by_id(category_id)
        await self.session.delete(category)
        await self.session.commit()
