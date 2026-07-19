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
    # Latest known avatar/channel-thumbnail URL, refreshed on every scrape.
    # None until the first successful scrape.
    profile_pic_url: Optional[str] = None
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

    # Date of the most recent successful scrape (ProfileSnapshot.scraped_at)
    # backing this summary. None only when there's no snapshot at all yet.
    updated_at: Optional[date] = None


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
    # Mean of each post's own (likes + comments) / usable-metric ratio
    # (same views-else-likes fallback as avg_views) -- an average of
    # per-post rates, not total_likes+total_comments/total_views, so one
    # viral post doesn't dominate the figure. None when no post in this
    # format/window has any usable likes/comments/views data at all.
    avg_engagement_rate: Optional[float] = None
    # Share (0..1) of the window's combined long_form + short_form views.
    views_share: float = 0.0


class FormatBreakdownOut(BaseModel):
    window_days: int
    formats: list[FormatStats]
    total_views: int


class SponsorshipStats(BaseModel):
    post_count: int = 0
    # None when no post in this bucket has a usable view-or-likes metric
    # (same views==0-means-no-metric rule as FormatStats.avg_views).
    avg_views: Optional[float] = None
    avg_likes: Optional[float] = None
    avg_comments: Optional[float] = None


class FormatSponsorshipStats(BaseModel):
    # "long_form" | "short_form" -- same folding-live-into-long_form rule
    # as FormatStats.
    format: Literal["long_form", "short_form"]
    organic: SponsorshipStats
    sponsored: SponsorshipStats


class SponsorshipBreakdownOut(BaseModel):
    window_days: int
    # Aggregated across both formats.
    organic: SponsorshipStats
    # "Sponsored" means Instagram's/YouTube's own paid-partnership /
    # paid-product-placement disclosure flag was set on the post --
    # creators who run sponsored content without using that official
    # disclosure tool show up as organic here. See
    # Post.is_paid_partnership and docs/DATABASE_ER_DIAGRAM.md.
    sponsored: SponsorshipStats
    formats: list[FormatSponsorshipStats]


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
    # "long_form" | "short_form" | "live" -- only set for type="top_post"
    # (sourced from the underlying PostPerformance.format). None for
    # "milestone" events, which aren't tied to any single post.
    format: Optional[str] = None


class PostingFrequencyPoint(BaseModel):
    # Bucket start date -- the Monday of that week for bucket="week", or
    # the day itself for bucket="day".
    date: date
    post_count: int


class PostingTimeDistribution(BaseModel):
    # Post counts by day of week, index 0=Monday .. 6=Sunday (Python's
    # datetime.weekday() convention), over the requested window.
    weekday_counts: list[int] = [0] * 7
    # Post counts by hour of day (0-23), in UTC -- posted_at is stored in
    # UTC, so this reflects the creator's UTC posting pattern, not their
    # local audience's clock. Good enough for "do they post consistently
    # around the same time" without claiming timezone precision we don't have.
    hour_counts: list[int] = [0] * 24
    # Joint weekday x hour counts -- matrix[weekday][hour], same indexing
    # as weekday_counts/hour_counts. Powers the weekday-by-hour heatmap;
    # weekday_counts/hour_counts remain as the pre-computed marginals so
    # existing consumers don't need to sum the matrix themselves.
    hourly_weekday_matrix: list[list[int]] = [[0] * 24 for _ in range(7)]
    # None when there are no posts in the window to rank.
    best_weekday: Optional[int] = None
    best_hour: Optional[int] = None
    total_posts: int = 0


class CreatorStatsOut(BaseModel):
    summary: CreatorSummary
    engagement: EngagementOut
    earnings: Optional[EarningsEstimate] = None
    rankings: RankingsOut
    about: AboutOut
