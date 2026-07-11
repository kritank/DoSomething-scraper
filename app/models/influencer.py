import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.category import Category
    from app.models.snapshot import ProfileSnapshot


class Influencer(Base):
    __tablename__ = "influencers"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    handle: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    category_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("categories.id", ondelete="RESTRICT"),
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")

    # Don't pull posts older than this date (null = full history). Bounds
    # the one-time backfill's request count for accounts with years of posts.
    scrape_posts_since: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    # Backfill state: the initial full-history pull can take many runs to
    # finish (rate limits, crashes, worker restarts). backfill_completed
    # distinguishes "still backfilling" from steady-state incremental
    # scraping; backfill_cursor is the feed's next_max_id so a resumed
    # backfill continues near where it left off instead of re-walking
    # already-fetched pages.
    backfill_completed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    backfill_cursor: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    category: Mapped["Category"] = relationship(
        "Category", back_populates="influencers"
    )
    profile_snapshots: Mapped[list["ProfileSnapshot"]] = relationship(
        "ProfileSnapshot", back_populates="influencer", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Influencer id={self.id} handle={self.handle}>"
