import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


class QueueDepthSnapshot(Base):
    """A periodic point-in-time sample of the scrape job queue's depth,
    taken every CRON_RETRY_FAILED tick by
    app.scheduler.runner.snapshot_queue_depth. GET /admin/queue/status only
    ever answers "what's the depth right now" -- this table exists so the
    dashboard can chart depth (and DLQ backlog) *over time*, which is the
    actual signal for "is the worker pool falling behind."

    dlq_depth is NULL for the Redis backend (no DLQ concept there -- see
    RedisQueueBackend), never a fabricated 0.
    """

    __tablename__ = "queue_depth_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    snapshot_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )
    backend: Mapped[str] = mapped_column(String(16), nullable=False)
    main_depth: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    dlq_depth: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    def __repr__(self) -> str:
        return f"<QueueDepthSnapshot snapshot_at={self.snapshot_at} main_depth={self.main_depth}>"
