from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.creator_stats import CreatorStatsService
from app.analytics.earnings import estimate_instagram_earnings, estimate_youtube_earnings
from app.core.database import get_db
from app.core.security import require_api_key
from app.schemas.creator_stats import CreatorStatsOut, GrowthPoint, PostPerformance

router = APIRouter(
    prefix="/influencers", tags=["Creator Stats"], dependencies=[Depends(require_api_key)]
)


@router.get("/{influencer_id}/stats", response_model=CreatorStatsOut)
async def get_creator_stats(influencer_id: UUID, db: AsyncSession = Depends(get_db)):
    """Composite payload backing the creator profile page's single fetch:
    summary + engagement + earnings estimate + in-universe rankings."""
    service = CreatorStatsService(db)
    summary = await service.get_summary(influencer_id)
    if summary is None:
        raise HTTPException(status_code=404, detail="Influencer not found")

    engagement = await service.get_engagement_rate(influencer_id)
    rankings = await service.get_rankings(influencer_id)

    earnings = None
    if summary.platform == "youtube":
        earnings = estimate_youtube_earnings(summary.views_28d, summary.country)
    else:
        earnings = estimate_instagram_earnings(
            summary.followers, engagement.engagement_rate, summary.subscribers_hidden
        )

    return CreatorStatsOut(summary=summary, engagement=engagement, earnings=earnings, rankings=rankings)


@router.get("/{influencer_id}/growth", response_model=list[GrowthPoint])
async def get_creator_growth(
    influencer_id: UUID,
    days: int = Query(90, ge=1, le=730),
    metric: Literal["followers", "total_views", "posts"] = Query("followers"),
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
    db: AsyncSession = Depends(get_db),
):
    service = CreatorStatsService(db)
    summary = await service.get_summary(influencer_id)
    if summary is None:
        raise HTTPException(status_code=404, detail="Influencer not found")
    return await service.get_post_performance(influencer_id, limit=limit)
