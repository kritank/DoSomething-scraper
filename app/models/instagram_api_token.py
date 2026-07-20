import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Float, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


class InstagramApiToken(Base):
    """A pooled Instagram Graph API (Business Discovery) credential.

    Structurally between InstagramAccount (leased, session-based) and
    YouTubeApiKey (shareable, quota-based): like YouTubeApiKey there is no
    lease/lock -- a token is a bearer credential safely usable by several
    concurrent requests -- but usage is tracked via Meta's Business Use
    Case (BUC) rolling-24h window (`buc_usage_pct`) rather than a
    once-daily quota reset, so there is no midnight-Pacific analog of
    YouTubeApiKey.quota_reset_at (see InstagramApiTokenRepo.get_usable_token).

    status: "active" | "cooldown" | "invalid"
    """

    __tablename__ = "instagram_api_tokens"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    label: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    access_token_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    # Our own reader account's IG user id -- required in every Business
    # Discovery request path (the "who is asking" side of the lookup).
    ig_user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    app_id: Mapped[str] = mapped_column(String(64), nullable=False)
    app_secret_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    # "facebook_login" | "instagram_login" -- which Graph API flavor minted
    # this token; determines the refresh call shape (see docs §8/PR2 2.5).
    auth_flavor: Mapped[str] = mapped_column(String(16), nullable=False)
    # Null for a non-expiring Page token (the common case for the
    # facebook_login flavor); set for instagram_login's 60-day tokens.
    token_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active", index=True)
    calls_today: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Rolling-24h BUC cooldown -- unlike YouTubeApiKey.quota_reset_at
    # (fixed midnight-Pacific), this is `now + 1h` set by whichever caller
    # (rate-limit error or proactive high-BUC check) exhausts the token;
    # get_usable_token() flips status back to "active" once it's passed.
    cooldown_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    # Last-seen max percentage across every metric in the response's
    # X-Business-Use-Case-Usage header -- observability only, not itself
    # used to gate get_usable_token (cooldown_until/status already encode
    # that decision at the moment it was made).
    buc_usage_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_success_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_failure_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    failure_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    def __repr__(self) -> str:
        return f"<InstagramApiToken label={self.label} status={self.status}>"
