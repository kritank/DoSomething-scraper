import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.influencer import Influencer


class Creator(Base):
    """Groups the per-platform Influencer rows (Instagram, YouTube, ...)
    that represent the same real-world creator -- e.g. one creator's
    YouTube channel and Instagram account are two independent Influencer
    rows (different scrape mechanics, different handles, entirely separate
    posts/comments/metrics), linked here only so the dashboard can present
    a combined, cross-platform view of one person/brand.

    Deliberately NOT the owner of category or scrape settings -- those
    stay per-platform on Influencer, since benchmarks and recommendations
    are computed per platform account, not per creator. Linking a creator
    is purely a display/reporting grouping, optional and non-destructive:
    deleting a Creator (see CreatorRepo.delete) unlinks its Influencer rows
    (ON DELETE SET NULL) rather than touching any of their scraped data.
    """

    __tablename__ = "creators"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    influencers: Mapped[list["Influencer"]] = relationship(
        "Influencer", back_populates="creator"
    )

    def __repr__(self) -> str:
        return f"<Creator id={self.id} name={self.name}>"
