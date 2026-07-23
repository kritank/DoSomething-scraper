import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.category import Category
    from app.models.creator import Creator
    from app.models.snapshot import ProfileSnapshot
    from app.models.post import Post


class Influencer(Base):
    __tablename__ = "influencers"
    __table_args__ = (
        # A handle is only unique within a platform -- the same @handle can
        # legitimately exist as both an Instagram and a YouTube influencer.
        UniqueConstraint("platform", "handle", name="uq_influencers_platform_handle"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    handle: Mapped[str] = mapped_column(String(255), nullable=False)
    # "instagram" | "youtube". Drives which JobProcessor the queue message
    # routes to (see worker_runner._run_one) and which handle-normalization
    # rules apply on create (see InfluencerRepo.create).
    platform: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="instagram", index=True
    )
    # Canonical platform-side ID resolved on first scrape (YouTube channel
    # ID "UC...", Instagram numeric pk) -- lets a handle rename survive
    # without orphaning this row. Null until the first successful scrape.
    platform_user_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    # Latest known avatar/channel-thumbnail URL, refreshed on every scrape
    # (unlike platform_user_id, which is permanent and set once) -- these
    # URLs are frequently signed/expiring on both platforms, so caching a
    # stale one indefinitely would eventually 403 in the dashboard.
    profile_pic_url: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)
    # Optional cross-platform grouping -- see app.models.creator.Creator.
    # ON DELETE SET NULL: deleting the Creator group must never cascade
    # into deleting this row's own scraped data.
    creator_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("creators.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    category_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("categories.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    # "business" | "individual" -- freeform enough that a bad value doesn't
    # break reads (no DB CHECK constraint, same convention as `platform`),
    # validated at the Pydantic layer instead (see InfluencerCreate/
    # InfluencerDetailsUpdate). Defaults to "individual"; set explicitly at
    # creation or edited after the fact via update_details, same as category.
    account_type: Mapped[str] = mapped_column(String(16), nullable=False, server_default="individual")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true", index=True)
    # True only when this row's is_active=false was set by a category-level
    # deactivate (CategoryRepo.update), never by a direct per-influencer
    # toggle -- lets reactivating the category resume exactly the
    # influencers it paused, without touching ones a user separately
    # deactivated for their own reasons (e.g. a broken account). Any manual
    # per-influencer toggle (InfluencerRepo.update_active) always resets
    # this back to false, since that action is now the explicit source of
    # truth for the row.
    paused_by_category: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    # Set only when a scrape job auto-deactivated this influencer because
    # the platform confirmed the handle doesn't resolve to any account
    # (InfluencerHandleNotFoundError -- see JobProcessor/
    # YouTubeJobProcessor._deactivate_for_missing_handle). NULL for a
    # manual deactivate or a category-level pause. Cleared by any manual
    # per-influencer edit (InfluencerRepo.update_active/update_details),
    # same "explicit action is the new source of truth" rule as
    # paused_by_category -- fixing the handle and saving, or just flipping
    # the row back active, both silently clear this.
    deactivation_reason: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)

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

    # Instagram-only. Null = untried against the Graph API yet, true =
    # Business Discovery works for this handle (a professional/Business or
    # Creator account), false = confirmed personal account, permanently
    # routed to the legacy cookie scraper. Always null for platform="youtube".
    api_supported: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)

    # Per-influencer override for settings.COMMENT_SYNC_DEFAULT_MAX_PER_POST
    # -- null means "use the platform default." A mega-viral post's true
    # comment count can be mathematically unreachable at the scraper's
    # per-account rate limit (see comment_sync.py's cap enforcement); this
    # lets an operator raise the cap for a specific creator worth the
    # extra budget, or lower it for one whose comment volume would
    # otherwise starve every other influencer's sync budget. 0 means
    # unlimited for this influencer specifically, same "0 disables the
    # cap" convention as COMMENT_SYNC_WINDOW_DAYS.
    max_comments_per_post: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

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
    creator: Mapped[Optional["Creator"]] = relationship(
        "Creator", back_populates="influencers"
    )
    profile_snapshots: Mapped[list["ProfileSnapshot"]] = relationship(
        "ProfileSnapshot", back_populates="influencer", cascade="all, delete-orphan"
    )
    # passive_deletes=True -- posts.influencer_id is NOT NULL with an
    # ON DELETE CASCADE at the DB level (InfluencerRepo.delete relies on
    # it), but without this the ORM's default behavior on deleting an
    # Influencer is to SELECT its posts and UPDATE their influencer_id to
    # NULL first (since no ORM-level cascade is declared here), which
    # violates that NOT NULL constraint -- the actual bug behind "delete
    # influencer" 500ing for any account that has posts. This tells
    # SQLAlchemy to leave child rows alone and trust Postgres's cascade to
    # delete them (which in turn cascades further into comments/
    # metrics_snapshots/feature_store/outlier_metrics via their own FKs).
    posts: Mapped[list["Post"]] = relationship(
        "Post", back_populates="influencer", passive_deletes=True
    )

    def __repr__(self) -> str:
        return f"<Influencer id={self.id} handle={self.handle}>"
