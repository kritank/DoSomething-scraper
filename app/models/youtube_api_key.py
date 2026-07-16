import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


class YouTubeApiKey(Base):
    """A pooled YouTube Data API v3 key.

    Unlike InstagramAccount, keys are safely shareable across concurrent
    jobs (a plain API key, not a browser session) -- there is no lease/lock
    here, just a running count of today's quota usage. YouTubeApiKeyRepo
    hands out whichever active key has the most quota remaining.

    status: "active" | "quota_exhausted" | "invalid" | "disabled"
    """

    __tablename__ = "youtube_api_keys"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    label: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    api_key_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active", index=True)

    quota_used_today: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Next YouTube quota reset (midnight Pacific). A key whose reset has
    # passed gets quota_used_today zeroed and, if quota_exhausted, flipped
    # back to active the next time get_usable_key() looks at it.
    quota_reset_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

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
        return f"<YouTubeApiKey label={self.label} status={self.status}>"
