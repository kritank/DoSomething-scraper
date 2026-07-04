import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.post import Post


class FeatureStore(Base):
    __tablename__ = "feature_store"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    post_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("posts.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    
    caption_length: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    word_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    hashtag_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    mention_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    emoji_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    
    has_cta: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    has_question: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    
    keywords: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    detected_language: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    
    posting_hour: Mapped[int] = mapped_column(Integer, nullable=False)
    posting_weekday: Mapped[int] = mapped_column(Integer, nullable=False)
    
    media_type: Mapped[str] = mapped_column(String(32), nullable=False)
    reel_duration_s: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Engagement-timing signals, derived from already-scraped comment data
    # (no extra API calls) once comments are synced for a post.
    first_comment_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    time_to_first_comment_s: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    creator_reply_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    time_to_first_creator_reply_s: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

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
        "Post", back_populates="feature_store"
    )

    def __repr__(self) -> str:
        return f"<FeatureStore post={self.post_id}>"
