from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.creator_stats import CreatorStatsService
from app.core.database import get_db
from app.core.exceptions import CreatorNotFoundError
from app.repositories.creator_repo import CreatorRepo
from app.repositories.influencer_repo import InfluencerRepo
from app.schemas.public_creator import (
    PublicCreatorProfileOut,
    PublicGrowthOut,
    PublicGrowthPoint,
    PublicPlatformAccountOut,
    PublicPostOut,
)

router = APIRouter(prefix="/creators", tags=["Creators"])


async def _resolve_creator_refs(id: UUID, creator_repo: CreatorRepo, influencer_repo: InfluencerRepo):
    """`id` is either a Creator id (multi-platform grouping) or, when no
    such Creator exists, falls back to treating it as a single Influencer
    id -- mirrors TopInfluencerOut.link_id, which always points to a
    /creators/{id}-shaped route with whichever id the influencer actually
    has. Returns (name, [(influencer_id, platform), ...])."""
    try:
        creator = await creator_repo.get_by_id_with_influencers(id)
        return creator.name, [(i.id, i.platform) for i in creator.influencers]
    except CreatorNotFoundError:
        influencer = await influencer_repo.get_by_id(id)  # raises InfluencerNotFoundError
        return influencer.handle, [(influencer.id, influencer.platform)]


@router.get("/{id}", response_model=PublicCreatorProfileOut)
async def get_public_creator_profile(id: UUID, db: AsyncSession = Depends(get_db)):
    """Public combined creator profile for the marketing site's creator
    detail page. No auth required -- same trust level as GET /influencers/top."""
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


@router.get("/{id}/posts", response_model=list[PublicPostOut])
async def get_public_creator_posts(
    id: UUID,
    sort: Literal["latest", "top"] = Query("latest", description="'latest' = most recent first, 'top' = highest-performing first."),
    limit: int = Query(6, ge=1, le=20),
    platform: Literal["instagram", "youtube"] | None = Query(
        None, description="Restrict to one linked platform; omit for all linked platforms combined."
    ),
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

    _, refs = await _resolve_creator_refs(id, creator_repo, influencer_repo)
    if platform:
        refs = [(influencer_id, p) for influencer_id, p in refs if p == platform]

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


_ALLOWED_GROWTH_WINDOWS = (7, 14, 21, 28)


@router.get("/{id}/growth", response_model=PublicGrowthOut)
async def get_public_creator_growth(
    id: UUID,
    metric: Literal["followers", "posts", "engagement"] = Query("followers"),
    days: int = Query(7, description="One of 7, 14, 21, 28"),
    db: AsyncSession = Depends(get_db),
):
    """Public follower/post-count/engagement history for the creator
    detail page's trend chart. No auth required -- same trust level as GET
    /influencers/top. Reuses the same growth/engagement-trend queries as
    the paid dashboard's charts (CreatorStatsService), just without the
    admin API-key gate and without the sponsorship/decay/heatmap widgets
    those charts sit alongside."""
    if days not in _ALLOWED_GROWTH_WINDOWS:
        days = min(_ALLOWED_GROWTH_WINDOWS, key=lambda w: abs(w - days))

    creator_repo = CreatorRepo(db)
    influencer_repo = InfluencerRepo(db)
    stats_service = CreatorStatsService(db)

    _, refs = await _resolve_creator_refs(id, creator_repo, influencer_repo)

    series_by_platform: dict[str, list[PublicGrowthPoint]] = {}
    for influencer_id, platform in refs:
        if metric == "engagement":
            trend = await stats_service.get_engagement_trend(influencer_id, days=days, bucket="day")
            points = [
                PublicGrowthPoint(date=p.date, value=round(p.avg_engagement_rate * 100, 2) if p.avg_engagement_rate is not None else None)
                for p in trend
            ]
        else:
            growth = await stats_service.get_growth_series(influencer_id, days=days, metric=metric)
            points = [PublicGrowthPoint(date=p.date, value=p.value) for p in growth]
        series_by_platform[platform] = points

    return PublicGrowthOut(
        metric=metric,
        days=days,
        platforms=sorted(series_by_platform.keys()),
        series={**series_by_platform, "combined": _merge_growth_series(metric, series_by_platform)},
    )
