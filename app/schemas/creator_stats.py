from datetime import date
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel


class CreatorSummary(BaseModel):
    influencer_id: UUID
    handle: str
    platform: str
    category_name: Optional[str] = None
    country: Optional[str] = None
    # Days since the channel/account was created (YouTube: publishedAt from
    # platform_metadata; Instagram: no equivalent, always None).
    account_age_days: Optional[int] = None

    followers: int
    subscribers_hidden: bool = False
    # YouTube only -- lifetime channel view counter. Always None for Instagram.
    total_views: Optional[int] = None
    post_count: int

    # None when there isn't enough snapshot history for the full window --
    # actual_window_days_7/28 report how many days of history actually
    # backed each delta, so the UI can render "(partial)" instead of lying
    # about a full 7/28-day comparison.
    followers_delta_7d: Optional[int] = None
    actual_window_days_7: int = 0
    followers_delta_28d: Optional[int] = None
    actual_window_days_28: int = 0

    # Views gained in the last 28 days. YouTube: delta of the channel's
    # lifetime view counter. Instagram: sum of per-post view/like deltas
    # (see CreatorStatsService._instagram_views_in_window) since Instagram
    # has no channel-level counter.
    views_28d: Optional[int] = None

    posts_per_week: Optional[float] = None


class GrowthPoint(BaseModel):
    date: date
    # None for metric="earnings" (a low/high band, not a point value) --
    # value_low/value_high are populated instead. Populated for every
    # other metric; value_low/value_high stay None there.
    value: Optional[int] = None
    # value - previous point's value; None for the series' first point.
    daily_delta: Optional[int] = None
    value_low: Optional[float] = None
    value_high: Optional[float] = None


class EngagementOut(BaseModel):
    # None when followers are hidden/zero, or no posts have usable
    # (non-NULL) like/comment data yet.
    engagement_rate: Optional[float] = None
    sample_size: int = 0
    lookback_posts: int = 0


class EarningsEstimate(BaseModel):
    low_usd: float
    high_usd: float
    # "monthly_ad_revenue" (YouTube) | "per_sponsored_post" (Instagram).
    basis: Literal["monthly_ad_revenue", "per_sponsored_post"]


class PostPerformance(BaseModel):
    post_id: UUID
    title: Optional[str] = None
    permalink: Optional[str] = None
    posted_at: str
    views: Optional[int] = None
    likes: Optional[int] = None
    comments: Optional[int] = None

    # views (or likes, if views unavailable) divided by the channel's
    # rolling median over its preceding posts. None if fewer than
    # MIN_POSTS_FOR_OUTLIER prior posts exist.
    outlier_score: Optional[float] = None

    # Lifetime-average views-or-likes per hour since posting, only
    # populated for posts still within their "fresh" window (YouTube: 7
    # days, Instagram: 48h). This is a proxy, not a true instantaneous
    # velocity -- see docs/CREATOR_STATS_PLAN.md Phase 5 for the real thing.
    velocity_per_hour: Optional[float] = None

    # "long_form" | "short_form" | "live" -- see
    # app.analytics.creator_stats.content_format.
    format: str = "long_form"


class RankingEntry(BaseModel):
    rank: int
    out_of: int


class RankingsOut(BaseModel):
    # Ranked among OUR tracked influencers on this platform -- never a
    # global/industry rank. Field names and UI copy must keep saying
    # "tracked" to avoid implying a vidiq-style global rank we can't compute.
    by_followers_overall: Optional[RankingEntry] = None
    by_followers_in_category: Optional[RankingEntry] = None
    by_views_growth_28d_overall: Optional[RankingEntry] = None


class FormatStats(BaseModel):
    # "long_form" | "short_form" -- "live" broadcasts fold into long_form
    # for this breakdown (see content_format).
    format: Literal["long_form", "short_form"]
    post_count: int
    total_views: int
    total_likes: int
    total_comments: int
    # None when no post in this format/window has a usable view-or-likes
    # metric (see _PostMetricPoint.outlier_metric for the views==0 rule).
    avg_views: Optional[float] = None
    # Share (0..1) of the window's combined long_form + short_form views.
    views_share: float = 0.0


class FormatBreakdownOut(BaseModel):
    window_days: int
    formats: list[FormatStats]
    total_views: int


class AboutOut(BaseModel):
    description: Optional[str] = None
    external_url: Optional[str] = None
    bio_links: list[str] = []
    country: Optional[str] = None
    # ISO8601 -- YouTube channel creation date (platform_metadata.published_at).
    # Always None for Instagram (the API doesn't expose account creation date).
    created_at_platform: Optional[str] = None
    # YouTube topicCategories Wikipedia URLs, prettified to their last path
    # segment with underscores replaced by spaces. Always [] for Instagram.
    topics: list[str] = []
    # YouTube brandingSettings keywords. Always [] for Instagram.
    keywords: list[str] = []
    is_verified: bool = False
    is_business_account: bool = False
    business_category: Optional[str] = None
    # None for Instagram (not exposed by the scraped fields we store).
    made_for_kids: Optional[bool] = None
    # YouTube channel ID ("UC...") or Instagram numeric pk.
    platform_user_id: Optional[str] = None


class KeyEvent(BaseModel):
    date: date
    # "top_post" (an outlier post published in the window) | "milestone"
    # (a round-number follower threshold crossed in the window).
    type: Literal["top_post", "milestone"]
    label: str
    post_id: Optional[UUID] = None
    permalink: Optional[str] = None
    metric_value: Optional[float] = None


class CreatorStatsOut(BaseModel):
    summary: CreatorSummary
    engagement: EngagementOut
    earnings: Optional[EarningsEstimate] = None
    rankings: RankingsOut
    about: AboutOut
