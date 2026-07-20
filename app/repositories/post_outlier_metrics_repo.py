from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.post_outlier_metrics import PostOutlierMetrics


class PostOutlierMetricsRepo:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def upsert_many(
        self,
        rows: list[dict[str, Optional[float]]],
    ) -> None:
        """Each row: {post_id, outlier_score, baseline_multiple, vph_current,
        vph_lifetime, engagement_ratio, baseline_median}. No-op on empty
        input. Caller commits."""
        if not rows:
            return
        now = datetime.now(timezone.utc)
        values = [{**row, "computed_at": now} for row in rows]
        stmt = insert(PostOutlierMetrics).values(values)
        stmt = stmt.on_conflict_do_update(
            index_elements=[PostOutlierMetrics.post_id],
            set_={
                "outlier_score": stmt.excluded.outlier_score,
                "baseline_multiple": stmt.excluded.baseline_multiple,
                "vph_current": stmt.excluded.vph_current,
                "vph_lifetime": stmt.excluded.vph_lifetime,
                "engagement_ratio": stmt.excluded.engagement_ratio,
                "baseline_median": stmt.excluded.baseline_median,
                "computed_at": stmt.excluded.computed_at,
            },
        )
        await self.session.execute(stmt)
