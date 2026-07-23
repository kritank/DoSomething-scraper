from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.creator_stats import CreatorStatsService
from app.core.database import get_db
from app.core.exceptions import CreatorNotFoundError
from app.core.simple_cache import get_or_set
from app.repositories.creator_repo import CreatorRepo
from app.repositories.influencer_repo import InfluencerRepo
from app.schemas.public_creator import (
    PublicCreatorProfileOut,
    PublicEngagementTrendPoint,
    PublicFollowerRatioPoint,
    PublicFormatSponsorshipStats,
    PublicGrowthOut,
    PublicGrowthPoint,
    PublicPerformanceDecayOut,
    PublicPerformanceDecayPoint,
    PublicPlatformAccountOut,
    PublicPostingFrequencyPoint,
    PublicPostingTimeDistributionOut,
    PublicPostOut,
    PublicSponsorshipOut,
    PublicSponsorshipStats,
)

router = APIRouter(prefix="/creators", tags=["Creators"])

PlatformFilter = Literal["instagram", "youtube"] | None


async def _resolve_creator_refs(
    id: UUID, creator_repo: CreatorRepo, influencer_repo: InfluencerRepo, platform: PlatformFilter = None
):
    """`id` is either a Creator id (multi-platform grouping) or, when no
    such Creator exists, falls back to treating it as a single Influencer
    id -- mirrors TopInfluencerOut.link_id, which always points to a
    /creators/{id}-shaped route with whichever id the influencer actually
    has. Returns (name, [(influencer_id, platform), ...]), optionally
    restricted to a single linked platform (same "All / YouTube /
    Instagram" toggle every card on the paid dashboard's creator profile
    offers)."""
    try:
        creator = await creator_repo.get_by_id_with_influencers(id)
        name, refs = creator.name, [(i.id, i.platform) for i in creator.influencers]
    except CreatorNotFoundError:
        influencer = await influencer_repo.get_by_id(id)  # raises InfluencerNotFoundError
        name, refs = influencer.handle, [(influencer.id, influencer.platform)]
    if platform:
        refs = [(influencer_id, p) for influencer_id, p in refs if p == platform]
    return name, refs


_PLATFORM_QUERY = Query(
    None, description="Restrict to one linked platform; omit for all linked platforms combined."
)


@router.get("/{id}", response_model=PublicCreatorProfileOut)
async def get_public_creator_profile(id: UUID, response: Response, db: AsyncSession = Depends(get_db)):
    """Public combined creator profile for the marketing site's creator
    detail page. No auth required -- same trust level as GET /influencers/top.

    get_public_accounts reuses the same unbounded leaderboard base query as
    /influencers/top (see that route's docstring), so it's cached here too
    -- short TTL, since the underlying data only changes on scrape, not
    per-request. Cache-Control lets Cloudflare absorb repeat requests
    before they reach this process at all."""
    response.headers["Cache-Control"] = "public, max-age=120, stale-while-revalidate=600"

    async def compute():
        creator_repo = CreatorRepo(db)
        influencer_repo = InfluencerRepo(db)

        name, refs = await _resolve_creator_refs(id, creator_repo, influencer_repo)
        influencer_ids = [influencer_id for influencer_id, _ in refs]

        rows = await influencer_repo.get_public_accounts(influencer_ids)
        if not rows:
            raise CreatorNotFoundError(str(id))

        accounts = [
            PublicPlatformAccountOut(
                influencer_id=row.id,
                platform=row.platform,
                handle=row.handle,
                followers=row.followers,
                posts=row.posts,
                is_verified=row.is_verified,
                category_name=row.category_name,
                engagement_rate=(
                    round(row.avg_engagement / row.followers * 100, 2)
                    if row.avg_engagement is not None and row.followers
                    else None
                ),
                last_updated=row.last_updated,
                country=(row.platform_metadata or {}).get("country"),
                joined_at=(row.platform_metadata or {}).get("published_at"),
            )
            for row in rows
        ]
        return PublicCreatorProfileOut(
            id=id,
            name=name,
            platforms=sorted({a.platform for a in accounts}),
            accounts=accounts,
            combined_followers=sum(a.followers for a in accounts),
            combined_posts=sum(a.posts for a in accounts),
        )

    return await get_or_set(f"public_creator_profile:{id}", ttl_seconds=120, compute=compute)


@router.get("/{id}/posts", response_model=list[PublicPostOut])
async def get_public_creator_posts(
    id: UUID,
    sort: Literal["latest", "top"] = Query("latest", description="'latest' = most recent first, 'top' = highest-performing first."),
    limit: int = Query(6, ge=1, le=20),
    platform: PlatformFilter = _PLATFORM_QUERY,
    db: AsyncSession = Depends(get_db),
):
    """Public recent/top posts for the creator detail page, combining every
    linked platform account (or just one, via `platform`). No auth required
    -- same trust level as GET /influencers/top. Deliberately excludes
    outlier_score/velocity (the paid dashboard's scoring internals) -- 'top'
    sort still uses them server-side, just doesn't expose the numbers."""
    creator_repo = CreatorRepo(db)
    influencer_repo = InfluencerRepo(db)
    stats_service = CreatorStatsService(db)

    _, refs = await _resolve_creator_refs(id, creator_repo, influencer_repo, platform)

    posts: list[PublicPostOut] = []
    for influencer_id, platform in refs:
        performance = await stats_service.get_post_performance(influencer_id, limit=limit, sort=sort)
        posts.extend(
            PublicPostOut(
                post_id=p.post_id,
                platform=platform,
                title=p.title,
                permalink=p.permalink,
                posted_at=p.posted_at,
                views=p.views,
                likes=p.likes,
                comments=p.comments,
                format=p.format,
            )
            for p in performance
        )

    if sort == "latest":
        posts.sort(key=lambda p: p.posted_at, reverse=True)
    else:
        posts.sort(key=lambda p: (p.views or p.likes or 0), reverse=True)

    return posts[:limit]


def _merge_growth_series(
    metric: str, series_by_platform: dict[str, list[PublicGrowthPoint]]
) -> list[PublicGrowthPoint]:
    """Combines per-platform series into one "combined" line. Always
    returns a series (even for a single platform) so the frontend can
    read series["combined"] unconditionally."""
    if len(series_by_platform) <= 1:
        return next(iter(series_by_platform.values()), [])

    all_dates = sorted({p.date for points in series_by_platform.values() for p in points})
    points_by_platform = {
        platform: {p.date: p.value for p in points} for platform, points in series_by_platform.items()
    }

    if metric == "engagement":
        # A rate, not a counter -- combined is the average of whichever
        # platforms reported a value that day, not a sum.
        combined = []
        for d in all_dates:
            values = [v for v in (pts.get(d) for pts in points_by_platform.values()) if v is not None]
            combined.append(PublicGrowthPoint(date=d, value=round(sum(values) / len(values), 2) if values else None))
        return combined

    if metric == "earnings":
        # A daily estimate band, not a cumulative counter -- sum each
        # platform's low/high for days it has a value (no forward-fill;
        # a day with no estimate from a platform genuinely contributed 0).
        low_by_platform = {
            platform: {p.date: p.value_low for p in points} for platform, points in series_by_platform.items()
        }
        high_by_platform = {
            platform: {p.date: p.value_high for p in points} for platform, points in series_by_platform.items()
        }
        combined = []
        for d in all_dates:
            lows = [v for v in (pts.get(d) for pts in low_by_platform.values()) if v is not None]
            highs = [v for v in (pts.get(d) for pts in high_by_platform.values()) if v is not None]
            combined.append(
                PublicGrowthPoint(
                    date=d,
                    value_low=round(sum(lows), 2) if lows else None,
                    value_high=round(sum(highs), 2) if highs else None,
                )
            )
        return combined

    # followers/posts are cumulative counters -- forward-fill each
    # platform's last known value so differing scrape cadences still sum
    # to a sensible combined total on every date instead of dipping
    # whenever only one platform has a fresh snapshot.
    last_value = {platform: None for platform in series_by_platform}
    combined = []
    for d in all_dates:
        total = 0
        any_value = False
        for platform, pts in points_by_platform.items():
            if pts.get(d) is not None:
                last_value[platform] = pts[d]
            if last_value[platform] is not None:
                total += last_value[platform]
                any_value = True
        combined.append(PublicGrowthPoint(date=d, value=total if any_value else None))
    return combined


@router.get("/{id}/growth", response_model=PublicGrowthOut)
async def get_public_creator_growth(
    id: UUID,
    metric: Literal["followers", "posts", "engagement", "total_views", "earnings"] = Query("followers"),
    days: int = Query(7, ge=1, le=3650),
    platform: PlatformFilter = _PLATFORM_QUERY,
    db: AsyncSession = Depends(get_db),
):
    """Public follower/post-count/engagement/view/earnings-estimate history
    for the creator detail page's trend chart. No auth required -- same
    trust level as GET /influencers/top. Reuses the same growth/
    engagement-trend queries as the paid dashboard's charts
    (CreatorStatsService), just without the admin API-key gate and
    without the sponsorship/decay/heatmap widgets those charts sit
    alongside."""
    creator_repo = CreatorRepo(db)
    influencer_repo = InfluencerRepo(db)
    stats_service = CreatorStatsService(db)

    _, refs = await _resolve_creator_refs(id, creator_repo, influencer_repo, platform)

    series_by_platform: dict[str, list[PublicGrowthPoint]] = {}
    for influencer_id, ref_platform in refs:
        if metric == "engagement":
            trend = await stats_service.get_engagement_trend(influencer_id, days=days, bucket="day")
            points = [
                PublicGrowthPoint(date=p.date, value=round(p.avg_engagement_rate * 100, 2) if p.avg_engagement_rate is not None else None)
                for p in trend
            ]
        else:
            growth = await stats_service.get_growth_series(influencer_id, days=days, metric=metric)
            points = [
                PublicGrowthPoint(date=p.date, value=p.value, value_low=p.value_low, value_high=p.value_high)
                for p in growth
            ]
        series_by_platform[ref_platform] = points

    return PublicGrowthOut(
        metric=metric,
        days=days,
        platforms=sorted(series_by_platform.keys()),
        series={**series_by_platform, "combined": _merge_growth_series(metric, series_by_platform)},
    )


def _merge_posting_frequency(
    series_by_platform: dict[str, list[PublicPostingFrequencyPoint]],
) -> list[PublicPostingFrequencyPoint]:
    """Sums post counts across platforms on matching bucket dates -- unlike
    growth's cumulative counters, a post count is never forward-filled
    (a bucket with no post from a platform genuinely contributed 0)."""
    totals: dict = {}
    for points in series_by_platform.values():
        for p in points:
            totals[p.date] = totals.get(p.date, 0) + p.post_count
    return [PublicPostingFrequencyPoint(date=d, post_count=totals[d]) for d in sorted(totals)]


@router.get("/{id}/posting-frequency", response_model=list[PublicPostingFrequencyPoint])
async def get_public_creator_posting_frequency(
    id: UUID,
    days: int = Query(90, ge=1, le=3650),
    bucket: Literal["day", "week"] = Query("week"),
    platform: PlatformFilter = _PLATFORM_QUERY,
    db: AsyncSession = Depends(get_db),
):
    """Public posting-cadence history for the creator detail page. No auth
    required -- same trust level as GET /influencers/top."""
    creator_repo = CreatorRepo(db)
    influencer_repo = InfluencerRepo(db)
    stats_service = CreatorStatsService(db)

    _, refs = await _resolve_creator_refs(id, creator_repo, influencer_repo, platform)

    series_by_platform: dict[str, list[PublicPostingFrequencyPoint]] = {}
    for influencer_id, platform in refs:
        points = await stats_service.get_posting_frequency(influencer_id, days=days, bucket=bucket)
        series_by_platform[platform] = [
            PublicPostingFrequencyPoint(date=p.date, post_count=p.post_count) for p in points
        ]

    return _merge_posting_frequency(series_by_platform)


def _merge_sponsorship_stats(all_stats: list[PublicSponsorshipStats]) -> PublicSponsorshipStats:
    """Post-count-weighted average of the avg_* fields across platforms --
    a straight mean would let a platform with 2 posts skew the figure as
    much as one with 200."""
    total_posts = sum(s.post_count for s in all_stats)
    if total_posts == 0:
        return PublicSponsorshipStats(post_count=0)

    def weighted_avg(get_value):
        weighted = [(s.post_count, get_value(s)) for s in all_stats if get_value(s) is not None]
        weight_sum = sum(w for w, _ in weighted)
        if weight_sum == 0:
            return None
        return round(sum(w * v for w, v in weighted) / weight_sum, 2)

    return PublicSponsorshipStats(
        post_count=total_posts,
        avg_views=weighted_avg(lambda s: s.avg_views),
        avg_likes=weighted_avg(lambda s: s.avg_likes),
        avg_comments=weighted_avg(lambda s: s.avg_comments),
    )


@router.get("/{id}/sponsorship", response_model=PublicSponsorshipOut)
async def get_public_creator_sponsorship(
    id: UUID,
    days: int = Query(90, ge=1, le=3650),
    platform: PlatformFilter = _PLATFORM_QUERY,
    db: AsyncSession = Depends(get_db),
):
    """Public sponsored-vs-organic post performance for the creator detail
    page, overall and crossed with format -- same shape as the paid
    dashboard's chart. No auth required -- same trust level as GET
    /influencers/top."""
    creator_repo = CreatorRepo(db)
    influencer_repo = InfluencerRepo(db)
    stats_service = CreatorStatsService(db)

    _, refs = await _resolve_creator_refs(id, creator_repo, influencer_repo, platform)

    organic_stats: list[PublicSponsorshipStats] = []
    sponsored_stats: list[PublicSponsorshipStats] = []
    long_form_organic: list[PublicSponsorshipStats] = []
    long_form_sponsored: list[PublicSponsorshipStats] = []
    short_form_organic: list[PublicSponsorshipStats] = []
    short_form_sponsored: list[PublicSponsorshipStats] = []
    for influencer_id, _platform in refs:
        breakdown = await stats_service.get_sponsorship_breakdown(influencer_id, days=days)
        if breakdown is None:
            continue
        organic_stats.append(PublicSponsorshipStats(**breakdown.organic.model_dump()))
        sponsored_stats.append(PublicSponsorshipStats(**breakdown.sponsored.model_dump()))
        long_form = next((f for f in breakdown.formats if f.format == "long_form"), None)
        short_form = next((f for f in breakdown.formats if f.format == "short_form"), None)
        if long_form:
            long_form_organic.append(PublicSponsorshipStats(**long_form.organic.model_dump()))
            long_form_sponsored.append(PublicSponsorshipStats(**long_form.sponsored.model_dump()))
        if short_form:
            short_form_organic.append(PublicSponsorshipStats(**short_form.organic.model_dump()))
            short_form_sponsored.append(PublicSponsorshipStats(**short_form.sponsored.model_dump()))

    return PublicSponsorshipOut(
        window_days=days,
        organic=_merge_sponsorship_stats(organic_stats),
        sponsored=_merge_sponsorship_stats(sponsored_stats),
        formats=[
            PublicFormatSponsorshipStats(
                format="long_form",
                organic=_merge_sponsorship_stats(long_form_organic),
                sponsored=_merge_sponsorship_stats(long_form_sponsored),
            ),
            PublicFormatSponsorshipStats(
                format="short_form",
                organic=_merge_sponsorship_stats(short_form_organic),
                sponsored=_merge_sponsorship_stats(short_form_sponsored),
            ),
        ],
    )


def _merge_engagement_trend(
    series_by_platform: dict[str, list[PublicEngagementTrendPoint]],
) -> list[PublicEngagementTrendPoint]:
    """Averages the engagement rate across whichever platforms posted in a
    given bucket (a rate, not a counter -- same rule as the "engagement"
    case in _merge_growth_series), and sums post_count."""
    rates_by_date: dict = {}
    counts_by_date: dict = {}
    for points in series_by_platform.values():
        for p in points:
            counts_by_date[p.date] = counts_by_date.get(p.date, 0) + p.post_count
            if p.avg_engagement_rate is not None:
                rates_by_date.setdefault(p.date, []).append(p.avg_engagement_rate)

    return [
        PublicEngagementTrendPoint(
            date=d,
            avg_engagement_rate=(
                round(sum(rates_by_date[d]) / len(rates_by_date[d]), 4) if d in rates_by_date else None
            ),
            post_count=counts_by_date[d],
        )
        for d in sorted(counts_by_date)
    ]


@router.get("/{id}/engagement-trend", response_model=list[PublicEngagementTrendPoint])
async def get_public_creator_engagement_trend(
    id: UUID,
    days: int = Query(90, ge=1, le=3650),
    bucket: Literal["day", "week"] = Query("week"),
    platform: PlatformFilter = _PLATFORM_QUERY,
    db: AsyncSession = Depends(get_db),
):
    """Public engagement-rate trend for the creator detail page. No auth
    required -- same trust level as GET /influencers/top."""
    creator_repo = CreatorRepo(db)
    influencer_repo = InfluencerRepo(db)
    stats_service = CreatorStatsService(db)

    _, refs = await _resolve_creator_refs(id, creator_repo, influencer_repo, platform)

    series_by_platform: dict[str, list[PublicEngagementTrendPoint]] = {}
    for influencer_id, platform in refs:
        points = await stats_service.get_engagement_trend(influencer_id, days=days, bucket=bucket)
        series_by_platform[platform] = [
            PublicEngagementTrendPoint(
                date=p.date, avg_engagement_rate=p.avg_engagement_rate, post_count=p.post_count
            )
            for p in points
        ]

    return _merge_engagement_trend(series_by_platform)


def _merge_performance_decay(
    window_days: int, by_platform: list[PublicPerformanceDecayOut]
) -> PublicPerformanceDecayOut:
    """Sample-size-weighted average velocity per age bucket -- bucket_label
    ordering/set is a fixed constant (_DECAY_BUCKETS in creator_stats.py),
    so every platform's payload has the same bucket_labels list to align on."""
    if not by_platform:
        return PublicPerformanceDecayOut(window_days=window_days, bucket_labels=[], points=[])

    bucket_labels = by_platform[0].bucket_labels
    points = []
    for i, label in enumerate(bucket_labels):
        bucket_points = [p.points[i] for p in by_platform]
        total_samples = sum(bp.sample_size for bp in bucket_points)
        weighted = [
            (bp.sample_size, bp.avg_velocity_per_hour)
            for bp in bucket_points
            if bp.avg_velocity_per_hour is not None
        ]
        weight_sum = sum(w for w, _ in weighted)
        avg_velocity = round(sum(w * v for w, v in weighted) / weight_sum, 2) if weight_sum else None
        points.append(
            PublicPerformanceDecayPoint(
                bucket_label=label, avg_velocity_per_hour=avg_velocity, sample_size=total_samples
            )
        )

    return PublicPerformanceDecayOut(window_days=window_days, bucket_labels=bucket_labels, points=points)


@router.get("/{id}/performance-decay", response_model=PublicPerformanceDecayOut)
async def get_public_creator_performance_decay(
    id: UUID,
    days: int = Query(90, ge=1, le=3650),
    platform: PlatformFilter = _PLATFORM_QUERY,
    db: AsyncSession = Depends(get_db),
):
    """Public views/likes-per-hour decay curve for the creator detail
    page. No auth required -- same trust level as GET /influencers/top."""
    creator_repo = CreatorRepo(db)
    influencer_repo = InfluencerRepo(db)
    stats_service = CreatorStatsService(db)

    _, refs = await _resolve_creator_refs(id, creator_repo, influencer_repo, platform)

    per_platform: list[PublicPerformanceDecayOut] = []
    for influencer_id, _platform in refs:
        decay = await stats_service.get_performance_decay(influencer_id, days=days)
        if decay is None:
            continue
        per_platform.append(
            PublicPerformanceDecayOut(
                window_days=decay.window_days,
                bucket_labels=decay.bucket_labels,
                points=[
                    PublicPerformanceDecayPoint(
                        bucket_label=p.bucket_label,
                        avg_velocity_per_hour=p.avg_velocity_per_hour,
                        sample_size=p.sample_size,
                    )
                    for p in decay.points
                ],
            )
        )

    return _merge_performance_decay(days, per_platform)


def _merge_posting_times(matrices: list[list[list[int]]]) -> PublicPostingTimeDistributionOut:
    """Sums weekday x hour matrices across platforms, then recomputes the
    marginals (weekday_counts/hour_counts) and best_weekday/best_hour from
    the merged matrix -- same derivation _aggregate_posting_times uses,
    just applied post-merge instead of on raw posted_at timestamps."""
    matrix = [[0] * 24 for _ in range(7)]
    for m in matrices:
        for wd in range(7):
            for hr in range(24):
                matrix[wd][hr] += m[wd][hr]

    weekday_counts = [sum(row) for row in matrix]
    hour_counts = [sum(matrix[wd][hr] for wd in range(7)) for hr in range(24)]
    total = sum(weekday_counts)

    return PublicPostingTimeDistributionOut(
        weekday_counts=weekday_counts,
        hour_counts=hour_counts,
        hourly_weekday_matrix=matrix,
        best_weekday=weekday_counts.index(max(weekday_counts)) if total else None,
        best_hour=hour_counts.index(max(hour_counts)) if total else None,
        total_posts=total,
    )


@router.get("/{id}/posting-times", response_model=PublicPostingTimeDistributionOut)
async def get_public_creator_posting_times(
    id: UUID,
    days: int = Query(90, ge=1, le=3650),
    platform: PlatformFilter = _PLATFORM_QUERY,
    db: AsyncSession = Depends(get_db),
):
    """Public weekday x hour posting-time heatmap for the creator detail
    page. No auth required -- same trust level as GET /influencers/top."""
    creator_repo = CreatorRepo(db)
    influencer_repo = InfluencerRepo(db)
    stats_service = CreatorStatsService(db)

    _, refs = await _resolve_creator_refs(id, creator_repo, influencer_repo, platform)

    matrices: list[list[list[int]]] = []
    for influencer_id, _platform in refs:
        distribution = await stats_service.get_posting_time_distribution(influencer_id, days=days)
        matrices.append(distribution.hourly_weekday_matrix)

    return _merge_posting_times(matrices)


def _merge_follower_ratio(
    series_by_platform: dict[str, list[PublicFollowerRatioPoint]],
) -> list[PublicFollowerRatioPoint]:
    """Forward-fills each platform's last known followers/following so
    differing scrape cadences still sum to a sensible combined total on
    every date, then re-derives the ratio from the summed totals -- same
    approach as the cumulative-counter case in _merge_growth_series."""
    if len(series_by_platform) <= 1:
        return next(iter(series_by_platform.values()), [])

    all_dates = sorted({p.date for points in series_by_platform.values() for p in points})
    points_by_platform = {
        platform: {p.date: (p.followers, p.following) for p in points}
        for platform, points in series_by_platform.items()
    }

    last_value = {platform: None for platform in series_by_platform}
    combined = []
    for d in all_dates:
        total_followers = 0
        total_following = 0
        any_value = False
        for platform, pts in points_by_platform.items():
            if pts.get(d) is not None:
                last_value[platform] = pts[d]
            if last_value[platform] is not None:
                followers, following = last_value[platform]
                total_followers += followers
                total_following += following
                any_value = True
        if not any_value:
            continue
        combined.append(
            PublicFollowerRatioPoint(
                date=d,
                followers=total_followers,
                following=total_following,
                ratio=round(total_followers / total_following, 2) if total_following > 0 else None,
            )
        )
    return combined


@router.get("/{id}/follower-ratio", response_model=list[PublicFollowerRatioPoint])
async def get_public_creator_follower_ratio(
    id: UUID,
    days: int = Query(90, ge=1, le=3650),
    platform: PlatformFilter = _PLATFORM_QUERY,
    db: AsyncSession = Depends(get_db),
):
    """Public followers/following ratio history for the creator detail
    page. No auth required -- same trust level as GET /influencers/top."""
    creator_repo = CreatorRepo(db)
    influencer_repo = InfluencerRepo(db)
    stats_service = CreatorStatsService(db)

    _, refs = await _resolve_creator_refs(id, creator_repo, influencer_repo, platform)

    series_by_platform: dict[str, list[PublicFollowerRatioPoint]] = {}
    for influencer_id, ref_platform in refs:
        points = await stats_service.get_follower_ratio_series(influencer_id, days=days)
        series_by_platform[ref_platform] = [
            PublicFollowerRatioPoint(date=p.date, followers=p.followers, following=p.following, ratio=p.ratio)
            for p in points
        ]

    return _merge_follower_ratio(series_by_platform)
