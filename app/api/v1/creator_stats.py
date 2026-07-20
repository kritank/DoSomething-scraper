from typing import Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.creator_stats import CreatorStatsService
from app.analytics.earnings import estimate_instagram_earnings, estimate_youtube_earnings
from app.core.database import get_db
from app.core.security import require_api_key
from app.schemas.creator_stats import (
    CommentEngagementOut,
    CreatorStatsOut,
    EngagementTrendPoint,
    FollowerRatioPoint,
    FormatBreakdownOut,
    GrowthPoint,
    KeyEvent,
    PerformanceDecayOut,
    PostingFrequencyPoint,
    PostingTimeDistribution,
    PostPerformance,
    ReplyTimeHeatmapOut,
    SponsorshipBreakdownOut,
)

router = APIRouter(
    prefix="/influencers", tags=["Creator Stats"], dependencies=[Depends(require_api_key)]
)


@router.get("/{influencer_id}/stats", response_model=CreatorStatsOut)
async def get_creator_stats(influencer_id: UUID, db: AsyncSession = Depends(get_db)):
    """Composite payload backing the creator profile page's single fetch:
    summary + engagement + earnings estimate + rankings + about."""
    service = CreatorStatsService(db)
    summary = await service.get_summary(influencer_id)
    if summary is None:
        raise HTTPException(status_code=404, detail="Influencer not found")

    engagement = await service.get_engagement_rate(influencer_id)
    rankings = await service.get_rankings(influencer_id)
    about = await service.get_about(influencer_id)

    earnings = None
    if summary.platform == "youtube":
        earnings = estimate_youtube_earnings(summary.views_28d, summary.country)
    else:
        earnings = estimate_instagram_earnings(
            summary.followers, engagement.engagement_rate, summary.subscribers_hidden
        )

    return CreatorStatsOut(
        summary=summary, engagement=engagement, earnings=earnings, rankings=rankings, about=about
    )


@router.get("/{influencer_id}/growth", response_model=list[GrowthPoint])
async def get_creator_growth(
    influencer_id: UUID,
    days: int = Query(90, ge=1, le=3650),
    metric: Literal["followers", "total_views", "posts", "earnings"] = Query("followers"),
    db: AsyncSession = Depends(get_db),
):
    service = CreatorStatsService(db)
    summary = await service.get_summary(influencer_id)
    if summary is None:
        raise HTTPException(status_code=404, detail="Influencer not found")
    return await service.get_growth_series(influencer_id, days=days, metric=metric)


@router.get("/{influencer_id}/posts/performance", response_model=list[PostPerformance])
async def get_creator_post_performance(
    influencer_id: UUID,
    limit: int = Query(20, ge=1, le=100),
    format: Optional[Literal["long_form", "short_form"]] = Query(
        None, description="Filter to one content format; omit for all formats."
    ),
    sort: Literal["latest", "top"] = Query("latest", description="'latest' = most recent first, 'top' = highest outlier/views first."),
    db: AsyncSession = Depends(get_db),
):
    service = CreatorStatsService(db)
    summary = await service.get_summary(influencer_id)
    if summary is None:
        raise HTTPException(status_code=404, detail="Influencer not found")
    return await service.get_post_performance(
        influencer_id, limit=limit, content_format_filter=format, sort=sort
    )


@router.get("/{influencer_id}/formats", response_model=FormatBreakdownOut)
async def get_creator_format_breakdown(
    influencer_id: UUID,
    days: int = Query(28, ge=1, le=3650),
    db: AsyncSession = Depends(get_db),
):
    service = CreatorStatsService(db)
    breakdown = await service.get_format_breakdown(influencer_id, days=days)
    if breakdown is None:
        raise HTTPException(status_code=404, detail="Influencer not found")
    return breakdown


@router.get("/{influencer_id}/sponsorship", response_model=SponsorshipBreakdownOut)
async def get_creator_sponsorship_breakdown(
    influencer_id: UUID,
    days: int = Query(90, ge=1, le=3650),
    db: AsyncSession = Depends(get_db),
):
    service = CreatorStatsService(db)
    breakdown = await service.get_sponsorship_breakdown(influencer_id, days=days)
    if breakdown is None:
        raise HTTPException(status_code=404, detail="Influencer not found")
    return breakdown


@router.get("/{influencer_id}/posting-frequency", response_model=list[PostingFrequencyPoint])
async def get_creator_posting_frequency(
    influencer_id: UUID,
    days: int = Query(90, ge=1, le=3650),
    bucket: Literal["day", "week"] = Query("week"),
    db: AsyncSession = Depends(get_db),
):
    service = CreatorStatsService(db)
    summary = await service.get_summary(influencer_id)
    if summary is None:
        raise HTTPException(status_code=404, detail="Influencer not found")
    return await service.get_posting_frequency(influencer_id, days=days, bucket=bucket)


@router.get("/{influencer_id}/posting-times", response_model=PostingTimeDistribution)
async def get_creator_posting_times(
    influencer_id: UUID,
    days: int = Query(90, ge=1, le=3650),
    db: AsyncSession = Depends(get_db),
):
    service = CreatorStatsService(db)
    summary = await service.get_summary(influencer_id)
    if summary is None:
        raise HTTPException(status_code=404, detail="Influencer not found")
    return await service.get_posting_time_distribution(influencer_id, days=days)


@router.get("/{influencer_id}/reply-time-heatmap", response_model=ReplyTimeHeatmapOut)
async def get_creator_reply_time_heatmap(
    influencer_id: UUID,
    days: int = Query(90, ge=1, le=3650),
    db: AsyncSession = Depends(get_db),
):
    service = CreatorStatsService(db)
    summary = await service.get_summary(influencer_id)
    if summary is None:
        raise HTTPException(status_code=404, detail="Influencer not found")
    return await service.get_reply_time_heatmap(influencer_id, days=days)


@router.get("/{influencer_id}/engagement-trend", response_model=list[EngagementTrendPoint])
async def get_creator_engagement_trend(
    influencer_id: UUID,
    days: int = Query(90, ge=1, le=3650),
    bucket: Literal["day", "week"] = Query("week"),
    db: AsyncSession = Depends(get_db),
):
    service = CreatorStatsService(db)
    summary = await service.get_summary(influencer_id)
    if summary is None:
        raise HTTPException(status_code=404, detail="Influencer not found")
    return await service.get_engagement_trend(influencer_id, days=days, bucket=bucket)


@router.get("/{influencer_id}/performance-decay", response_model=PerformanceDecayOut)
async def get_creator_performance_decay(
    influencer_id: UUID,
    days: int = Query(90, ge=1, le=3650),
    db: AsyncSession = Depends(get_db),
):
    service = CreatorStatsService(db)
    result = await service.get_performance_decay(influencer_id, days=days)
    if result is None:
        raise HTTPException(status_code=404, detail="Influencer not found")
    return result


@router.get("/{influencer_id}/comment-engagement", response_model=CommentEngagementOut)
async def get_creator_comment_engagement(
    influencer_id: UUID,
    days: int = Query(90, ge=1, le=3650),
    db: AsyncSession = Depends(get_db),
):
    service = CreatorStatsService(db)
    result = await service.get_comment_engagement(influencer_id, days=days)
    if result is None:
        raise HTTPException(status_code=404, detail="Influencer not found")
    return result


@router.get("/{influencer_id}/follower-ratio", response_model=list[FollowerRatioPoint])
async def get_creator_follower_ratio(
    influencer_id: UUID,
    days: int = Query(90, ge=1, le=3650),
    db: AsyncSession = Depends(get_db),
):
    service = CreatorStatsService(db)
    summary = await service.get_summary(influencer_id)
    if summary is None:
        raise HTTPException(status_code=404, detail="Influencer not found")
    return await service.get_follower_ratio_series(influencer_id, days=days)


@router.get("/{influencer_id}/events", response_model=list[KeyEvent])
async def get_creator_key_events(
    influencer_id: UUID,
    days: int = Query(90, ge=1, le=3650),
    db: AsyncSession = Depends(get_db),
):
    service = CreatorStatsService(db)
    summary = await service.get_summary(influencer_id)
    if summary is None:
        raise HTTPException(status_code=404, detail="Influencer not found")
    return await service.get_key_events(influencer_id, days=days)
