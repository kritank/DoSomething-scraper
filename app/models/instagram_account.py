import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


class InstagramAccount(Base):
    """A pooled Instagram session, logged in via app.scraper.login_automator
    or by pasting session cookies directly.

    status: "active" | "in_use" | "checkpoint_required" | "disabled" |
            "pending_login" | "login_failed"
    auth_method: "cookies" | "login" -- how the account was registered.
    For "login" accounts, password_encrypted is retained (Fernet, same key
    as cookies) after a successful login too, not just during the pending
    attempt -- enables a future auto-relogin-on-session-expiry capability.

    proxy_encrypted: optional sticky egress proxy pinned per account (Fernet,
    same key as cookies) so login and every scrape request share one IP.
    """

    __tablename__ = "instagram_accounts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    username: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active", index=True)
    auth_method: Mapped[str] = mapped_column(String(16), nullable=False, default="cookies")

    session_cookies_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    session_captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    password_encrypted: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Fernet-encrypted (proxy URLs carry credentials), same key as cookies.
    # Pinned per account: the account's login, checkpoint resolution, and
    # every scrape request all egress through this one proxy so Instagram
    # sees a single consistent IP per identity. NULL = direct connection.
    proxy_encrypted: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    user_agent: Mapped[str] = mapped_column(String(512), nullable=False)
    locale: Mapped[str] = mapped_column(String(16), nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)

    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_success_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_failure_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    failure_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cooldown_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)

    locked_by: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    lease_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

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

    @property
    def has_proxy(self) -> bool:
        """Whether an egress proxy is pinned. Surfaced to the dashboard so an
        operator can see at a glance which accounts are proxied; the proxy URL
        itself is never exposed over the API (it carries credentials)."""
        return bool(self.proxy_encrypted)

    def __repr__(self) -> str:
        return f"<InstagramAccount username={self.username} status={self.status}>"
