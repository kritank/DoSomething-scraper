from uuid import UUID
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, ConfigDict

from app.core.database import get_db
from app.models.benchmark import CategoryBenchmark


class BenchmarkOut(BaseModel):
    id: UUID
    category_id: UUID
    avg_followers: int
    avg_engagement_rate: float
    median_engagement_rate: float
    avg_caption_length: int
    avg_hashtag_count: float
    avg_posting_freq_week: float
    avg_reels_per_week: float
    best_posting_hour: int
    best_posting_weekday: int
    avg_reel_duration_s: float
    sample_size: int
    computed_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


router = APIRouter(prefix="/benchmarks", tags=["Benchmarks"])


@router.get("/{category_id}", response_model=BenchmarkOut)
async def get_latest_benchmark(category_id: UUID, db: AsyncSession = Depends(get_db)):
    stmt = select(CategoryBenchmark).where(
        CategoryBenchmark.category_id == category_id
    ).order_by(CategoryBenchmark.computed_at.desc()).limit(1)
    
    benchmark = (await db.execute(stmt)).scalar_one_or_none()
    if not benchmark:
        raise HTTPException(status_code=404, detail="Benchmark not found for category")
        
    return benchmark
