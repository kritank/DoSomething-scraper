from datetime import date, datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel


class PublicPlatformAccountOut(BaseModel):
    influencer_id: UUID
    platform: str
    handle: str
    followers: int
    posts: int
    is_verified: bool
    category_name: str
    engagement_rate: Optional[float]
    last_updated: datetime
    # YouTube-only (channel country / creation date); always None for
    # Instagram, which doesn't expose either via its API.
    country: Optional[str] = None
    joined_at: Optional[str] = None


class PublicCreatorProfileOut(BaseModel):
    id: UUID
    name: str
    platforms: list[str]
    accounts: list[PublicPlatformAccountOut]
    combined_followers: int
    combined_posts: int


class PublicPostOut(BaseModel):
    post_id: UUID
    platform: str
    title: Optional[str] = None
    permalink: Optional[str] = None
    posted_at: str
    views: Optional[int] = None
    likes: Optional[int] = None
    comments: Optional[int] = None
    # "long_form" | "short_form" | "live"
    format: str = "long_form"


class PublicGrowthPoint(BaseModel):
    date: date
    # None on a day with no snapshot/post data for this metric -- the
    # frontend line chart just skips the point rather than drawing a
    # misleading zero.
    value: Optional[float] = None
    # Only populated for metric="earnings" (value stays None there) -- a
    # daily estimate band, not a cumulative total.
    value_low: Optional[float] = None
    value_high: Optional[float] = None


class PublicGrowthOut(BaseModel):
    metric: str
    days: int
    # Which platforms have their own entry in `series` (excludes the
    # synthetic "combined" key).
    platforms: list[str]
    # Keyed by platform, plus "combined" (present even for a single
    # platform, so the frontend can always read series["combined"] for
    # the "Combined" tab without a special case).
    series: dict[str, list[PublicGrowthPoint]]


class PublicPostingFrequencyPoint(BaseModel):
    # Bucket start date -- the Monday of that week for bucket="week", or
    # the day itself for bucket="day".
    date: date
    post_count: int


class PublicSponsorshipStats(BaseModel):
    post_count: int = 0
    avg_views: Optional[float] = None
    avg_likes: Optional[float] = None
    avg_comments: Optional[float] = None


class PublicFormatSponsorshipStats(BaseModel):
    format: Literal["long_form", "short_form"]
    organic: PublicSponsorshipStats
    sponsored: PublicSponsorshipStats


class PublicSponsorshipOut(BaseModel):
    window_days: int
    organic: PublicSponsorshipStats
    sponsored: PublicSponsorshipStats
    formats: list[PublicFormatSponsorshipStats]


class PublicEngagementTrendPoint(BaseModel):
    date: date
    avg_engagement_rate: Optional[float] = None
    post_count: int = 0


class PublicPerformanceDecayPoint(BaseModel):
    bucket_label: str
    avg_velocity_per_hour: Optional[float] = None
    sample_size: int = 0


class PublicPerformanceDecayOut(BaseModel):
    window_days: int
    bucket_labels: list[str]
    points: list[PublicPerformanceDecayPoint]


class PublicPostingTimeDistributionOut(BaseModel):
    weekday_counts: list[int] = [0] * 7
    hour_counts: list[int] = [0] * 24
    hourly_weekday_matrix: list[list[int]] = [[0] * 24 for _ in range(7)]
    best_weekday: Optional[int] = None
    best_hour: Optional[int] = None
    total_posts: int = 0


class PublicFollowerRatioPoint(BaseModel):
    date: date
    followers: int
    following: int
    # followers/following -- None when following is 0 (division undefined,
    # not "infinite ratio").
    ratio: Optional[float] = None
