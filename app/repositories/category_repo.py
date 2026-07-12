from typing import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.core.exceptions import DuplicateCategoryError, CategoryNotFoundError
from app.models.category import Category
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

    async def update(self, category_id: UUID, data: CategoryUpdate) -> Category:
        category = await self.get_by_id(category_id)
        if data.name is not None:
            category.name = data.name
        if data.is_active is not None:
            category.is_active = data.is_active
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
