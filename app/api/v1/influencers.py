from datetime import datetime
from typing import Optional
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
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


@router.get("/{influencer_id}/avatar")
async def get_influencer_avatar(influencer_id: UUID, db: AsyncSession = Depends(get_db)):
    """Proxies an influencer's profile picture through our own origin.

    Instagram's CDN sends `Cross-Origin-Resource-Policy: same-origin` on
    profile picture responses, which Chrome enforces even for a plain
    `<img src>` -- the browser silently refuses to paint the image when
    loaded directly from a different origin (the dashboard), no matter how
    valid the signed URL is. YouTube's thumbnail CDN sends `cross-origin`
    and works fine directly; Instagram's doesn't, so it needs this detour.
    Fetching the bytes server-side (browser CORP enforcement only applies
    to browser-initiated requests) and re-serving them from our own origin
    sidesteps that -- there's no way to override Instagram's response
    headers from the client side.

    No auth required -- same trust level as GET /influencers/top; a
    profile picture isn't sensitive, and an <img> tag can't attach our
    admin API key header anyway.
    """
    influencer = await InfluencerRepo(db).get_by_id(influencer_id)
    if influencer is None or not influencer.profile_pic_url:
        raise HTTPException(status_code=404, detail="No profile picture available")

    async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
        try:
            upstream = await client.get(influencer.profile_pic_url)
            upstream.raise_for_status()
        except httpx.HTTPError:
            raise HTTPException(status_code=502, detail="Could not fetch profile picture")

    return Response(
        content=upstream.content,
        media_type=upstream.headers.get("content-type", "image/jpeg"),
        headers={
            # Signed CDN URLs expire after days/weeks -- caching moderately
            # cuts repeat upstream fetches without risking a stale broken
            # image for too long once a URL does expire.
            "Cache-Control": "public, max-age=21600",
            "Access-Control-Allow-Origin": "*",
        },
    )
