"""vidiq-style creator profile stats -- growth, engagement, per-post
performance and in-universe rankings, derived entirely from existing daily
snapshots (ProfileSnapshot, PostMetricsSnapshot). See
docs/CREATOR_STATS_PLAN.md for the design and the data caveats these
queries deliberately encode (rounded YouTube subscriber counts, partial
growth windows, NULL-vs-0 metric semantics).
"""

from __future__ import annotations

import re
import statistics
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.analytics.earnings import youtube_rpm_range
from app.models.influencer import Influencer
from app.models.post import Post
from app.models.snapshot import PostMetricsSnapshot, ProfileSnapshot
from app.schemas.creator_stats import (
    AboutOut,
    CreatorSummary,
    EngagementOut,
    FormatBreakdownOut,
    FormatStats,
    GrowthPoint,
    KeyEvent,
    PostPerformance,
    RankingEntry,
    RankingsOut,
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


def _compute_outlier_and_velocity(
    points_asc: list[_PostMetricPoint], platform: str, now: datetime
) -> dict[UUID, tuple[Optional[float], Optional[float]]]:
    """Pure function (no DB access) so this logic is unit-testable in
    isolation. `points_asc` must be sorted oldest-first. Returns
    {post_id: (outlier_score, velocity_per_hour)}."""
    fresh_window = YOUTUBE_FRESH_WINDOW if platform == "youtube" else INSTAGRAM_FRESH_WINDOW
    results: dict[UUID, tuple[Optional[float], Optional[float]]] = {}

    for i, point in enumerate(points_asc):
        prior = [
            p.outlier_metric
            for p in points_asc[max(0, i - OUTLIER_LOOKBACK_POSTS) : i]
            if p.outlier_metric is not None
        ]
        outlier_score: Optional[float] = None
        if len(prior) >= MIN_POSTS_FOR_OUTLIER and point.outlier_metric is not None:
            median = statistics.median(prior)
            if median > 0:
                outlier_score = round(point.outlier_metric / median, 2)

        velocity: Optional[float] = None
        if point.outlier_metric is not None:
            age = now - point.posted_at
            if timedelta(0) < age <= fresh_window:
                hours = max(age.total_seconds() / 3600, 1 / 60)
                velocity = round(point.outlier_metric / hours, 2)

        results[point.post_id] = (outlier_score, velocity)

    return results


# Round-number follower thresholds milestone events are detected against --
# see _detect_milestones. Capped at 500M since no tracked account will ever
# cross higher, keeping the scan bounded.
MILESTONE_THRESHOLDS = [10_000, 50_000, 100_000, 500_000] + [n * 1_000_000 for n in range(1, 501)]


def _format_milestone_label(threshold: int) -> str:
    value = f"{threshold // 1_000_000}M" if threshold >= 1_000_000 else f"{threshold // 1_000}K"
    return f"Crossed {value} followers"


def _detect_milestones(series: list[GrowthPoint]) -> list[KeyEvent]:
    """Pure function (no DB access) so this is unit-testable in isolation.
    `series` must be sorted oldest-first (get_growth_series' contract).

    Compares each point against the highest value seen so far (not just
    the immediately preceding point) so a threshold only ever fires once
    -- a sub-count that dips below a crossed threshold and climbs back
    later must not re-fire the same milestone."""
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
        )

    async def get_growth_series(
        self, influencer_id: UUID, days: int, metric: str
    ) -> list[GrowthPoint]:
        if metric == "earnings":
            return await self._get_earnings_series(influencer_id, days)

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
        return points

    async def _get_earnings_series(self, influencer_id: UUID, days: int) -> list[GrowthPoint]:
        """Daily estimated-earnings band: each point is that day's view
        growth times the channel's country RPM range -- a per-day
        estimate, not a cumulative total. YouTube only (Instagram earnings
        are per-post, not time-based -- see get_about's docstring in
        docs/CREATOR_STATS_V2_PLAN.md Phase B1); returns [] for Instagram.
        """
        influencer = (
            await self.session.execute(select(Influencer).where(Influencer.id == influencer_id))
        ).scalar_one_or_none()
        if influencer is None or influencer.platform != "youtube":
            return []

        latest = await self._closest_snapshot(influencer_id, date.today())
        country = (latest.platform_metadata or {}).get("country") if latest else None
        low_rpm, high_rpm = youtube_rpm_range(country)

        views_series = await self.get_growth_series(influencer_id, days=days, metric="total_views")
        points: list[GrowthPoint] = []
        for point in views_series:
            if point.daily_delta is None or point.daily_delta < 0:
                continue  # first point has no delta yet; a negative delta means a data anomaly, not real "negative views"
            points.append(
                GrowthPoint(
                    date=point.date,
                    value_low=round(point.daily_delta * low_rpm / 1000, 2),
                    value_high=round(point.daily_delta * high_rpm / 1000, 2),
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

    async def get_post_performance(
        self, influencer_id: UUID, limit: int = 20, content_format_filter: Optional[str] = None
    ) -> list[PostPerformance]:
        influencer = (
            await self.session.execute(select(Influencer).where(Influencer.id == influencer_id))
        ).scalar_one_or_none()
        if influencer is None:
            return []

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

        # Outlier medians are always computed over ALL formats (a Short's
        # views are still compared against the channel's overall median,
        # matching vidiq) -- content_format_filter only narrows what's
        # returned, applied client-side after scoring. When filtering,
        # fetch a much larger candidate pool so `limit` filtered posts can
        # actually be found even on a channel that's mostly one format.
        fetch_count = (limit * 8 if content_format_filter else limit) + OUTLIER_LOOKBACK_POSTS
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

        formats_by_post: dict[UUID, str] = {
            row.id: content_format(influencer.platform, row.product_type) for row in rows_asc
        }
        points_asc = [
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
        ]
        now = datetime.now(timezone.utc)
        scores = _compute_outlier_and_velocity(points_asc, influencer.platform, now)

        newest_first = list(reversed(points_asc))
        if content_format_filter:
            newest_first = [p for p in newest_first if formats_by_post[p.post_id] == content_format_filter]
        newest_first = newest_first[:limit]

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
                velocity_per_hour=scores[p.post_id][1],
                format=formats_by_post[p.post_id],
            )
            for p in newest_first
        ]

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

        buckets: dict[str, dict[str, float]] = {
            "long_form": {"post_count": 0, "total_views": 0, "total_likes": 0, "total_comments": 0, "usable_values": []},
            "short_form": {"post_count": 0, "total_views": 0, "total_likes": 0, "total_comments": 0, "usable_values": []},
        }
        for row in rows:
            fmt = content_format(influencer.platform, row.product_type)
            if fmt == "live":
                fmt = "long_form"  # folded into long_form for this breakdown, see FormatStats
            bucket = buckets[fmt]
            bucket["post_count"] += 1
            bucket["total_views"] += row.views or 0
            bucket["total_likes"] += row.likes or 0
            bucket["total_comments"] += row.comments or 0
            # Same views==0-means-no-metric rule as outlier scoring.
            usable = row.views if row.views else row.likes
            if usable is not None:
                bucket["usable_values"].append(usable)

        total_views = sum(b["total_views"] for b in buckets.values())
        formats = []
        for fmt in ("long_form", "short_form"):
            b = buckets[fmt]
            avg_views = round(sum(b["usable_values"]) / len(b["usable_values"]), 1) if b["usable_values"] else None
            formats.append(
                FormatStats(
                    format=fmt,
                    post_count=int(b["post_count"]),
                    total_views=int(b["total_views"]),
                    total_likes=int(b["total_likes"]),
                    total_comments=int(b["total_comments"]),
                    avg_views=avg_views,
                    views_share=round(b["total_views"] / total_views, 4) if total_views > 0 else 0.0,
                )
            )

        return FormatBreakdownOut(window_days=days, formats=formats, total_views=int(total_views))

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
            growth = [
                (row.id, row.latest_views - (row.start_views or 0))
                for row in rows
                if row.latest_views is not None
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
