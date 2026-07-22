from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class PostOut(BaseModel):
    id: UUID
    influencer_id: UUID
    handle: str
    platform: str
    shortcode: str
    title: Optional[str] = None
    caption: Optional[str] = None
    permalink: Optional[str] = None
    posted_at: datetime
    likes: Optional[int] = None
    comments: Optional[int] = None
    views: Optional[int] = None
    reposts: Optional[int] = None
    # How many Comment rows we've actually stored for this post (top-level
    # + replies), from Post.comments_synced_count -- compare against
    # `comments` (the platform's own reported count) to see sync
    # completeness, e.g. in the dashboard's posts table. A large gap here
    # usually means the post hit its per-post comment-sync cap (see
    # settings.COMMENT_SYNC_DEFAULT_MAX_PER_POST /
    # Influencer.max_comments_per_post) rather than a sync failure.
    comments_synced: int = 0
    # Cross-creator outliers feed (docs/OUTLIERS_PLAN.md Phase 3) -- from
    # post_outlier_metrics, NULL until enough post history exists to score.
    outlier_score: Optional[float] = None
    baseline_multiple: Optional[float] = None
    vph_current: Optional[float] = None


class PostListOut(BaseModel):
    posts: list[PostOut]
    total: int
