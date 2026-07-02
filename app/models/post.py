import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.influencer import Influencer
    from app.models.snapshot import PostMetricsSnapshot
    from app.models.feature_store import FeatureStore


class Post(Base):
    __tablename__ = "posts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    influencer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("influencers.id", ondelete="CASCADE"),
        nullable=False,
    )
    shortcode: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    
    caption: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    hashtags: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    mentions: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    
    posted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    permalink: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

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
        "Influencer", backref="posts"
    )
    metrics_snapshots: Mapped[list["PostMetricsSnapshot"]] = relationship(
        "PostMetricsSnapshot", back_populates="post", cascade="all, delete-orphan"
    )
    feature_store: Mapped[Optional["FeatureStore"]] = relationship(
        "FeatureStore", back_populates="post", uselist=False, cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Post id={self.id} shortcode={self.shortcode}>"
