from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.repositories.influencer_repo import InfluencerRepo


class TopInfluencerOut(BaseModel):
    id: UUID
    handle: str
    category_name: str
    followers: int
    following: int
    posts: int
    is_verified: bool
    # None when the influencer has no post-metrics history yet (e.g. still backfilling).
    engagement_rate: Optional[float]
    last_updated: datetime


router = APIRouter(prefix="/influencers", tags=["Influencers"])


@router.get("/top", response_model=list[TopInfluencerOut])
async def get_top_influencers(
    limit: int = Query(20, ge=1, le=100),
    category: Optional[str] = Query(None, description="Filter by category name"),
    db: AsyncSession = Depends(get_db),
):
    """Public leaderboard, ranked by follower count, for the marketing site's
    "Top Influencers" page. No auth required — same trust level as
    /benchmarks and /recommendations."""
    rows = await InfluencerRepo(db).get_top_ranked(limit=limit, category_name=category)
    return [
        TopInfluencerOut(
            id=row.id,
            handle=row.handle,
            category_name=row.category_name,
            followers=row.followers,
            following=row.following,
            posts=row.posts,
            is_verified=row.is_verified,
            engagement_rate=(
                round(row.avg_engagement / row.followers * 100, 2)
                if row.avg_engagement is not None and row.followers
                else None
            ),
            last_updated=row.last_updated,
        )
        for row in rows
    ]
