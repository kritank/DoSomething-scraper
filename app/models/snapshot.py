import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import BigInteger, Boolean, Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.influencer import Influencer
    from app.models.post import Post


class ProfileSnapshot(Base):
    __tablename__ = "profile_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    influencer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("influencers.id", ondelete="CASCADE"),
        nullable=False,
    )
    scraped_at: Mapped[date] = mapped_column(Date, nullable=False, server_default=func.current_date())
    
    followers: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    following: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    posts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    biography: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    biography_with_entities: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    bio_links: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    pronouns: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    external_url: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)

    is_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_business_account: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_professional_account: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    category_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    category_enum: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    overall_category_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    business_contact_method: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    business_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    business_phone_number: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    highlight_reel_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    has_clips: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    has_guides: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    has_channel: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    mutual_followers_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    is_meta_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    hides_like_view_counts: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    has_ar_effects: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    business_category_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # YouTube-only: a channel's lifetime view count has no Instagram
    # equivalent. BigInteger -- large channels exceed Integer's ~2.1B range.
    total_views: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    # True when statistics.hiddenSubscriberCount is set -- distinguishes
    # "0 subscribers" (followers=0, this false) from "count not disclosed"
    # (followers=0, this true), so it's never mistaken for a dead channel.
    subscribers_hidden: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Platform-specific extras that don't warrant their own column (channel
    # creation date, country, keywords, madeForKids, topic categories) --
    # see docs/YOUTUBE_SCRAPER_DESIGN.md §3.1. Null for Instagram rows.
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
        "Influencer", back_populates="profile_snapshots"
    )

    def __repr__(self) -> str:
        return f"<ProfileSnapshot influencer={self.influencer_id} date={self.scraped_at}>"


class PostMetricsSnapshot(Base):
    __tablename__ = "post_metrics_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    post_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("posts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    scraped_at: Mapped[date] = mapped_column(Date, nullable=False, server_default=func.current_date())

    # NULL (not 0) whenever the platform doesn't publicly expose the metric
    # for this item -- e.g. a YouTube video with likes hidden by the
    # creator, or comments disabled. Instagram rows always have real
    # (possibly zero) values here; only YouTube rows are expected to be NULL.
    likes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    comments: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # NULL (not 0) for media types with no public view metric at all --
    # see JobProcessor._record_metrics_snapshot. BigInteger since a viral
    # reel's play count routinely exceeds Integer's ~2.1B range.
    views: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    # Instagram exposes no save_count for other accounts' posts (fully
    # private to the owner via Insights); reshare_count is the closest
    # real, public metric there. YouTube exposes no public share count at
    # all -- NULL for every YouTube row, never a fabricated 0.
    reposts: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    post: Mapped["Post"] = relationship(
        "Post", back_populates="metrics_snapshots"
    )

    def __repr__(self) -> str:
        return f"<PostMetricsSnapshot post={self.post_id} date={self.scraped_at}>"
