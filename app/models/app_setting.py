import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


class AppSetting(Base):
    """Small runtime-mutable key/value override store.

    Exists specifically because `settings` (app.core.config) is a plain
    in-memory singleton, instantiated once per process from env/.env at
    startup -- the api, worker, and scheduler containers are three
    SEPARATE processes, each with their own copy. Flipping a setting via
    the dashboard only reaches the api container's memory; worker and
    scheduler (the processes that actually dispatch/route scrape jobs)
    would never see it. A DB row is the only thing all three processes
    share, so this is the source of truth for anything that needs to be
    toggled live without a redeploy -- currently just
    "instagram_backend", but built as a generic key/value table rather
    than a single-purpose column so the next such toggle doesn't need its
    own migration.

    Absence of a row for a given key means "no override" -- callers fall
    back to the static `settings.*` default, so a fresh environment
    behaves identically to before this table existed.
    """

    __tablename__ = "app_settings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    key: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    def __repr__(self) -> str:
        return f"<AppSetting key={self.key} value={self.value}>"
