from uuid import UUID
from typing import Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, ConfigDict

from app.core.database import get_db
from app.models.recommendation import Recommendation


class RecommendationOut(BaseModel):
    id: UUID
    influencer_id: UUID
    category_id: UUID
    priority: str
    recommendation_type: str
    title: str
    body: str
    metric_value: Optional[str]
    benchmark_value: Optional[str]
    generated_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


router = APIRouter(prefix="/recommendations", tags=["Recommendations"])


@router.get("/{influencer_id}", response_model=list[RecommendationOut])
async def get_influencer_recommendations(influencer_id: UUID, db: AsyncSession = Depends(get_db)):
    stmt = select(Recommendation).where(
        Recommendation.influencer_id == influencer_id
    ).order_by(Recommendation.generated_at.desc())
    
    result = await db.execute(stmt)
    return result.scalars().all()
