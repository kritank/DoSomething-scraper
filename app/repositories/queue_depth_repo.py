from datetime import date, datetime, timedelta, timezone
from typing import Optional, Sequence

from sqlalchemy import Row, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.queue_depth_snapshot import QueueDepthSnapshot


class QueueDepthRepo:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def record_snapshot(self, backend: str, main_depth: Optional[int], dlq_depth: Optional[int]) -> None:
        self.session.add(QueueDepthSnapshot(backend=backend, main_depth=main_depth, dlq_depth=dlq_depth))
        await self.session.commit()

    async def get_hourly_history(self, start_date: date, end_date: date) -> Sequence[Row]:
        """Hour-bucketed, not day-bucketed like everything else in this
        dashboard -- queue depth is a fast-moving metric (the whole point
        of watching it is catching backlog building up within a single
        day), so day granularity would flatten exactly the signal this
        exists to show.
        """
        range_start = datetime.combine(start_date, datetime.min.time()).replace(tzinfo=timezone.utc)
        range_end = datetime.combine(end_date, datetime.min.time()).replace(tzinfo=timezone.utc) + timedelta(days=1)
        hour = func.date_trunc("hour", QueueDepthSnapshot.snapshot_at).label("hour")
        stmt = (
            select(
                hour,
                func.avg(QueueDepthSnapshot.main_depth).label("avg_main_depth"),
                func.max(QueueDepthSnapshot.main_depth).label("max_main_depth"),
                func.avg(QueueDepthSnapshot.dlq_depth).label("avg_dlq_depth"),
                func.max(QueueDepthSnapshot.dlq_depth).label("max_dlq_depth"),
            )
            .where(QueueDepthSnapshot.snapshot_at >= range_start)
            .where(QueueDepthSnapshot.snapshot_at < range_end)
            .group_by(hour)
            .order_by(hour)
        )
        result = await self.session.execute(stmt)
        return result.all()
