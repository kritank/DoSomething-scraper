from __future__ import annotations

from typing import Optional
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.influencer import Influencer
from app.models.post import Post
from app.models.post_outlier_metrics import PostOutlierMetrics
from app.models.snapshot import PostMetricsSnapshot


class PostRepo:
    def __init__(self, session: AsyncSession):
        self.session = session

    def _latest_snapshot_subquery(self):
        # One row per post: its most recent metrics snapshot. Same
        # DISTINCT ON pattern as ScrapeJobRepo.get_latest_per_influencer --
        # a single indexed scan, Postgres-only (consistent with the rest
        # of the app).
        return (
            select(PostMetricsSnapshot)
            .distinct(PostMetricsSnapshot.post_id)
            .order_by(PostMetricsSnapshot.post_id, PostMetricsSnapshot.created_at.desc())
            .subquery()
        )

    async def list_posts(
        self,
        influencer_id: Optional[UUID] = None,
        category_id: Optional[UUID] = None,
        platforms: Optional[list[str]] = None,
        # Cross-creator outliers feed (docs/OUTLIERS_PLAN.md Phase 3) --
        # posts below min_score, or with no score yet, are excluded when set.
        min_score: Optional[float] = None,
        sort: str = "posted_at",
        sort_dir: str = "desc",
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict], int]:
        latest = self._latest_snapshot_subquery()

        def _apply_filters(stmt):
            if influencer_id is not None:
                stmt = stmt.where(Post.influencer_id == influencer_id)
            if category_id is not None:
                stmt = stmt.where(Influencer.category_id == category_id)
            if platforms:
                stmt = stmt.where(Influencer.platform.in_(platforms))
            if min_score is not None:
                stmt = stmt.where(PostOutlierMetrics.outlier_score >= min_score)
            return stmt

        base = _apply_filters(
            select(Post)
            .join(Influencer, Influencer.id == Post.influencer_id)
            .outerjoin(PostOutlierMetrics, PostOutlierMetrics.post_id == Post.id)
        )
        count_stmt = select(func.count()).select_from(base.subquery())
        total = (await self.session.execute(count_stmt)).scalar_one()

        sort_col = {
            "posted_at": Post.posted_at,
            "likes": latest.c.likes,
            "comments": latest.c.comments,
            "outlier_score": PostOutlierMetrics.outlier_score,
            "vph_current": PostOutlierMetrics.vph_current,
        }.get(sort, Post.posted_at)
        # NULLs (posts not yet scored) always sort last, regardless of
        # direction -- otherwise "sort by outlier score desc" would put
        # every unscored post above every real 5x outlier.
        order = (
            [sort_col.desc().nullslast(), Post.posted_at.desc()]
            if sort_dir == "desc"
            else [sort_col.asc().nullslast(), Post.posted_at.desc()]
        )

        stmt = _apply_filters(
            select(
                Post.id,
                Post.influencer_id,
                Influencer.handle,
                Influencer.platform,
                Post.shortcode,
                Post.title,
                Post.caption,
                Post.permalink,
                Post.posted_at,
                latest.c.likes,
                latest.c.comments,
                latest.c.views,
                latest.c.reposts,
                PostOutlierMetrics.outlier_score,
                PostOutlierMetrics.baseline_multiple,
                PostOutlierMetrics.vph_current,
            )
            .select_from(Post)
            .join(Influencer, Influencer.id == Post.influencer_id)
            .outerjoin(latest, latest.c.post_id == Post.id)
            .outerjoin(PostOutlierMetrics, PostOutlierMetrics.post_id == Post.id)
        ).order_by(*order).limit(limit).offset(offset)

        result = await self.session.execute(stmt)
        rows = [dict(r._mapping) for r in result.all()]
        return rows, total
