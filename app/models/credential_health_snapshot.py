import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.instagram_account import InstagramAccount
    from app.models.instagram_api_token import InstagramApiToken
    from app.models.youtube_api_key import YouTubeApiKey


class CredentialHealthSnapshot(Base):
    """A periodic point-in-time snapshot of one pooled credential's health
    (an Instagram account or a YouTube API key), taken every
    CRON_RETRY_FAILED tick by app.scheduler.runner.snapshot_credential_health.

    Neither InstagramAccount nor YouTubeApiKey historizes its own status --
    querying them only ever answers "what's true right now". This table
    exists purely so the dashboard can chart health *over time* (e.g. "how
    often did this key sit in quota_exhausted today") without adding that
    burden to the source tables themselves.

    label is denormalized (copied at snapshot time, not joined) so a
    snapshot's history stays readable even after the source account/key
    row is deleted -- ON DELETE SET NULL on both FK columns reflects that:
    losing the live row must never delete its history.
    """

    __tablename__ = "credential_health_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    snapshot_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )
    platform: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    failure_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # YouTube-only -- NULL for Instagram snapshots.
    quota_used_today: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # Instagram Graph API token pool only -- NULL for the other two platforms.
    buc_usage_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

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
    # "instagram_api" platform rows only -- NULL otherwise. A separate
    # platform value (not "instagram") so existing dashboard queries
    # filtering platform="instagram" keep meaning "the cookie pool"
    # unchanged rather than silently including Graph API tokens too.
    instagram_api_token_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("instagram_api_tokens.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    instagram_account: Mapped[Optional["InstagramAccount"]] = relationship("InstagramAccount")
    youtube_api_key: Mapped[Optional["YouTubeApiKey"]] = relationship("YouTubeApiKey")
    instagram_api_token: Mapped[Optional["InstagramApiToken"]] = relationship("InstagramApiToken")

    def __repr__(self) -> str:
        return f"<CredentialHealthSnapshot platform={self.platform} label={self.label} status={self.status}>"
