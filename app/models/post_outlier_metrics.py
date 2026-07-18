import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, Float, ForeignKey, Index, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.post import Post


class PostOutlierMetrics(Base):
    """Persisted, re-computed-on-scrape outlier/velocity scoring for a post
    -- one row per post, upserted. See docs/OUTLIERS_PLAN.md Phase 1.

    Unlike FeatureStore (written once at extraction time), these columns are
    re-written every time new PostMetricsSnapshot rows land for the parent
    influencer, and are legitimately NULL early in a post's life (not enough
    prior posts / snapshots yet) -- never a fabricated 0.
    """

    __tablename__ = "post_outlier_metrics"
    __table_args__ = (
        # Backs the cross-creator outliers feed (Content page, sort=outlier_score).
        Index(
            "ix_post_outlier_metrics_score",
            "outlier_score",
            postgresql_where=text("outlier_score IS NOT NULL"),
        ),
    )

    post_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("posts.id", ondelete="CASCADE"),
        primary_key=True,
    )

    # Composite score blending baseline_multiple, velocity and engagement --
    # see docs/OUTLIERS_PLAN.md Phase 2. Starts out equal to baseline_multiple
    # until Phase 2 lands.
    outlier_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # views (or likes fallback) / rolling median of the preceding
    # OUTLIER_LOOKBACK_POSTS posts -- the v1 "N x channel average" figure.
    baseline_multiple: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # True views-per-hour from the two most recent PostMetricsSnapshot rows.
    vph_current: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # Lifetime-average views-per-hour (metric / hours since posted).
    vph_lifetime: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # This post's engagement rate vs the channel's rolling median engagement
    # rate over the same lookback window.
    engagement_ratio: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # Denominator behind baseline_multiple, kept for explainability tooltips.
    baseline_median: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    post: Mapped["Post"] = relationship("Post", back_populates="outlier_metrics")

    def __repr__(self) -> str:
        return f"<PostOutlierMetrics post={self.post_id} score={self.outlier_score}>"
