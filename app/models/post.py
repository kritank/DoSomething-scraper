import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.influencer import Influencer
    from app.models.snapshot import PostMetricsSnapshot
    from app.models.feature_store import FeatureStore
    from app.models.post_outlier_metrics import PostOutlierMetrics
    from app.models.comment import Comment


class Post(Base):
    __tablename__ = "posts"
    __table_args__ = (
        # Backs the feed-pagination cutoff scan and the comment-sync
        # window query, both filtered/ordered by (influencer_id, posted_at).
        Index("ix_posts_influencer_id_posted_at", "influencer_id", "posted_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    influencer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("influencers.id", ondelete="CASCADE"),
        nullable=False,
    )
    shortcode: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    media_pk: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    caption: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # YouTube separates a video's title from its description -- null for
    # Instagram rows, where caption already covers both. Deliberately not
    # concatenated into caption: that would corrupt caption_length/
    # word_count feature-store benchmarks shared across platforms.
    title: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    hashtags: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    mentions: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)

    posted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    permalink: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    accessibility_caption: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_paid_partnership: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    product_type: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    music_metadata: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    original_height: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    original_width: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    locations: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    coauthor_producers: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    tagged_usernames: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    counts_disabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Platform-specific fields that don't warrant their own column (YouTube
    # tags, definition/dimension, category/topics, madeForKids, etc.) --
    # see docs/YOUTUBE_SCRAPER_DESIGN.md §3.2. Null for Instagram rows.
    platform_metadata: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    influencer: Mapped["Influencer"] = relationship(
        "Influencer", back_populates="posts"
    )
    metrics_snapshots: Mapped[list["PostMetricsSnapshot"]] = relationship(
        "PostMetricsSnapshot", back_populates="post", cascade="all, delete-orphan"
    )
    feature_store: Mapped[Optional["FeatureStore"]] = relationship(
        "FeatureStore", back_populates="post", uselist=False, cascade="all, delete-orphan"
    )
    outlier_metrics: Mapped[Optional["PostOutlierMetrics"]] = relationship(
        "PostOutlierMetrics", back_populates="post", uselist=False, cascade="all, delete-orphan"
    )
    # passive_deletes=True -- comments.post_id is NOT NULL with an
    # ON DELETE CASCADE at the DB level, but without this the ORM's default
    # behavior on deleting a Post is to SELECT its comments and UPDATE
    # their post_id to NULL first (since no ORM-level cascade is declared
    # here), which violates that NOT NULL constraint. This tells SQLAlchemy
    # to leave child rows alone and trust Postgres's cascade to delete them.
    comments: Mapped[list["Comment"]] = relationship(
        "Comment", back_populates="post", passive_deletes=True
    )

    def __repr__(self) -> str:
        return f"<Post id={self.id} shortcode={self.shortcode}>"
