import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.instagram_account import InstagramAccount
    from app.models.youtube_api_key import YouTubeApiKey


class ScrapeJob(Base):
    __tablename__ = "scrape_jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    influencer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("influencers.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_s: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # Ticked every JOB_HEARTBEAT_INTERVAL_S by JobProcessor._heartbeat while
    # status == "running", independent of which phase of the scrape is
    # currently executing. reap_stale_jobs() uses staleness of *this*, not
    # total elapsed time since started_at, to detect a genuinely dead
    # worker -- a job legitimately taking a long time never gets falsely
    # reaped as long as heartbeats keep landing.
    last_heartbeat_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    # Set by request_cancel() when a "running" job is asked to stop.
    # JobProcessor._heartbeat notices this on its next tick and signals the
    # in-flight scrape to unwind cooperatively (see JobCancelledError) --
    # this is a request, not a guarantee of instant stop, bounded by
    # roughly one heartbeat interval or one feed-page fetch, whichever the
    # loop reaches first.
    cancel_requested_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    posts_processed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    comments_processed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # YouTube Data API quota units this job consumed (see YouTubeClient.
    # units_used). NULL (not 0) for Instagram jobs -- there's no quota
    # concept there, same "N/A stays None" convention as reposts/likes
    # elsewhere in this schema.
    quota_units_used: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Which pooled credential actually serviced this run -- exactly one of
    # these is ever set, matching the job's influencer's platform. Set once
    # by JobProcessor right after it acquires the leased Instagram account;
    # for YouTube, set from YouTubeClient.last_key_id after the scrape
    # finishes -- if the key rotated mid-job (quota exhaustion), this
    # reflects whichever key was used last, not every key touched.
    # ON DELETE SET NULL: deleting the account/key later must never delete
    # this job's own history.
    instagram_account_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("instagram_accounts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    youtube_api_key_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("youtube_api_keys.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    instagram_account: Mapped[Optional["InstagramAccount"]] = relationship("InstagramAccount")
    youtube_api_key: Mapped[Optional["YouTubeApiKey"]] = relationship("YouTubeApiKey")

    @property
    def scraper_account(self) -> Optional[str]:
        """Human-readable label for whichever credential ran this job --
        the Instagram username or the YouTube key's label. Requires
        instagram_account/youtube_api_key to be eager-loaded (see
        ScrapeJobRepo) -- this is read from an async context where a lazy
        load would raise, not silently trigger one."""
        if self.instagram_account is not None:
            return self.instagram_account.username
        if self.youtube_api_key is not None:
            return self.youtube_api_key.label
        return None

    def __repr__(self) -> str:
        return f"<ScrapeJob id={self.id} status={self.status}>"


class ScrapeRun(Base):
    __tablename__ = "scrape_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    worker_id: Mapped[str] = mapped_column(String(128), nullable=False)
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("scrape_jobs.id", ondelete="CASCADE"), nullable=False
    )
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    
    def __repr__(self) -> str:
        return f"<ScrapeRun job_id={self.job_id} worker_id={self.worker_id}>"
