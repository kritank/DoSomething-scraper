"""vidiq-style creator profile stats -- growth, engagement, per-post
performance and in-universe rankings, derived entirely from existing daily
snapshots (ProfileSnapshot, PostMetricsSnapshot). See
docs/CREATOR_STATS_PLAN.md for the design and the data caveats these
queries deliberately encode (rounded YouTube subscriber counts, partial
growth windows, NULL-vs-0 metric semantics).
"""

from __future__ import annotations

import math
import re
import statistics
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.analytics.earnings import instagram_value_per_1k_views_range, youtube_rpm_range
from app.models.comment import Comment
from app.models.feature_store import FeatureStore
from app.models.influencer import Influencer
from app.models.post import Post
from app.models.snapshot import PostMetricsSnapshot, ProfileSnapshot
from app.repositories.post_outlier_metrics_repo import PostOutlierMetricsRepo
from app.schemas.creator_stats import (
    AboutOut,
    CommentEngagementOut,
    CommentEngagementStats,
    CreatorSummary,
    EngagementOut,
    EngagementTrendPoint,
    FollowerRatioPoint,
    FormatBreakdownOut,
    FormatStats,
    GrowthPoint,
    KeyEvent,
    FormatSponsorshipStats,
    PerformanceDecayOut,
    PerformanceDecayPoint,
    PostingFrequencyPoint,
    PostingTimeDistribution,
    PostPerformance,
    RankingEntry,
    RankingsOut,
    ReplyTimeFormatStats,
    ReplyTimeHeatmapOut,
    SponsorshipBreakdownOut,
    SponsorshipStats,
)

# Instagram Reels ("clips") are short-form; everything else (feed photos,
# carousels, IGTV) is long_form -- IGTV in particular is long video, not a
# short. YouTube's product_type is already "video"|"short"|"live" (see
# YouTubeVideo.media_label in app/schemas/youtube.py), so it maps through
# almost as-is.
_INSTAGRAM_SHORT_FORM_PRODUCT_TYPES = {"clips"}


def content_format(platform: str, product_type: Optional[str]) -> str:
    """'long_form' | 'short_form' | 'live'. Pure function, unit-testable --
    see docs/CREATOR_STATS_V2_PLAN.md Phase A1."""
    if platform == "youtube":
        if product_type == "short":
            return "short_form"
        if product_type == "live":
            return "live"
        return "long_form"
    return "short_form" if product_type in _INSTAGRAM_SHORT_FORM_PRODUCT_TYPES else "long_form"

# A video/post needs at least this many prior posts with usable metrics
# before an outlier score is meaningful -- otherwise a channel's 3rd-ever
# video would get a wildly noisy "median of 2" comparison.
MIN_POSTS_FOR_OUTLIER = 5
# How many preceding posts feed the rolling median an outlier score is
# measured against. Matches vidiq's "vs channel average" framing without
# being diluted by years of history on long-running channels.
OUTLIER_LOOKBACK_POSTS = 30
# Candidate pool scanned for sort="top" in get_post_performance -- see the
# comment at its call site for the tradeoff this size encodes.
TOP_SORT_CANDIDATE_POOL = 400
# How many of an influencer's most recent posts recompute_outlier_metrics
# re-scores and persists per call -- see its docstring for why older posts
# aren't rewritten every time.
RECENT_RESCORE_WINDOW = 50
# A post is "fresh" enough for a velocity/hour figure within this window --
# past it, lifetime-average views/hour stops meaning much (see
# PostPerformance.velocity_per_hour docstring).
YOUTUBE_FRESH_WINDOW = timedelta(days=7)
INSTAGRAM_FRESH_WINDOW = timedelta(hours=48)

DEFAULT_ENGAGEMENT_LOOKBACK_POSTS = 12


@dataclass
class _PostMetricPoint:
    post_id: UUID
    posted_at: datetime
    title: Optional[str]
    permalink: Optional[str]
    views: Optional[int]
    likes: Optional[int]
    comments: Optional[int]

    @property
    def outlier_metric(self) -> Optional[int]:
        """views when the platform exposes it, else likes -- Instagram has
        no public view count for image posts, so likes is the only signal.

        Treats views == 0 the same as views is None: confirmed against
        real data that Instagram photo/carousel posts come back with
        views=0 (not NULL) despite having substantial likes -- a 0 there
        means "no view metric for this post type," not "zero views."
        Using it as-is would tank the rolling median toward 0 and silently
        suppress outlier scores for accounts posting mostly photos.
        """
        return self.views if self.views else self.likes


@dataclass
class _OutlierDetail:
    """Everything the batch persistence path (docs/OUTLIERS_PLAN.md Phase 1)
    needs beyond the (outlier_score, velocity_per_hour) tuple the live
    profile endpoint uses -- notably the raw median, kept for explainability
    tooltips, and engagement_ratio, Phase 2's composite-score input."""

    outlier_score: Optional[float]
    velocity_per_hour: Optional[float]
    baseline_median: Optional[float]
    engagement_ratio: Optional[float]


def _point_engagement_rate(point: _PostMetricPoint) -> Optional[float]:
    """(likes + comments) / outlier_metric for one post -- None when either
    side is unmeasurable (metric missing/zero, or both likes and comments
    hidden), never a fabricated 0/0."""
    metric = point.outlier_metric
    if not metric:
        return None
    if point.likes is None and point.comments is None:
        return None
    return ((point.likes or 0) + (point.comments or 0)) / metric


def _compute_outlier_details(
    points_asc: list[_PostMetricPoint], platform: str, now: datetime
) -> dict[UUID, _OutlierDetail]:
    """Pure function (no DB access) so this logic is unit-testable in
    isolation. `points_asc` must be sorted oldest-first."""
    fresh_window = YOUTUBE_FRESH_WINDOW if platform == "youtube" else INSTAGRAM_FRESH_WINDOW
    results: dict[UUID, _OutlierDetail] = {}
    point_ers = [_point_engagement_rate(p) for p in points_asc]

    for i, point in enumerate(points_asc):
        prior = [
            p.outlier_metric
            for p in points_asc[max(0, i - OUTLIER_LOOKBACK_POSTS) : i]
            if p.outlier_metric is not None
        ]
        outlier_score: Optional[float] = None
        baseline_median: Optional[float] = None
        if len(prior) >= MIN_POSTS_FOR_OUTLIER and point.outlier_metric is not None:
            median = statistics.median(prior)
            baseline_median = median
            if median > 0:
                outlier_score = round(point.outlier_metric / median, 2)

        velocity: Optional[float] = None
        if point.outlier_metric is not None:
            age = now - point.posted_at
            if timedelta(0) < age <= fresh_window:
                hours = max(age.total_seconds() / 3600, 1 / 60)
                velocity = round(point.outlier_metric / hours, 2)

        prior_ers = [
            er for er in point_ers[max(0, i - OUTLIER_LOOKBACK_POSTS) : i] if er is not None
        ]
        engagement_ratio: Optional[float] = None
        if len(prior_ers) >= MIN_POSTS_FOR_OUTLIER and point_ers[i] is not None:
            baseline_er = statistics.median(prior_ers)
            if baseline_er > 0:
                engagement_ratio = round(point_ers[i] / baseline_er, 2)

        results[point.post_id] = _OutlierDetail(
            outlier_score=outlier_score,
            velocity_per_hour=velocity,
            baseline_median=baseline_median,
            engagement_ratio=engagement_ratio,
        )

    return results


def _compute_vph_current(
    current_metric: Optional[int],
    current_date: date,
    previous_metric: Optional[int],
    previous_date: date,
) -> Optional[float]:
    """True views(or likes)-per-hour derived from the two most recent daily
    snapshots -- unlike vph_lifetime (metric / age-since-posted), this
    reflects *current* momentum and isn't restricted to freshly-posted
    content (a 2-year-old video suddenly picking up views scores here).
    Snapshots are day-granular, so the rate is coarse but real. A negative
    delta (platform recount/correction) yields None rather than a negative
    rate; same-day pairs (days <= 0) can't produce a rate at all."""
    if current_metric is None or previous_metric is None:
        return None
    days = (current_date - previous_date).days
    if days <= 0:
        return None
    delta = current_metric - previous_metric
    if delta < 0:
        return None
    return round(delta / (days * 24), 2)


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _select_metric_pair(
    platform: str,
    current_views: Optional[int],
    current_likes: Optional[int],
    previous_views: Optional[int],
    previous_likes: Optional[int],
) -> tuple[Optional[int], Optional[int]]:
    """Picks the same metric (views, or likes on the Instagram
    no-view-count-for-this-post-type case) for both snapshots in a pair --
    computing vph_current from views on one day and likes on the next would
    produce a meaningless delta. Mirrors _PostMetricPoint.outlier_metric's
    views-else-likes rule, decided from the *current* snapshot's views."""
    if platform == "instagram" and not current_views:
        return current_likes, previous_likes
    return current_views, previous_views


def _compute_composite_outlier_score(
    baseline_multiple: Optional[float],
    vph_current: Optional[float],
    vph_lifetime: Optional[float],
    engagement_ratio: Optional[float],
) -> Optional[float]:
    """Blends the baseline multiplier with current-momentum and engagement
    signals into one ranking score for the cross-creator outliers feed (see
    docs/OUTLIERS_PLAN.md Phase 2). Degrades gracefully to baseline_multiple
    alone when velocity/engagement can't be computed -- an Instagram photo
    post or a post with only one snapshot still gets a usable score, and
    baseline_multiple is still exposed separately as the explainable "Nx"
    figure the UI badges on.

    Velocity is measured as vph_current relative to the post's *own*
    vph_lifetime (is it accelerating past its own average pace?) rather
    than a cross-post median -- self-relative, always defined once both
    figures exist, and avoids a second full-lookback pass just to build a
    fresh-post velocity distribution.
    """
    if baseline_multiple is None:
        return None
    score = baseline_multiple
    if vph_current is not None and vph_lifetime and vph_lifetime > 0:
        velocity_ratio = vph_current / vph_lifetime
        if velocity_ratio > 1:
            score *= 1 + 0.5 * math.log2(velocity_ratio)
    if engagement_ratio is not None:
        score *= _clamp(engagement_ratio, 0.75, 1.25)
    return round(score, 2)


def _compute_outlier_and_velocity(
    points_asc: list[_PostMetricPoint], platform: str, now: datetime
) -> dict[UUID, tuple[Optional[float], Optional[float]]]:
    """Thin wrapper over `_compute_outlier_details` preserving the
    (outlier_score, velocity_per_hour) tuple contract the live profile
    endpoint (and existing tests) rely on. Returns
    {post_id: (outlier_score, velocity_per_hour)}."""
    details = _compute_outlier_details(points_asc, platform, now)
    return {pid: (d.outlier_score, d.velocity_per_hour) for pid, d in details.items()}


# Round-number follower thresholds milestone events are detected against --
# see _detect_milestones. Denser below 1M than above it: a small/growing
# account crossing 50M is nonsense, but a small/growing account crossing
# 2K/5K/8K is exactly the kind of near-term progress that makes the key
# events feed feel alive rather than going quiet for months between 10K/
# 50K/100K -- coarse thresholds were the main reason events looked like
# they'd "stopped updating" after the initial burst. Capped at 500M since
# no tracked account will ever cross higher, keeping the scan bounded.
MILESTONE_THRESHOLDS = (
    [n * 1_000 for n in range(1, 10)]  # 1K, 2K, ..., 9K
    + [n * 5_000 for n in range(2, 10)]  # 10K, 15K, ..., 45K
    + [n * 10_000 for n in range(5, 10)]  # 50K, 60K, ..., 90K
    + [n * 50_000 for n in range(2, 10)]  # 100K, 150K, ..., 450K
    + [n * 100_000 for n in range(5, 10)]  # 500K, 600K, ..., 900K
    + [n * 1_000_000 for n in range(1, 501)]  # 1M, 2M, ..., 500M
)


def _format_milestone_label(threshold: int) -> str:
    value = f"{threshold // 1_000_000}M" if threshold >= 1_000_000 else f"{threshold // 1_000}K"
    return f"Crossed {value} followers"


def _detect_milestones(series: list[GrowthPoint]) -> list[KeyEvent]:
    """Pure function (no DB access) so this is unit-testable in isolation.
    `series` must be sorted oldest-first (get_growth_series' contract).

    Compares each point against the highest value seen so far (not just
    the immediately preceding point) so a threshold only ever fires once
    -- a sub-count that dips below a crossed threshold and climbs back
    later must not re-fire the same milestone.

    Detection latency: a milestone is only detectable once a new snapshot
    in `series` actually crosses it, so it's bounded by scrape cadence
    (DAILY_SCRAPE_INTERVAL_H, ~24h by default) rather than real time -- a
    threshold crossed mid-day shows up once the next scrape lands, up to
    ~24h later, not the instant it was actually crossed on the platform."""
    events: list[KeyEvent] = []
    high_water_mark: Optional[int] = None
    for point in series:
        if high_water_mark is not None:
            for threshold in MILESTONE_THRESHOLDS:
                if high_water_mark < threshold <= (point.value or 0):
                    events.append(
                        KeyEvent(
                            date=point.date,
                            type="milestone",
                            label=_format_milestone_label(threshold),
                            metric_value=float(threshold),
                        )
                    )
        high_water_mark = max(high_water_mark or 0, point.value or 0)
    return events


def _strip_phantom_zero_lead(points: list[GrowthPoint]) -> list[GrowthPoint]:
    """A leading 0-value point in a followers/total_views series is a
    broken/seed snapshot, not "tracking started at zero" -- no tracked
    account genuinely has 0 followers. Left in, it does two things wrong:
    draws a misleading vertical cliff on the growth chart, and makes
    _detect_milestones treat the very next real point as having crossed
    every single threshold between 0 and that value at once (since
    high_water_mark starts at 0 instead of None) -- a flood of milestone
    events all dated the same day, which is exactly what makes the key
    events feed look like it "shot up once on the first scrape and never
    updated again": the flood was real events firing early and wrong, not
    the feed being broken afterward.

    Strips any leading zero(s) followed by ANY positive value -- not just
    a large jump. A hardcoded >=1000 threshold here previously left the
    phantom zero in place for small/new accounts (e.g. a broken 0 snapshot
    followed by a genuine 450-follower reading), which is exactly the
    account size this docstring's own claim ("no tracked account genuinely
    has 0 followers") says should never be trusted either. Clears the new
    first point's daily_delta since it no longer has a real "previous day"
    to diff against."""
    if len(points) < 2:
        return points
    start = 0
    while start < len(points) - 1 and (points[start].value or 0) == 0 and (points[start + 1].value or 0) > 0:
        start += 1
    if start == 0:
        return points
    rest = points[start:]
    return [rest[0].model_copy(update={"daily_delta": None})] + rest[1:]


def _bucket_posting_frequency(
    posted_ats: list[datetime], bucket: str
) -> list[PostingFrequencyPoint]:
    """Pure function (no DB access) so this is unit-testable in isolation.
    Groups post timestamps into Monday-start calendar weeks (bucket="week")
    or individual days (bucket="day"), independent of dialect-specific
    week-numbering."""
    counts: dict[date, int] = {}
    for posted_at in posted_ats:
        bucket_date = (
            posted_at.date() - timedelta(days=posted_at.weekday())
            if bucket == "week"
            else posted_at.date()
        )
        counts[bucket_date] = counts.get(bucket_date, 0) + 1
    return [PostingFrequencyPoint(date=d, post_count=c) for d, c in sorted(counts.items())]


@dataclass
class _EngagementTrendRow:
    posted_at: datetime
    likes: Optional[int]
    comments: Optional[int]


def _bucket_engagement_trend(
    rows: list[_EngagementTrendRow], followers: int, bucket: str
) -> list[EngagementTrendPoint]:
    """Pure function (no DB access) so this is unit-testable in isolation.
    Same Monday-start week bucketing as _bucket_posting_frequency. Uses one
    fixed `followers` count (the influencer's current total) as the
    denominator for every post regardless of when it was published --
    reconstructing "followers at post time" would need denser
    ProfileSnapshot history than most accounts have yet (see
    docs/CREATOR_STATS_PLAN.md), and EngagementOut already makes this same
    simplification for its single-number engagement rate."""
    post_counts: dict[date, int] = {}
    rate_sums: dict[date, list[float]] = {}
    for row in rows:
        bucket_date = (
            row.posted_at.date() - timedelta(days=row.posted_at.weekday())
            if bucket == "week"
            else row.posted_at.date()
        )
        post_counts[bucket_date] = post_counts.get(bucket_date, 0) + 1
        # Likes-hidden posts are excluded rather than treated as 0 -- same
        # null-safety rule as EngagementOut.
        if row.likes is None and row.comments is None:
            continue
        rate = ((row.likes or 0) + (row.comments or 0)) / followers
        rate_sums.setdefault(bucket_date, []).append(rate)

    points = []
    for d in sorted(post_counts):
        rates = rate_sums.get(d, [])
        points.append(
            EngagementTrendPoint(
                date=d,
                avg_engagement_rate=round(sum(rates) / len(rates), 4) if rates else None,
                post_count=post_counts[d],
            )
        )
    return points


# Age-since-posted buckets for the performance decay curve: dense in the
# first 24h (most velocity decay happens early), coarser out to 30 days,
# with a catch-all tail. Same (upper bound seconds/hours, label) shape as
# _REPLY_TIME_BUCKETS -- here in hours, and None-upper must be last.
_DECAY_BUCKETS: list[tuple[Optional[float], str]] = [
    (1, "0-1h"),
    (3, "1-3h"),
    (6, "3-6h"),
    (12, "6-12h"),
    (24, "12-24h"),
    (48, "1-2d"),
    (96, "2-4d"),
    (168, "4-7d"),
    (336, "7-14d"),
    (720, "14-30d"),
    (None, "30d+"),
]


def _decay_bucket_index(hours: float) -> int:
    for i, (upper, _label) in enumerate(_DECAY_BUCKETS):
        if upper is None or hours < upper:
            return i
    return len(_DECAY_BUCKETS) - 1  # unreachable -- last bucket has upper=None


@dataclass
class _DecayRow:
    hours_since_posted: float
    velocity_per_hour: float


def _aggregate_performance_decay(rows: list[_DecayRow], days: int) -> PerformanceDecayOut:
    """Pure function (no DB access) so this is unit-testable in isolation."""
    bucket_labels = [label for _, label in _DECAY_BUCKETS]
    sums = [0.0] * len(bucket_labels)
    counts = [0] * len(bucket_labels)
    for row in rows:
        idx = _decay_bucket_index(row.hours_since_posted)
        sums[idx] += row.velocity_per_hour
        counts[idx] += 1

    points = [
        PerformanceDecayPoint(
            bucket_label=label,
            avg_velocity_per_hour=round(sums[i] / counts[i], 2) if counts[i] else None,
            sample_size=counts[i],
        )
        for i, label in enumerate(bucket_labels)
    ]
    return PerformanceDecayOut(window_days=days, bucket_labels=bucket_labels, points=points)


@dataclass
class _CommentEngagementRow:
    """Pre-resolved input to _aggregate_comment_engagement -- `format` is
    already folded ("live" -> "long_form"), same convention as _FormatRow."""

    format: str  # "long_form" | "short_form"
    is_from_creator: bool
    is_verified: bool
    child_comment_count: int
    like_count: int


def _empty_comment_bucket() -> dict:
    return {"comment_count": 0, "creator_replies": 0, "verified": 0, "child_sum": 0, "like_sum": 0}


def _comment_stats_from_bucket(format_label: str, bucket: dict) -> CommentEngagementStats:
    n = bucket["comment_count"]
    return CommentEngagementStats(
        format=format_label,
        comment_count=n,
        creator_reply_rate=round(bucket["creator_replies"] / n, 4) if n else None,
        verified_commenter_rate=round(bucket["verified"] / n, 4) if n else None,
        avg_child_comment_count=round(bucket["child_sum"] / n, 2) if n else None,
        avg_likes_per_comment=round(bucket["like_sum"] / n, 2) if n else None,
    )


def _aggregate_comment_engagement(
    rows: list[_CommentEngagementRow], days: int, posts_with_comments: int
) -> CommentEngagementOut:
    """Pure function (no DB access) so this is unit-testable in isolation."""
    overall = _empty_comment_bucket()
    by_format = {"long_form": _empty_comment_bucket(), "short_form": _empty_comment_bucket()}
    for row in rows:
        for bucket in (overall, by_format[row.format]):
            bucket["comment_count"] += 1
            if row.is_from_creator:
                bucket["creator_replies"] += 1
            if row.is_verified:
                bucket["verified"] += 1
            bucket["child_sum"] += row.child_comment_count
            bucket["like_sum"] += row.like_count

    return CommentEngagementOut(
        window_days=days,
        posts_with_comments=posts_with_comments,
        overall=_comment_stats_from_bucket("overall", overall),
        formats=[_comment_stats_from_bucket(fmt, by_format[fmt]) for fmt in ("long_form", "short_form")],
    )


def _aggregate_posting_times(posted_ats: list[datetime]) -> PostingTimeDistribution:
    """Pure function (no DB access) so this is unit-testable in isolation.
    weekday index 0=Monday..6=Sunday (datetime.weekday() convention); hour
    index 0-23 in whatever tz posted_at carries (UTC, as stored)."""
    weekday_counts = [0] * 7
    hour_counts = [0] * 24
    matrix = [[0] * 24 for _ in range(7)]
    for posted_at in posted_ats:
        wd, hr = posted_at.weekday(), posted_at.hour
        weekday_counts[wd] += 1
        hour_counts[hr] += 1
        matrix[wd][hr] += 1

    total = len(posted_ats)
    return PostingTimeDistribution(
        weekday_counts=weekday_counts,
        hour_counts=hour_counts,
        hourly_weekday_matrix=matrix,
        best_weekday=weekday_counts.index(max(weekday_counts)) if total else None,
        best_hour=hour_counts.index(max(hour_counts)) if total else None,
        total_posts=total,
    )


# Time-since-post buckets for the reply-time heatmap: 15-min resolution
# out to 90 min (an audience/comment-response window is front-loaded --
# most reply activity happens early), then coarser 1hr buckets out to
# 3.5h, with a catch-all tail so every measured reply lands somewhere.
# Each tuple is (upper bound in seconds, exclusive) -- None means "no
# upper bound" and must be last.
_REPLY_TIME_BUCKETS: list[tuple[Optional[int], str]] = [
    (900, "0-15m"),
    (1800, "15-30m"),
    (2700, "30-45m"),
    (3600, "45-60m"),
    (4500, "60-75m"),
    (5400, "75-90m"),
    (9000, "1.5-2.5h"),
    (12600, "2.5-3.5h"),
    (None, "3.5h+"),
]


def _reply_time_bucket_index(seconds: int) -> int:
    for i, (upper, _label) in enumerate(_REPLY_TIME_BUCKETS):
        if upper is None or seconds < upper:
            return i
    return len(_REPLY_TIME_BUCKETS) - 1  # unreachable -- last bucket has upper=None


@dataclass
class _ReplyTimeRow:
    """Pre-resolved input to _aggregate_reply_time_heatmap -- `format` is
    already folded ("live" -> "long_form"), same convention as _FormatRow."""

    format: str  # "long_form" | "short_form"
    reply_time_s: int
    # Latest known total comment count for the post (PostMetricsSnapshot),
    # None when the post has never had a metrics snapshot with a comment
    # count -- excluded from bucket_avg_comments rather than counted as 0.
    comments: Optional[int]


def _aggregate_reply_time_heatmap(rows: list[_ReplyTimeRow], days: int) -> ReplyTimeHeatmapOut:
    """Pure function (no DB access) so this is unit-testable in isolation."""
    bucket_labels = [label for _, label in _REPLY_TIME_BUCKETS]
    n_buckets = len(bucket_labels)

    def _empty_bucket() -> dict:
        return {
            "counts": [0] * n_buckets,
            "bucket_reply_times": [[] for _ in range(n_buckets)],
            "bucket_comments": [[] for _ in range(n_buckets)],
            "reply_times": [],
        }

    buckets: dict[str, dict] = {"long_form": _empty_bucket(), "short_form": _empty_bucket()}
    for row in rows:
        bucket = buckets[row.format]
        idx = _reply_time_bucket_index(row.reply_time_s)
        bucket["counts"][idx] += 1
        bucket["bucket_reply_times"][idx].append(row.reply_time_s)
        bucket["reply_times"].append(row.reply_time_s)
        if row.comments is not None:
            bucket["bucket_comments"][idx].append(row.comments)

    formats = []
    for fmt in ("long_form", "short_form"):
        b = buckets[fmt]
        formats.append(
            ReplyTimeFormatStats(
                format=fmt,
                reply_count=len(b["reply_times"]),
                avg_reply_time_s=round(sum(b["reply_times"]) / len(b["reply_times"]), 1)
                if b["reply_times"]
                else None,
                bucket_counts=b["counts"],
                bucket_avg_reply_time_s=[
                    round(sum(times) / len(times), 1) if times else None
                    for times in b["bucket_reply_times"]
                ],
                bucket_avg_comments=[
                    round(sum(comments) / len(comments), 1) if comments else None
                    for comments in b["bucket_comments"]
                ],
            )
        )

    return ReplyTimeHeatmapOut(
        window_days=days, bucket_labels=bucket_labels, formats=formats, total_replies=len(rows)
    )


@dataclass
class _FormatRow:
    """Pre-resolved input to _aggregate_format_breakdown -- `format` is
    already folded ("live" -> "long_form")."""

    format: str  # "long_form" | "short_form"
    views: Optional[int]
    likes: Optional[int]
    comments: Optional[int]


def _aggregate_format_breakdown(rows: list[_FormatRow], days: int) -> FormatBreakdownOut:
    """Pure function (no DB access) so this is unit-testable in isolation."""
    buckets: dict[str, dict] = {
        "long_form": {"post_count": 0, "total_views": 0, "total_likes": 0, "total_comments": 0, "usable_values": [], "engagement_rates": []},
        "short_form": {"post_count": 0, "total_views": 0, "total_likes": 0, "total_comments": 0, "usable_values": [], "engagement_rates": []},
    }
    for row in rows:
        bucket = buckets[row.format]
        bucket["post_count"] += 1
        bucket["total_views"] += row.views or 0
        bucket["total_likes"] += row.likes or 0
        bucket["total_comments"] += row.comments or 0
        # Same views==0-means-no-metric rule as outlier scoring.
        usable = row.views if row.views else row.likes
        if usable is not None:
            bucket["usable_values"].append(usable)
        # Same null-safety as _point_engagement_rate: skip when the usable
        # metric or both likes/comments are unmeasurable, never a
        # fabricated 0/0.
        if usable and (row.likes is not None or row.comments is not None):
            bucket["engagement_rates"].append(((row.likes or 0) + (row.comments or 0)) / usable)

    total_views = sum(b["total_views"] for b in buckets.values())
    formats = []
    for fmt in ("long_form", "short_form"):
        b = buckets[fmt]
        avg_views = round(sum(b["usable_values"]) / len(b["usable_values"]), 1) if b["usable_values"] else None
        avg_engagement_rate = (
            round(sum(b["engagement_rates"]) / len(b["engagement_rates"]), 4)
            if b["engagement_rates"]
            else None
        )
        formats.append(
            FormatStats(
                format=fmt,
                post_count=int(b["post_count"]),
                total_views=int(b["total_views"]),
                total_likes=int(b["total_likes"]),
                total_comments=int(b["total_comments"]),
                avg_views=avg_views,
                avg_engagement_rate=avg_engagement_rate,
                views_share=round(b["total_views"] / total_views, 4) if total_views > 0 else 0.0,
            )
        )

    return FormatBreakdownOut(window_days=days, formats=formats, total_views=int(total_views))


@dataclass
class _SponsorshipRow:
    """Pre-resolved input to _aggregate_sponsorship_breakdown -- `format`
    is already folded ("live" -> "long_form") so the aggregation itself
    doesn't need the influencer's platform."""

    format: str  # "long_form" | "short_form"
    is_paid_partnership: bool
    views: Optional[int]
    likes: Optional[int]
    comments: Optional[int]


def _empty_sponsorship_bucket() -> dict:
    return {"post_count": 0, "total_likes": 0, "total_comments": 0, "usable_values": []}


def _sponsorship_stats_from_bucket(bucket: dict) -> SponsorshipStats:
    post_count = bucket["post_count"]
    return SponsorshipStats(
        post_count=post_count,
        avg_views=round(sum(bucket["usable_values"]) / len(bucket["usable_values"]), 1)
        if bucket["usable_values"]
        else None,
        avg_likes=round(bucket["total_likes"] / post_count, 1) if post_count else None,
        avg_comments=round(bucket["total_comments"] / post_count, 1) if post_count else None,
    )


def _aggregate_sponsorship_breakdown(
    rows: list[_SponsorshipRow], days: int
) -> SponsorshipBreakdownOut:
    """Pure function (no DB access) so this is unit-testable in isolation.
    Buckets posts by is_paid_partnership both overall and crossed with
    format, using the same views-else-likes "usable metric" rule as
    get_format_breakdown."""
    overall = {False: _empty_sponsorship_bucket(), True: _empty_sponsorship_bucket()}
    by_format = {
        "long_form": {False: _empty_sponsorship_bucket(), True: _empty_sponsorship_bucket()},
        "short_form": {False: _empty_sponsorship_bucket(), True: _empty_sponsorship_bucket()},
    }
    for row in rows:
        usable = row.views if row.views else row.likes
        for bucket in (overall[row.is_paid_partnership], by_format[row.format][row.is_paid_partnership]):
            bucket["post_count"] += 1
            bucket["total_likes"] += row.likes or 0
            bucket["total_comments"] += row.comments or 0
            if usable is not None:
                bucket["usable_values"].append(usable)

    return SponsorshipBreakdownOut(
        window_days=days,
        organic=_sponsorship_stats_from_bucket(overall[False]),
        sponsored=_sponsorship_stats_from_bucket(overall[True]),
        formats=[
            FormatSponsorshipStats(
                format=fmt,
                organic=_sponsorship_stats_from_bucket(by_format[fmt][False]),
                sponsored=_sponsorship_stats_from_bucket(by_format[fmt][True]),
            )
            for fmt in ("long_form", "short_form")
        ],
    )


@dataclass
class _InstagramMetricSnapshotRow:
    post_id: UUID
    scraped_at: date
    views: Optional[int]
    likes: Optional[int]


def _interpolate_daily_gaps(anchor_dates: list[date], anchor_values: list[int]) -> list[GrowthPoint]:
    """Fills any gap between two known (date, value) points -- dates more
    than a day apart -- with linearly-interpolated calendar-day
    GrowthPoints, rather than leaving those days absent so the next real
    point's daily_delta silently absorbs the whole gap. A no-op shape for
    an already-dense series (every gap has span_days=1, interpolation at
    offset=0 just returns the anchor itself).

    daily_delta is the difference between each point's own ROUNDED value
    and the previous point's rounded value (a telescoping sum), not two
    independently-rounded deltas -- rounding each step's delta separately
    (e.g. three steps of 3.33 each) can round every single one down and
    lose a unit of the real total (3+3+3=9 when the real total is 10).
    Diffing consecutive rounded cumulative values instead guarantees the
    deltas sum exactly to anchor_values[-1] - anchor_values[0], since both
    endpoints are already exact integers. First point's daily_delta is
    always None, matching every other series in this module."""
    if not anchor_dates:
        return []
    if len(anchor_dates) == 1:
        return [GrowthPoint(date=anchor_dates[0], value=anchor_values[0], daily_delta=None)]

    points: list[GrowthPoint] = []
    previous_rounded: Optional[int] = None
    for i in range(len(anchor_dates) - 1):
        start_day, end_day = anchor_dates[i], anchor_dates[i + 1]
        start_total, end_total = anchor_values[i], anchor_values[i + 1]
        span_days = (end_day - start_day).days
        for offset in range(span_days):  # emits start_day .. end_day - 1
            value = round(start_total + (end_total - start_total) * offset / span_days)
            points.append(
                GrowthPoint(
                    date=start_day + timedelta(days=offset),
                    value=value,
                    daily_delta=(value - previous_rounded) if previous_rounded is not None else None,
                )
            )
            previous_rounded = value

    points.append(
        GrowthPoint(
            date=anchor_dates[-1],
            value=anchor_values[-1],
            daily_delta=(anchor_values[-1] - previous_rounded) if previous_rounded is not None else None,
        )
    )
    return points


def _reconstruct_daily_views_series(
    baseline_values: dict[UUID, int], window_rows: list[_InstagramMetricSnapshotRow]
) -> list[GrowthPoint]:
    """Pure function (no DB access) so this is unit-testable in isolation.

    Instagram has no channel-level lifetime view counter (unlike YouTube's
    ProfileSnapshot.total_views), so a daily views series has to be
    reconstructed bottom-up from per-post snapshots -- the daily-series
    analog of _instagram_views_in_window's single-window total. Forward-
    fills each post's last known usable-metric value (views-else-likes,
    same convention as elsewhere in this module) across days it wasn't
    re-scraped, summing across posts per day to get that day's cumulative
    reconstructed total, then diffs consecutive days for daily_delta.

    `baseline_values` seeds each pre-existing post's contribution with its
    last known value from before the window, so a post that already had
    views doesn't appear to "start from 0" -- a genuinely new post with no
    baseline starts at 0 and jumps to its full value on its first
    snapshot, which is correct: that value is all real growth within the
    window.

    Instagram scraping is opportunistic, not guaranteed-daily -- a day with
    no snapshot for any post is common, not an edge case. Emits one
    GrowthPoint per CALENDAR day across the full window (not just days that
    happen to have a row): a gap between two real data-days has its total
    delta spread evenly across the intervening days instead of dumping the
    whole multi-day jump onto the single day the next snapshot happened to
    land on -- which previously made _get_earnings_series report e.g. 4
    days' worth of view growth as a single day's earnings spike, with $0
    shown on the days actually in between."""
    if not window_rows:
        return []
    current_value = dict(baseline_values)
    by_date: dict[date, list[_InstagramMetricSnapshotRow]] = {}
    for row in window_rows:
        by_date.setdefault(row.scraped_at, []).append(row)

    # The reconstructed cumulative total on each day that actually has a
    # snapshot ("anchor" days) -- _interpolate_daily_gaps then fills every
    # calendar day in between.
    anchor_days = sorted(by_date)
    anchor_totals: list[int] = []
    for day in anchor_days:
        for row in by_date[day]:
            v = row.views if row.views else row.likes
            if v is not None:
                current_value[row.post_id] = v
        anchor_totals.append(sum(current_value.values()))

    return _interpolate_daily_gaps(anchor_days, anchor_totals)


class CreatorStatsService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def _closest_snapshot(
        self, influencer_id: UUID, on_or_before: date
    ) -> Optional[ProfileSnapshot]:
        stmt = (
            select(ProfileSnapshot)
            .where(
                ProfileSnapshot.influencer_id == influencer_id,
                ProfileSnapshot.scraped_at <= on_or_before,
            )
            # scraped_at is date-only -- a second manual "scrape now" the
            # same day produces a second row with the same scraped_at, so
            # ties are broken by created_at to actually get the latest one.
            .order_by(ProfileSnapshot.scraped_at.desc(), ProfileSnapshot.created_at.desc())
            .limit(1)
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def _instagram_views_in_window(
        self, influencer_id: UUID, window_start: date
    ) -> Optional[int]:
        """Instagram has no channel-level lifetime view counter (unlike
        YouTube's ProfileSnapshot.total_views), so "views gained in the
        window" is reconstructed bottom-up from posts: for each post,
        (latest metric value) - (value as of the most recent snapshot
        before the window started, or 0 if the post was itself first
        posted during the window -- its entire lifetime value counts as
        growth in that case, since it didn't exist before the window).
        Falls back to likes for posts with no public view count.

        Posts that predate the window but have no snapshot from before it
        (their only snapshot -- e.g. from a recent one-time backfill --
        happens to fall inside the window) are excluded from the sum
        entirely rather than having their full lifetime value counted:
        with no real baseline, we can't tell how much of that value is
        "new" in this window, and for freshly-backfilled accounts nearly
        every post is in this state, so counting full lifetime totals
        would wildly overstate 28-day growth (confirmed against real
        backfilled data -- see docs/CREATOR_STATS_PLAN.md). This makes
        views_28d an undercount immediately after a backfill, tightening
        to accurate as daily snapshots accumulate a real pre-window
        baseline for each post.
        """
        window_start_dt = datetime.combine(window_start, datetime.min.time(), tzinfo=timezone.utc)
        start_value_sq = (
            select(
                PostMetricsSnapshot.post_id,
                PostMetricsSnapshot.views,
                PostMetricsSnapshot.likes,
                func.row_number()
                .over(
                    partition_by=PostMetricsSnapshot.post_id,
                    order_by=PostMetricsSnapshot.scraped_at.desc(),
                )
                .label("rn"),
            )
            .where(PostMetricsSnapshot.scraped_at < window_start)
            .subquery("start_value")
        )
        latest_value_sq = (
            select(
                PostMetricsSnapshot.post_id,
                PostMetricsSnapshot.views,
                PostMetricsSnapshot.likes,
                func.row_number()
                .over(
                    partition_by=PostMetricsSnapshot.post_id,
                    order_by=PostMetricsSnapshot.scraped_at.desc(),
                )
                .label("rn"),
            )
            .subquery("latest_value")
        )

        stmt = (
            select(
                Post.posted_at,
                latest_value_sq.c.views.label("latest_views"),
                latest_value_sq.c.likes.label("latest_likes"),
                start_value_sq.c.views.label("start_views"),
                start_value_sq.c.likes.label("start_likes"),
            )
            .select_from(Post)
            .join(
                latest_value_sq,
                (latest_value_sq.c.post_id == Post.id) & (latest_value_sq.c.rn == 1),
            )
            .outerjoin(
                start_value_sq,
                (start_value_sq.c.post_id == Post.id) & (start_value_sq.c.rn == 1),
            )
            .where(Post.influencer_id == influencer_id)
        )
        rows = (await self.session.execute(stmt)).all()
        if not rows:
            return None

        total = 0
        for row in rows:
            has_baseline = row.start_views is not None or row.start_likes is not None
            posted_during_window = row.posted_at >= window_start_dt
            if not has_baseline and not posted_during_window:
                continue  # no real baseline for a pre-existing post -- exclude, don't overcount

            if row.latest_views is not None:
                total += row.latest_views - (row.start_views or 0)
            elif row.latest_likes is not None:
                total += row.latest_likes - (row.start_likes or 0)
        return max(total, 0)

    async def _instagram_views_daily_series(
        self, influencer_id: UUID, days: int
    ) -> list[GrowthPoint]:
        """Reconstructs a daily cumulative-views series for Instagram from
        per-post PostMetricsSnapshot rows -- the daily-series analog of
        _instagram_views_in_window's single-window total. See
        _reconstruct_daily_views_series for the actual aggregation (kept
        as a pure function so it's unit-testable without a DB)."""
        cutoff = date.today() - timedelta(days=days)

        baseline_sq = (
            select(
                PostMetricsSnapshot.post_id,
                PostMetricsSnapshot.views,
                PostMetricsSnapshot.likes,
                func.row_number()
                .over(
                    partition_by=PostMetricsSnapshot.post_id,
                    order_by=PostMetricsSnapshot.scraped_at.desc(),
                )
                .label("rn"),
            )
            .where(PostMetricsSnapshot.scraped_at < cutoff)
            .subquery("baseline")
        )
        baseline_stmt = (
            select(baseline_sq.c.post_id, baseline_sq.c.views, baseline_sq.c.likes)
            .select_from(baseline_sq)
            .join(Post, Post.id == baseline_sq.c.post_id)
            .where(baseline_sq.c.rn == 1, Post.influencer_id == influencer_id)
        )
        baseline_rows = (await self.session.execute(baseline_stmt)).all()
        baseline_values = {
            row.post_id: (row.views if row.views else row.likes) or 0 for row in baseline_rows
        }

        window_stmt = (
            select(
                PostMetricsSnapshot.post_id,
                PostMetricsSnapshot.scraped_at,
                PostMetricsSnapshot.views,
                PostMetricsSnapshot.likes,
            )
            .select_from(PostMetricsSnapshot)
            .join(Post, Post.id == PostMetricsSnapshot.post_id)
            .where(Post.influencer_id == influencer_id, PostMetricsSnapshot.scraped_at >= cutoff)
            .order_by(PostMetricsSnapshot.scraped_at.asc())
        )
        window_rows_raw = (await self.session.execute(window_stmt)).all()
        window_rows = [
            _InstagramMetricSnapshotRow(
                post_id=r.post_id, scraped_at=r.scraped_at, views=r.views, likes=r.likes
            )
            for r in window_rows_raw
        ]
        return _reconstruct_daily_views_series(baseline_values, window_rows)

    async def get_summary(self, influencer_id: UUID) -> Optional[CreatorSummary]:
        influencer = (
            await self.session.execute(
                select(Influencer)
                .options(selectinload(Influencer.category))
                .where(Influencer.id == influencer_id)
            )
        ).scalar_one_or_none()
        if influencer is None:
            return None

        latest = await self._closest_snapshot(influencer_id, date.today())
        if latest is None:
            return CreatorSummary(
                influencer_id=influencer_id,
                handle=influencer.handle,
                platform=influencer.platform,
                category_name=influencer.category.name if influencer.category else None,
                profile_pic_url=influencer.profile_pic_url,
                followers=0,
                post_count=0,
            )

        metadata = latest.platform_metadata or {}
        account_age_days = None
        published_at_raw = metadata.get("published_at")
        if published_at_raw:
            try:
                published_at = datetime.fromisoformat(str(published_at_raw).replace("Z", "+00:00"))
                account_age_days = (datetime.now(timezone.utc) - published_at).days
            except ValueError:
                account_age_days = None

        snapshot_7d = await self._closest_snapshot(influencer_id, latest.scraped_at - timedelta(days=7))
        snapshot_28d = await self._closest_snapshot(influencer_id, latest.scraped_at - timedelta(days=28))

        followers_delta_7d = None
        actual_window_days_7 = 0
        if snapshot_7d is not None and snapshot_7d.id != latest.id:
            followers_delta_7d = latest.followers - snapshot_7d.followers
            actual_window_days_7 = (latest.scraped_at - snapshot_7d.scraped_at).days

        followers_delta_28d = None
        actual_window_days_28 = 0
        if snapshot_28d is not None and snapshot_28d.id != latest.id:
            followers_delta_28d = latest.followers - snapshot_28d.followers
            actual_window_days_28 = (latest.scraped_at - snapshot_28d.scraped_at).days

        views_28d: Optional[int] = None
        window_start_28d = latest.scraped_at - timedelta(days=28)
        if influencer.platform == "youtube":
            if snapshot_28d is not None and latest.total_views is not None and snapshot_28d.total_views is not None:
                views_28d = latest.total_views - snapshot_28d.total_views
        else:
            views_28d = await self._instagram_views_in_window(influencer_id, window_start_28d)

        posts_28d_stmt = select(func.count(Post.id)).where(
            Post.influencer_id == influencer_id,
            Post.posted_at >= datetime.now(timezone.utc) - timedelta(days=28),
        )
        posts_28d = (await self.session.execute(posts_28d_stmt)).scalar() or 0

        return CreatorSummary(
            influencer_id=influencer_id,
            handle=influencer.handle,
            platform=influencer.platform,
            category_name=influencer.category.name if influencer.category else None,
            profile_pic_url=influencer.profile_pic_url,
            country=metadata.get("country"),
            account_age_days=account_age_days,
            followers=latest.followers,
            subscribers_hidden=latest.subscribers_hidden,
            total_views=latest.total_views,
            post_count=latest.posts,
            followers_delta_7d=followers_delta_7d,
            actual_window_days_7=actual_window_days_7,
            followers_delta_28d=followers_delta_28d,
            actual_window_days_28=actual_window_days_28,
            views_28d=views_28d,
            posts_per_week=round(posts_28d / 4, 2),
            updated_at=latest.scraped_at,
        )

    async def get_growth_series(
        self, influencer_id: UUID, days: int, metric: str
    ) -> list[GrowthPoint]:
        if metric == "earnings":
            return await self._get_earnings_series(influencer_id, days)

        if metric == "total_views":
            influencer = (
                await self.session.execute(select(Influencer).where(Influencer.id == influencer_id))
            ).scalar_one_or_none()
            if influencer is not None and influencer.platform != "youtube":
                # No channel-level view counter on Instagram -- reconstruct
                # from post snapshots instead of reading ProfileSnapshot.
                # total_views, which is always NULL there.
                points = await self._instagram_views_daily_series(influencer_id, days)
                return _strip_phantom_zero_lead(points)

        column = {
            "followers": ProfileSnapshot.followers,
            "total_views": ProfileSnapshot.total_views,
            "posts": ProfileSnapshot.posts,
        }[metric]

        cutoff = date.today() - timedelta(days=days)
        # scraped_at is date-only -- a re-triggered manual scrape the same
        # day adds a second row for that date, so this dedupes to one
        # point per calendar day (the latest row, by created_at) before
        # plotting; otherwise the chart shows several stacked points for
        # a single day (confirmed against real dev data: a channel
        # manually rescraped 5x in one day produced 5 identical points).
        row_number = (
            func.row_number()
            .over(
                partition_by=ProfileSnapshot.scraped_at,
                order_by=ProfileSnapshot.created_at.desc(),
            )
        )
        subq = (
            select(ProfileSnapshot.scraped_at, column.label("value"), row_number.label("rn"))
            .where(
                ProfileSnapshot.influencer_id == influencer_id,
                ProfileSnapshot.scraped_at >= cutoff,
            )
            .subquery("daily_snapshot")
        )
        stmt = (
            select(subq.c.scraped_at, subq.c.value)
            .where(subq.c.rn == 1)
            .order_by(subq.c.scraped_at.asc())
        )
        rows = (await self.session.execute(stmt)).all()

        points: list[GrowthPoint] = []
        previous_value: Optional[int] = None
        for scraped_at, value in rows:
            if value is None:
                continue
            points.append(
                GrowthPoint(
                    date=scraped_at,
                    value=value,
                    daily_delta=(value - previous_value) if previous_value is not None else None,
                )
            )
            previous_value = value
        # Only for cumulative counters where 0 is never a real value for a
        # tracked account -- "posts" legitimately starts at 0 for a
        # brand-new account with no posts yet, so it's excluded.
        if metric in ("followers", "total_views"):
            points = _strip_phantom_zero_lead(points)
        return points

    async def _get_earnings_series(self, influencer_id: UUID, days: int) -> list[GrowthPoint]:
        """Daily estimated-earnings band: each point is that day's view
        growth times a platform-appropriate per-1000-views rate -- a
        per-day estimate, not a cumulative total. YouTube uses real
        country AdSense RPM benchmarks; Instagram (no ad-revenue-share
        program at this granularity -- see estimate_instagram_earnings'
        docstring for the platform's actual per-sponsored-post economics)
        uses a rough per-view content-value heuristic instead. Both roll
        up from the same total_views daily series -- real for YouTube,
        reconstructed from post snapshots for Instagram (see
        get_growth_series / _instagram_views_daily_series).
        """
        influencer = (
            await self.session.execute(select(Influencer).where(Influencer.id == influencer_id))
        ).scalar_one_or_none()
        if influencer is None:
            return []

        if influencer.platform == "youtube":
            latest = await self._closest_snapshot(influencer_id, date.today())
            country = (latest.platform_metadata or {}).get("country") if latest else None
            low_rate, high_rate = youtube_rpm_range(country)
        else:
            low_rate, high_rate = instagram_value_per_1k_views_range()

        views_series = await self.get_growth_series(influencer_id, days=days, metric="total_views")
        if influencer.platform == "youtube":
            # Instagram's series (_reconstruct_daily_views_series) is
            # already gap-filled/interpolated; YouTube's is a plain read
            # of ProfileSnapshot rows (get_growth_series), which is
            # deliberately NOT gap-filled there (that series also feeds
            # milestone detection, where an interpolated point would
            # fabricate a threshold crossing that never really happened
            # on that day) -- interpolate only for this earnings-specific
            # consumption, so a missed scrape's view growth spreads across
            # the days it actually happened over instead of landing as a
            # single-day spike with $0 on the skipped days.
            dated = [(p.date, p.value) for p in views_series if p.value is not None]
            views_series = _interpolate_daily_gaps([d for d, _ in dated], [v for _, v in dated])
        points: list[GrowthPoint] = []
        for point in views_series:
            if point.daily_delta is None or point.daily_delta < 0:
                continue  # first point has no delta yet; a negative delta means a data anomaly, not real "negative views"
            points.append(
                GrowthPoint(
                    date=point.date,
                    value_low=round(point.daily_delta * low_rate / 1000, 2),
                    value_high=round(point.daily_delta * high_rate / 1000, 2),
                )
            )
        return points

    async def get_engagement_rate(
        self, influencer_id: UUID, last_n_posts: int = DEFAULT_ENGAGEMENT_LOOKBACK_POSTS
    ) -> EngagementOut:
        influencer = (
            await self.session.execute(select(Influencer).where(Influencer.id == influencer_id))
        ).scalar_one_or_none()
        latest = await self._closest_snapshot(influencer_id, date.today())
        if influencer is None or latest is None or latest.subscribers_hidden or latest.followers <= 0:
            return EngagementOut(lookback_posts=last_n_posts)

        latest_metric_sq = (
            select(
                PostMetricsSnapshot.post_id,
                PostMetricsSnapshot.likes,
                PostMetricsSnapshot.comments,
                func.row_number()
                .over(
                    partition_by=PostMetricsSnapshot.post_id,
                    order_by=PostMetricsSnapshot.scraped_at.desc(),
                )
                .label("rn"),
            )
            .subquery("latest_metric")
        )

        stmt = (
            select(latest_metric_sq.c.likes, latest_metric_sq.c.comments)
            .select_from(Post)
            .join(
                latest_metric_sq,
                (latest_metric_sq.c.post_id == Post.id) & (latest_metric_sq.c.rn == 1),
            )
            .where(Post.influencer_id == influencer_id)
            .order_by(Post.posted_at.desc())
            .limit(last_n_posts)
        )
        rows = (await self.session.execute(stmt)).all()

        # Likes-hidden posts (likes is None) are excluded rather than
        # treated as 0 -- mixing a real 0 with "unknown" would understate
        # the rate for creators who hide likes on some posts.
        usable = [(likes or 0) + (comments or 0) for likes, comments in rows if likes is not None]
        if not usable:
            return EngagementOut(lookback_posts=last_n_posts)

        rate = sum(usable) / len(usable) / latest.followers
        return EngagementOut(
            engagement_rate=round(rate, 4), sample_size=len(usable), lookback_posts=last_n_posts
        )

    async def _fetch_metric_points_asc(
        self, influencer_id: UUID, fetch_count: int
    ) -> tuple[list[_PostMetricPoint], list]:
        """Shared by get_post_performance and recompute_outlier_metrics --
        the last `fetch_count` posts (by posted_at) with their latest
        metrics snapshot, oldest-first. Returns (points_asc, raw_rows_asc)
        -- callers that need Post.product_type (for content_format) use the
        raw rows; the pure-function scoring path only needs points_asc."""
        latest_metric_sq = (
            select(
                PostMetricsSnapshot.post_id,
                PostMetricsSnapshot.views,
                PostMetricsSnapshot.likes,
                PostMetricsSnapshot.comments,
                func.row_number()
                .over(
                    partition_by=PostMetricsSnapshot.post_id,
                    order_by=PostMetricsSnapshot.scraped_at.desc(),
                )
                .label("rn"),
            )
            .subquery("latest_metric")
        )
        stmt = (
            select(
                Post.id,
                Post.title,
                Post.caption,
                Post.permalink,
                Post.posted_at,
                Post.product_type,
                latest_metric_sq.c.views,
                latest_metric_sq.c.likes,
                latest_metric_sq.c.comments,
            )
            .select_from(Post)
            .outerjoin(
                latest_metric_sq,
                (latest_metric_sq.c.post_id == Post.id) & (latest_metric_sq.c.rn == 1),
            )
            .where(Post.influencer_id == influencer_id)
            .order_by(Post.posted_at.desc())
            .limit(fetch_count)
        )
        rows = (await self.session.execute(stmt)).all()
        rows_asc = list(reversed(rows))
        return [
            _PostMetricPoint(
                post_id=row.id,
                posted_at=row.posted_at,
                title=row.title or row.caption,
                permalink=row.permalink,
                views=row.views,
                likes=row.likes,
                comments=row.comments,
            )
            for row in rows_asc
        ], rows_asc

    async def get_post_performance(
        self,
        influencer_id: UUID,
        limit: int = 20,
        content_format_filter: Optional[str] = None,
        sort: str = "latest",
    ) -> list[PostPerformance]:
        influencer = (
            await self.session.execute(select(Influencer).where(Influencer.id == influencer_id))
        ).scalar_one_or_none()
        if influencer is None:
            return []

        # Outlier medians are always computed over ALL formats (a Short's
        # views are still compared against the channel's overall median,
        # matching vidiq) -- content_format_filter only narrows what's
        # returned, applied client-side after scoring. When filtering,
        # fetch a much larger candidate pool so `limit` filtered posts can
        # actually be found even on a channel that's mostly one format.
        #
        # sort="top" re-ranks by outlier_score/views instead of recency, so
        # it needs a much wider candidate pool than "latest" -- otherwise
        # it could only ever find "top of the last `limit` posts" rather
        # than anything resembling top-of-all-time. TOP_SORT_CANDIDATE_POOL
        # trades off against outlier_score staying correct (it needs the
        # OUTLIER_LOOKBACK_POSTS immediately preceding each candidate,
        # which this single posted_at-ordered fetch already provides) vs.
        # not scanning a channel's entire multi-thousand-post history on
        # every request.
        if sort == "top":
            fetch_count = TOP_SORT_CANDIDATE_POOL * (2 if content_format_filter else 1)
        else:
            fetch_count = (limit * 8 if content_format_filter else limit) + OUTLIER_LOOKBACK_POSTS

        points_asc, rows_asc = await self._fetch_metric_points_asc(influencer_id, fetch_count)
        formats_by_post: dict[UUID, str] = {
            row.id: content_format(influencer.platform, row.product_type) for row in rows_asc
        }
        now = datetime.now(timezone.utc)
        scores = _compute_outlier_and_velocity(points_asc, influencer.platform, now)

        ordered = list(reversed(points_asc))
        if content_format_filter:
            ordered = [p for p in ordered if formats_by_post[p.post_id] == content_format_filter]
        if sort == "top":
            ordered = sorted(
                ordered,
                key=lambda p: (scores[p.post_id][0] if scores[p.post_id][0] is not None else -1, p.views or p.likes or 0),
                reverse=True,
            )
        newest_first = ordered[:limit]

        # True current velocity (docs/OUTLIERS_PLAN.md Phase 2) -- only
        # computed for the page actually being returned (<= limit posts),
        # not the whole candidate pool, since it needs a snapshot-pair
        # query per post. Falls back to the age-restricted lifetime-average
        # figure (scores[...][1]) for posts with only one snapshot so far
        # (freshly posted, no delta yet) -- otherwise None, meaning "not
        # enough scrape history yet", not "too old".
        vph_by_post = await self._compute_vph_current_by_post(
            [p.post_id for p in newest_first], influencer.platform
        )

        return [
            PostPerformance(
                post_id=p.post_id,
                title=p.title,
                permalink=p.permalink,
                posted_at=p.posted_at.isoformat(),
                views=p.views,
                likes=p.likes,
                comments=p.comments,
                outlier_score=scores[p.post_id][0],
                velocity_per_hour=(
                    vph_by_post[p.post_id]
                    if vph_by_post[p.post_id] is not None
                    else scores[p.post_id][1]
                ),
                format=formats_by_post[p.post_id],
            )
            for p in newest_first
        ]

    async def _fetch_last_two_snapshots(
        self, post_ids: list[UUID]
    ) -> dict[UUID, list[tuple[date, Optional[int], Optional[int]]]]:
        """For each post_id, its up-to-2 most recent *distinct-day* metrics
        snapshots (views, likes), newest first -- the raw material for true
        VPH (docs/OUTLIERS_PLAN.md Phase 2). Same-day duplicate snapshots
        are deduped by created_at DESC first, matching the convention used
        elsewhere in this module."""
        if not post_ids:
            return {}
        daily = (
            select(
                PostMetricsSnapshot.post_id,
                PostMetricsSnapshot.scraped_at,
                PostMetricsSnapshot.views,
                PostMetricsSnapshot.likes,
                func.row_number()
                .over(
                    partition_by=(PostMetricsSnapshot.post_id, PostMetricsSnapshot.scraped_at),
                    order_by=PostMetricsSnapshot.created_at.desc(),
                )
                .label("day_rn"),
            )
            .where(PostMetricsSnapshot.post_id.in_(post_ids))
            .subquery("daily")
        )
        ranked = (
            select(
                daily.c.post_id,
                daily.c.scraped_at,
                daily.c.views,
                daily.c.likes,
                func.row_number()
                .over(partition_by=daily.c.post_id, order_by=daily.c.scraped_at.desc())
                .label("rn"),
            )
            .where(daily.c.day_rn == 1)
            .subquery("ranked")
        )
        stmt = select(ranked).where(ranked.c.rn <= 2)
        rows = (await self.session.execute(stmt)).all()

        result: dict[UUID, list[tuple[date, Optional[int], Optional[int]]]] = {}
        for row in rows:
            result.setdefault(row.post_id, []).append((row.scraped_at, row.views, row.likes))
        for pid, snaps in result.items():
            snaps.sort(key=lambda s: s[0], reverse=True)
        return result

    async def _compute_vph_current_by_post(
        self, post_ids: list[UUID], platform: str
    ) -> dict[UUID, Optional[float]]:
        """True current velocity (docs/OUTLIERS_PLAN.md Phase 2) for a batch
        of posts, keyed by post_id -- None where fewer than 2 distinct-day
        snapshots exist yet. Shared by recompute_outlier_metrics (batch
        persistence) and get_post_performance (the live profile endpoint),
        so a post's velocity doesn't drift depending on which path
        computed it."""
        snapshots_by_post = await self._fetch_last_two_snapshots(post_ids)
        result: dict[UUID, Optional[float]] = {}
        for post_id in post_ids:
            snaps = snapshots_by_post.get(post_id, [])
            if len(snaps) < 2:
                result[post_id] = None
                continue
            (cur_date, cur_views, cur_likes), (prev_date, prev_views, prev_likes) = snaps[0], snaps[1]
            cur_metric, prev_metric = _select_metric_pair(platform, cur_views, cur_likes, prev_views, prev_likes)
            result[post_id] = _compute_vph_current(cur_metric, cur_date, prev_metric, prev_date)
        return result

    async def recompute_outlier_metrics(self, influencer_id: UUID) -> int:
        """Batch counterpart to get_post_performance's live scoring --
        persists baseline_multiple/vph_current/vph_lifetime/engagement_ratio
        and a blended composite outlier_score into post_outlier_metrics for
        an influencer's recent posts. Called after a scrape lands new
        PostMetricsSnapshot rows (see JobProcessor._record_metrics_snapshot)
        and by scripts/backfill_outlier_metrics.py. See
        docs/OUTLIERS_PLAN.md Phase 1/2. Returns the number of posts
        upserted.

        Only re-scores the last RECENT_RESCORE_WINDOW posts, not full
        history: older posts' medians don't meaningfully shift once their
        surrounding window is stable, and rescanning a channel's entire
        multi-thousand-post history on every scrape doesn't pay for itself.
        """
        influencer = (
            await self.session.execute(select(Influencer).where(Influencer.id == influencer_id))
        ).scalar_one_or_none()
        if influencer is None:
            return 0

        points_asc, _ = await self._fetch_metric_points_asc(
            influencer_id, RECENT_RESCORE_WINDOW + OUTLIER_LOOKBACK_POSTS
        )
        if not points_asc:
            return 0

        now = datetime.now(timezone.utc)
        details = _compute_outlier_details(points_asc, influencer.platform, now)

        # Only the most recent RECENT_RESCORE_WINDOW posts are written --
        # the leading OUTLIER_LOOKBACK_POSTS exist purely to feed those
        # posts' rolling medians and don't need their own rows rewritten.
        to_persist = points_asc[-RECENT_RESCORE_WINDOW:]
        vph_by_post = await self._compute_vph_current_by_post(
            [p.post_id for p in to_persist], influencer.platform
        )

        rows = []
        for p in to_persist:
            detail = details[p.post_id]
            vph_current = vph_by_post[p.post_id]

            outlier_score = _compute_composite_outlier_score(
                baseline_multiple=detail.outlier_score,
                vph_current=vph_current,
                vph_lifetime=detail.velocity_per_hour,
                engagement_ratio=detail.engagement_ratio,
            )
            rows.append(
                {
                    "post_id": p.post_id,
                    "outlier_score": outlier_score,
                    "baseline_multiple": detail.outlier_score,
                    "vph_current": vph_current,
                    "vph_lifetime": detail.velocity_per_hour,
                    "engagement_ratio": detail.engagement_ratio,
                    "baseline_median": detail.baseline_median,
                }
            )
        await PostOutlierMetricsRepo(self.session).upsert_many(rows)
        return len(rows)

    async def get_format_breakdown(self, influencer_id: UUID, days: int) -> Optional[FormatBreakdownOut]:
        influencer = (
            await self.session.execute(select(Influencer).where(Influencer.id == influencer_id))
        ).scalar_one_or_none()
        if influencer is None:
            return None

        latest_metric_sq = (
            select(
                PostMetricsSnapshot.post_id,
                PostMetricsSnapshot.views,
                PostMetricsSnapshot.likes,
                PostMetricsSnapshot.comments,
                func.row_number()
                .over(
                    partition_by=PostMetricsSnapshot.post_id,
                    order_by=PostMetricsSnapshot.scraped_at.desc(),
                )
                .label("rn"),
            )
            .subquery("latest_metric")
        )
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        stmt = (
            select(
                Post.product_type,
                latest_metric_sq.c.views,
                latest_metric_sq.c.likes,
                latest_metric_sq.c.comments,
            )
            .select_from(Post)
            .outerjoin(
                latest_metric_sq,
                (latest_metric_sq.c.post_id == Post.id) & (latest_metric_sq.c.rn == 1),
            )
            .where(Post.influencer_id == influencer_id, Post.posted_at >= cutoff)
        )
        rows = (await self.session.execute(stmt)).all()

        format_rows = []
        for row in rows:
            fmt = content_format(influencer.platform, row.product_type)
            if fmt == "live":
                fmt = "long_form"  # folded into long_form for this breakdown, see FormatStats
            format_rows.append(
                _FormatRow(format=fmt, views=row.views, likes=row.likes, comments=row.comments)
            )

        return _aggregate_format_breakdown(format_rows, days)

    async def get_sponsorship_breakdown(
        self, influencer_id: UUID, days: int
    ) -> Optional[SponsorshipBreakdownOut]:
        """Officially-disclosed sponsored (Post.is_paid_partnership) vs
        organic performance, overall and crossed with format. Undercounts
        real sponsorships -- only catches posts where the creator used the
        platform's own paid-partnership/paid-promotion disclosure tool --
        see Post.is_paid_partnership and SponsorshipBreakdownOut's docstring."""
        influencer = (
            await self.session.execute(select(Influencer).where(Influencer.id == influencer_id))
        ).scalar_one_or_none()
        if influencer is None:
            return None

        latest_metric_sq = (
            select(
                PostMetricsSnapshot.post_id,
                PostMetricsSnapshot.views,
                PostMetricsSnapshot.likes,
                PostMetricsSnapshot.comments,
                func.row_number()
                .over(
                    partition_by=PostMetricsSnapshot.post_id,
                    order_by=PostMetricsSnapshot.scraped_at.desc(),
                )
                .label("rn"),
            )
            .subquery("latest_metric")
        )
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        stmt = (
            select(
                Post.product_type,
                Post.is_paid_partnership,
                latest_metric_sq.c.views,
                latest_metric_sq.c.likes,
                latest_metric_sq.c.comments,
            )
            .select_from(Post)
            .outerjoin(
                latest_metric_sq,
                (latest_metric_sq.c.post_id == Post.id) & (latest_metric_sq.c.rn == 1),
            )
            .where(Post.influencer_id == influencer_id, Post.posted_at >= cutoff)
        )
        rows = (await self.session.execute(stmt)).all()

        sponsorship_rows = []
        for row in rows:
            fmt = content_format(influencer.platform, row.product_type)
            if fmt == "live":
                fmt = "long_form"
            sponsorship_rows.append(
                _SponsorshipRow(
                    format=fmt,
                    is_paid_partnership=row.is_paid_partnership,
                    views=row.views,
                    likes=row.likes,
                    comments=row.comments,
                )
            )

        return _aggregate_sponsorship_breakdown(sponsorship_rows, days)

    async def get_posting_frequency(
        self, influencer_id: UUID, days: int, bucket: str = "week"
    ) -> list[PostingFrequencyPoint]:
        """How many posts landed per week (or day) over the window --
        answers "are they posting consistently" at a glance, which none of
        the existing growth/format charts show. Bucketed in Python rather
        than a DB date_trunc so "week" always means "Monday-start calendar
        week" regardless of dialect-specific week-numbering quirks."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        stmt = (
            select(Post.posted_at)
            .where(Post.influencer_id == influencer_id, Post.posted_at >= cutoff)
            .order_by(Post.posted_at.asc())
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        return _bucket_posting_frequency(list(rows), bucket)

    async def get_posting_time_distribution(
        self, influencer_id: UUID, days: int
    ) -> PostingTimeDistribution:
        """Post counts by weekday and by hour-of-day (UTC) -- surfaces
        whether a creator has a consistent posting rhythm, using data
        that's already on every Post row (posted_at); no extra table or
        backfill needed."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        stmt = select(Post.posted_at).where(
            Post.influencer_id == influencer_id, Post.posted_at >= cutoff
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        return _aggregate_posting_times(list(rows))

    async def get_reply_time_heatmap(
        self, influencer_id: UUID, days: int
    ) -> Optional[ReplyTimeHeatmapOut]:
        """How quickly the creator replies to comments, bucketed by
        time-since-post and crossed with format -- built entirely from
        FeatureStore.time_to_first_creator_reply_s (real platform comment
        timestamps, computed in comment_sync.py), no new scraping needed."""
        influencer = (
            await self.session.execute(select(Influencer).where(Influencer.id == influencer_id))
        ).scalar_one_or_none()
        if influencer is None:
            return None

        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        latest_metric_sq = (
            select(
                PostMetricsSnapshot.post_id,
                PostMetricsSnapshot.comments,
                func.row_number()
                .over(
                    partition_by=PostMetricsSnapshot.post_id,
                    order_by=PostMetricsSnapshot.scraped_at.desc(),
                )
                .label("rn"),
            )
            .subquery("latest_metric")
        )
        stmt = (
            select(
                Post.product_type,
                FeatureStore.time_to_first_creator_reply_s,
                latest_metric_sq.c.comments,
            )
            .select_from(Post)
            .join(FeatureStore, FeatureStore.post_id == Post.id)
            .outerjoin(
                latest_metric_sq,
                (latest_metric_sq.c.post_id == Post.id) & (latest_metric_sq.c.rn == 1),
            )
            .where(
                Post.influencer_id == influencer_id,
                Post.posted_at >= cutoff,
                FeatureStore.time_to_first_creator_reply_s.is_not(None),
            )
        )
        rows = (await self.session.execute(stmt)).all()

        reply_rows = []
        for row in rows:
            fmt = content_format(influencer.platform, row.product_type)
            if fmt == "live":
                fmt = "long_form"
            reply_rows.append(
                _ReplyTimeRow(
                    format=fmt,
                    reply_time_s=row.time_to_first_creator_reply_s,
                    comments=row.comments,
                )
            )

        return _aggregate_reply_time_heatmap(reply_rows, days)

    async def get_engagement_trend(
        self, influencer_id: UUID, days: int, bucket: str = "week"
    ) -> list[EngagementTrendPoint]:
        """Engagement rate ((likes+comments)/followers), averaged per
        posting-date bucket -- the time-series extension of
        get_engagement_rate, built entirely from existing PostMetricsSnapshot
        data. Empty when there's no usable follower count yet (mirrors
        get_engagement_rate's own guard)."""
        influencer = (
            await self.session.execute(select(Influencer).where(Influencer.id == influencer_id))
        ).scalar_one_or_none()
        latest = await self._closest_snapshot(influencer_id, date.today())
        if influencer is None or latest is None or latest.subscribers_hidden or latest.followers <= 0:
            return []

        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        latest_metric_sq = (
            select(
                PostMetricsSnapshot.post_id,
                PostMetricsSnapshot.likes,
                PostMetricsSnapshot.comments,
                func.row_number()
                .over(
                    partition_by=PostMetricsSnapshot.post_id,
                    order_by=PostMetricsSnapshot.scraped_at.desc(),
                )
                .label("rn"),
            )
            .subquery("latest_metric")
        )
        stmt = (
            select(Post.posted_at, latest_metric_sq.c.likes, latest_metric_sq.c.comments)
            .select_from(Post)
            .outerjoin(
                latest_metric_sq,
                (latest_metric_sq.c.post_id == Post.id) & (latest_metric_sq.c.rn == 1),
            )
            .where(Post.influencer_id == influencer_id, Post.posted_at >= cutoff)
            .order_by(Post.posted_at.asc())
        )
        rows = (await self.session.execute(stmt)).all()
        trend_rows = [
            _EngagementTrendRow(posted_at=row.posted_at, likes=row.likes, comments=row.comments)
            for row in rows
        ]
        return _bucket_engagement_trend(trend_rows, latest.followers, bucket)

    async def get_performance_decay(
        self, influencer_id: UUID, days: int
    ) -> Optional[PerformanceDecayOut]:
        """Cohort views/likes-per-hour decay curve: every PostMetricsSnapshot
        for posts published in the window, bucketed by how many hours old
        the post was at that snapshot. Built as a cohort curve rather than
        per-post -- most posts only get re-scraped a handful of times (see
        docs/analysis backing this feature), so a single post rarely has
        enough snapshots to plot its own decay, but averaging across posts
        per age bucket is reliable with current snapshot volume."""
        influencer = (
            await self.session.execute(select(Influencer).where(Influencer.id == influencer_id))
        ).scalar_one_or_none()
        if influencer is None:
            return None

        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        stmt = (
            select(Post.posted_at, PostMetricsSnapshot.scraped_at, PostMetricsSnapshot.views, PostMetricsSnapshot.likes)
            .select_from(PostMetricsSnapshot)
            .join(Post, Post.id == PostMetricsSnapshot.post_id)
            .where(Post.influencer_id == influencer_id, Post.posted_at >= cutoff)
        )
        rows = (await self.session.execute(stmt)).all()

        decay_rows = []
        for posted_at, scraped_at, views, likes in rows:
            metric = views if views else likes
            if metric is None:
                continue
            # scraped_at is date-only; treat it as end-of-day for the age
            # calculation since the real scrape time within that day isn't
            # recorded -- coarse, but consistent across every snapshot.
            scraped_dt = datetime.combine(scraped_at, datetime.max.time(), tzinfo=timezone.utc)
            hours = (scraped_dt - posted_at).total_seconds() / 3600
            if hours <= 0:
                continue
            decay_rows.append(_DecayRow(hours_since_posted=hours, velocity_per_hour=metric / hours))

        return _aggregate_performance_decay(decay_rows, days)

    async def get_comment_engagement(
        self, influencer_id: UUID, days: int
    ) -> Optional[CommentEngagementOut]:
        """Audience-quality signal built entirely from the comments table:
        creator-reply rate, verified-commenter share, and thread depth,
        overall and crossed with format. Coverage is naturally partial --
        only posts that had comments scraped contribute -- see
        CommentEngagementOut.posts_with_comments."""
        influencer = (
            await self.session.execute(select(Influencer).where(Influencer.id == influencer_id))
        ).scalar_one_or_none()
        if influencer is None:
            return None

        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        stmt = (
            select(
                Post.id,
                Post.product_type,
                Comment.is_from_creator,
                Comment.is_verified,
                Comment.child_comment_count,
                Comment.like_count,
            )
            .select_from(Comment)
            .join(Post, Post.id == Comment.post_id)
            .where(Post.influencer_id == influencer_id, Post.posted_at >= cutoff)
        )
        rows = (await self.session.execute(stmt)).all()

        comment_rows = []
        posts_with_comments = set()
        for post_id, product_type, is_from_creator, is_verified, child_comment_count, like_count in rows:
            posts_with_comments.add(post_id)
            fmt = content_format(influencer.platform, product_type)
            if fmt == "live":
                fmt = "long_form"
            comment_rows.append(
                _CommentEngagementRow(
                    format=fmt,
                    is_from_creator=is_from_creator,
                    is_verified=is_verified,
                    child_comment_count=child_comment_count,
                    like_count=like_count,
                )
            )

        return _aggregate_comment_engagement(comment_rows, days, len(posts_with_comments))

    async def get_follower_ratio_series(
        self, influencer_id: UUID, days: int
    ) -> list[FollowerRatioPoint]:
        """Daily followers/following, plus the derived ratio -- trivial off
        ProfileSnapshot, but not surfaced as its own trend anywhere yet.
        Same same-day dedupe as get_growth_series."""
        cutoff = date.today() - timedelta(days=days)
        row_number = (
            func.row_number()
            .over(
                partition_by=ProfileSnapshot.scraped_at,
                order_by=ProfileSnapshot.created_at.desc(),
            )
        )
        subq = (
            select(
                ProfileSnapshot.scraped_at,
                ProfileSnapshot.followers,
                ProfileSnapshot.following,
                row_number.label("rn"),
            )
            .where(
                ProfileSnapshot.influencer_id == influencer_id,
                ProfileSnapshot.scraped_at >= cutoff,
            )
            .subquery("daily_snapshot")
        )
        stmt = (
            select(subq.c.scraped_at, subq.c.followers, subq.c.following)
            .where(subq.c.rn == 1)
            .order_by(subq.c.scraped_at.asc())
        )
        rows = (await self.session.execute(stmt)).all()
        return [
            FollowerRatioPoint(
                date=scraped_at,
                followers=followers,
                following=following,
                ratio=round(followers / following, 2) if following else None,
            )
            for scraped_at, followers, following in rows
        ]

    async def get_about(self, influencer_id: UUID) -> Optional[AboutOut]:
        influencer = (
            await self.session.execute(select(Influencer).where(Influencer.id == influencer_id))
        ).scalar_one_or_none()
        if influencer is None:
            return None

        latest = await self._closest_snapshot(influencer_id, date.today())
        if latest is None:
            return AboutOut(platform_user_id=influencer.platform_user_id)

        metadata = latest.platform_metadata or {}
        topics = [
            url.rsplit("/", 1)[-1].replace("_", " ")
            for url in (metadata.get("topic_categories") or [])
        ]
        keywords_raw = metadata.get("keywords") or ""
        # brandingSettings keywords come back as one space-delimited string
        # with multi-word keywords double-quoted, e.g. `tech "smart home" review`.
        keywords = [k for k in re.findall(r'"([^"]+)"|(\S+)', keywords_raw) for k in k if k]

        bio_links = [
            link.get("url")
            for link in (latest.bio_links or [])
            if isinstance(link, dict) and link.get("url")
        ]

        # YouTube stores its customUrl slug ("@handle") in external_url, not
        # a real link (see YouTubeParser.parse_channel) -- turn it into a
        # clickable URL here rather than exposing the bare slug to the UI.
        external_url = latest.external_url
        if influencer.platform == "youtube" and external_url and not external_url.startswith("http"):
            external_url = f"https://youtube.com/{external_url}"

        return AboutOut(
            description=latest.biography,
            external_url=external_url,
            bio_links=bio_links,
            country=metadata.get("country"),
            created_at_platform=metadata.get("published_at"),
            topics=topics,
            keywords=keywords,
            is_verified=latest.is_verified,
            is_business_account=latest.is_business_account,
            business_category=latest.business_category_name or latest.category_name,
            made_for_kids=metadata.get("made_for_kids") if influencer.platform == "youtube" else None,
            platform_user_id=influencer.platform_user_id,
        )

    async def get_key_events(self, influencer_id: UUID, days: int) -> list[KeyEvent]:
        influencer = (
            await self.session.execute(select(Influencer).where(Influencer.id == influencer_id))
        ).scalar_one_or_none()
        if influencer is None:
            return []

        events: list[KeyEvent] = []

        # -- top_post events: outlier posts (>=2x) published in the window,
        # capped at 8; if fewer than 3 qualify, fall back to the top 3 by
        # raw views/likes so a quiet channel still gets some markers.
        cutoff_dt = datetime.now(timezone.utc) - timedelta(days=days)
        performance = await self.get_post_performance(influencer_id, limit=200)
        in_window = [p for p in performance if datetime.fromisoformat(p.posted_at) >= cutoff_dt]
        outliers = sorted(
            [p for p in in_window if (p.outlier_score or 0) >= 2],
            key=lambda p: p.outlier_score,
            reverse=True,
        )[:8]
        top_posts = outliers if len(outliers) >= 3 else sorted(
            [p for p in in_window if (p.views or p.likes)],
            key=lambda p: (p.views or p.likes or 0),
            reverse=True,
        )[:3]
        for p in top_posts:
            metric_value = p.views if p.views else p.likes
            label = (p.title or "Untitled post")[:60]
            events.append(
                KeyEvent(
                    date=datetime.fromisoformat(p.posted_at).date(),
                    type="top_post",
                    label=label,
                    post_id=p.post_id,
                    permalink=p.permalink,
                    metric_value=metric_value,
                    format=p.format,
                )
            )

        # -- milestone events: round-number follower crossings, scanned
        # across the deduped daily series (see get_growth_series).
        series = await self.get_growth_series(influencer_id, days=days, metric="followers")
        events.extend(_detect_milestones(series))

        events.sort(key=lambda e: e.date)
        return events

    async def get_rankings(self, influencer_id: UUID) -> RankingsOut:
        influencer = (
            await self.session.execute(select(Influencer).where(Influencer.id == influencer_id))
        ).scalar_one_or_none()
        if influencer is None:
            return RankingsOut()

        latest_followers_sq = (
            select(
                ProfileSnapshot.influencer_id,
                ProfileSnapshot.followers,
                func.row_number()
                .over(
                    partition_by=ProfileSnapshot.influencer_id,
                    order_by=ProfileSnapshot.scraped_at.desc(),
                )
                .label("rn"),
            )
            .subquery("latest_followers")
        )

        async def _rank_by_followers(category_id: Optional[UUID]) -> Optional[RankingEntry]:
            stmt = (
                select(Influencer.id, latest_followers_sq.c.followers)
                .join(
                    latest_followers_sq,
                    (latest_followers_sq.c.influencer_id == Influencer.id)
                    & (latest_followers_sq.c.rn == 1),
                )
                .where(Influencer.platform == influencer.platform, Influencer.is_active.is_(True))
            )
            if category_id is not None:
                stmt = stmt.where(Influencer.category_id == category_id)
            rows = (await self.session.execute(stmt)).all()
            ranked = sorted(rows, key=lambda r: r.followers, reverse=True)
            for idx, row in enumerate(ranked, start=1):
                if row.id == influencer_id:
                    return RankingEntry(rank=idx, out_of=len(ranked))
            return None

        by_followers_overall = await _rank_by_followers(None)
        by_followers_in_category = await _rank_by_followers(influencer.category_id)

        # 28-day view-growth ranking is only computed for YouTube -- it
        # reads straight off ProfileSnapshot.total_views, whereas doing it
        # for every tracked Instagram account would mean running
        # _instagram_views_in_window once per account on every profile
        # view. Not worth the cost for a secondary ranking card; revisit
        # with AnalyticsCache (app/models/analytics_cache.py) if requested.
        by_views_growth_28d_overall: Optional[RankingEntry] = None
        if influencer.platform == "youtube":
            cutoff = date.today() - timedelta(days=28)
            latest_views_sq = (
                select(
                    ProfileSnapshot.influencer_id,
                    ProfileSnapshot.total_views,
                    ProfileSnapshot.scraped_at,
                    func.row_number()
                    .over(
                        partition_by=ProfileSnapshot.influencer_id,
                        order_by=ProfileSnapshot.scraped_at.desc(),
                    )
                    .label("rn"),
                )
                .subquery("latest_views")
            )
            start_views_sq = (
                select(
                    ProfileSnapshot.influencer_id,
                    ProfileSnapshot.total_views,
                    func.row_number()
                    .over(
                        partition_by=ProfileSnapshot.influencer_id,
                        order_by=ProfileSnapshot.scraped_at.desc(),
                    )
                    .label("rn"),
                )
                .where(ProfileSnapshot.scraped_at <= cutoff)
                .subquery("start_views")
            )
            stmt = (
                select(
                    Influencer.id,
                    latest_views_sq.c.total_views.label("latest_views"),
                    start_views_sq.c.total_views.label("start_views"),
                )
                .join(
                    latest_views_sq,
                    (latest_views_sq.c.influencer_id == Influencer.id) & (latest_views_sq.c.rn == 1),
                )
                .outerjoin(
                    start_views_sq,
                    (start_views_sq.c.influencer_id == Influencer.id) & (start_views_sq.c.rn == 1),
                )
                .where(Influencer.platform == "youtube", Influencer.is_active.is_(True))
            )
            rows = (await self.session.execute(stmt)).all()
            # start_views is None for an influencer with no snapshot at or
            # before the cutoff (tracking started less than 28 days ago) --
            # excluded entirely rather than coalesced to 0, same guard as
            # _instagram_views_in_window's docstring: coalescing would
            # count the channel's whole lifetime view total as "28-day
            # growth" and instantly rank it #1 over genuinely fast growers.
            growth = [
                (row.id, row.latest_views - row.start_views)
                for row in rows
                if row.latest_views is not None and row.start_views is not None
            ]
            ranked = sorted(growth, key=lambda r: r[1], reverse=True)
            for idx, (inf_id, _) in enumerate(ranked, start=1):
                if inf_id == influencer_id:
                    by_views_growth_28d_overall = RankingEntry(rank=idx, out_of=len(ranked))
                    break

        return RankingsOut(
            by_followers_overall=by_followers_overall,
            by_followers_in_category=by_followers_in_category,
            by_views_growth_28d_overall=by_views_growth_28d_overall,
        )
