from typing import Optional, Sequence
from uuid import UUID

from sqlalchemy import Row, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from app.core.exceptions import DuplicateInfluencerError, InfluencerNotFoundError
from app.models.category import Category
from app.models.influencer import Influencer
from app.models.post import Post
from app.models.snapshot import PostMetricsSnapshot, ProfileSnapshot
from app.schemas.influencer import (
    InfluencerActiveUpdate,
    InfluencerCreate,
    InfluencerDetailsUpdate,
    InfluencerScrapeSettingsUpdate,
)

# How many of an influencer's most recent posts feed the engagement-rate
# average on the top-influencers leaderboard. Keeps the metric responsive to
# recent performance instead of being diluted by years of post history.
ENGAGEMENT_LOOKBACK_POSTS = 12


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

    async def get_top_ranked(
        self, limit: int = 20, category_name: Optional[str] = None
    ) -> Sequence[Row]:
        """Ranked leaderboard for the public "Top Influencers" page: each
        active influencer's latest profile snapshot (followers/verified/etc.)
        plus an engagement rate averaged over their most recent posts.

        Returns raw Rows (not ORM objects) since this is a read-only
        aggregate projection, not a mapped entity.
        """
        latest_snapshot = (
            select(
                ProfileSnapshot,
                func.row_number()
                .over(
                    partition_by=ProfileSnapshot.influencer_id,
                    order_by=ProfileSnapshot.scraped_at.desc(),
                )
                .label("rn"),
            )
            .subquery("latest_snapshot")
        )

        latest_metric = (
            select(
                PostMetricsSnapshot.post_id,
                PostMetricsSnapshot.likes,
                PostMetricsSnapshot.comments,
                func.row_number()
                .over(
                    partition_by=PostMetricsSnapshot.post_id,
                    order_by=PostMetricsSnapshot.scraped_at.desc(),
                )
                .label("rn"),
            )
            .subquery("latest_metric")
        )

        recent_posts = (
            select(
                Post.id,
                Post.influencer_id,
                func.row_number()
                .over(partition_by=Post.influencer_id, order_by=Post.posted_at.desc())
                .label("rn"),
            )
            .subquery("recent_posts")
        )

        engagement = (
            select(
                recent_posts.c.influencer_id,
                func.avg(latest_metric.c.likes + latest_metric.c.comments).label(
                    "avg_engagement"
                ),
            )
            .join(latest_metric, latest_metric.c.post_id == recent_posts.c.id)
            .where(
                recent_posts.c.rn <= ENGAGEMENT_LOOKBACK_POSTS,
                latest_metric.c.rn == 1,
            )
            .group_by(recent_posts.c.influencer_id)
            .subquery("engagement")
        )

        stmt = (
            select(
                Influencer.id,
                Influencer.handle,
                Category.name.label("category_name"),
                latest_snapshot.c.followers,
                latest_snapshot.c.following,
                latest_snapshot.c.posts,
                latest_snapshot.c.is_verified,
                latest_snapshot.c.updated_at.label("last_updated"),
                engagement.c.avg_engagement,
            )
            .join(latest_snapshot, latest_snapshot.c.influencer_id == Influencer.id)
            .join(Category, Category.id == Influencer.category_id)
            .outerjoin(engagement, engagement.c.influencer_id == Influencer.id)
            .where(Influencer.is_active.is_(True), latest_snapshot.c.rn == 1)
        )
        if category_name:
            stmt = stmt.where(Category.name == category_name)
        stmt = stmt.order_by(latest_snapshot.c.followers.desc()).limit(limit)

        result = await self.session.execute(stmt)
        return result.all()
