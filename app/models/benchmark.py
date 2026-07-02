import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, Float, ForeignKey, Integer
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.category import Category


class CategoryBenchmark(Base):
    __tablename__ = "category_benchmarks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    category_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("categories.id", ondelete="CASCADE"), nullable=False
    )
    
    avg_followers: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    avg_engagement_rate: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    median_engagement_rate: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    
    avg_caption_length: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    avg_hashtag_count: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    
    avg_posting_freq_week: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    avg_reels_per_week: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    
    best_posting_hour: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    best_posting_weekday: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    
    avg_reel_duration_s: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    
    top_hashtags: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    top_keywords: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    top_posting_patterns: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    
    sample_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
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

    category: Mapped["Category"] = relationship("Category")

    def __repr__(self) -> str:
        return f"<CategoryBenchmark category={self.category_id} computed_at={self.computed_at}>"
