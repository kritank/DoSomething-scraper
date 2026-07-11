from typing import Sequence
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.repositories.category_repo import CategoryRepo
from app.repositories.influencer_repo import InfluencerRepo
from app.repositories.scrape_job_repo import ScrapeJobRepo
from app.schemas.category import CategoryCreate, CategoryOut
from app.schemas.influencer import InfluencerCreate, InfluencerOut, InfluencerScrapeSettingsUpdate
from app.schemas.scrape_job import ScrapeJobOut
from app.services.dispatch_service import DispatchService


router = APIRouter(prefix="/admin", tags=["Admin"])


@router.post("/categories", response_model=CategoryOut)
async def create_category(data: CategoryCreate, db: AsyncSession = Depends(get_db)):
    repo = CategoryRepo(db)
    return await repo.create(data)


@router.get("/categories", response_model=list[CategoryOut])
async def list_categories(db: AsyncSession = Depends(get_db)):
    repo = CategoryRepo(db)
    return await repo.get_all()


@router.post("/influencers", response_model=InfluencerOut)
async def register_influencer(data: InfluencerCreate, db: AsyncSession = Depends(get_db)):
    repo = InfluencerRepo(db)
    # Validate category exists
    category_repo = CategoryRepo(db)
    await category_repo.get_by_id(data.category_id)
    return await repo.create(data)


@router.get("/influencers", response_model=list[InfluencerOut])
async def list_influencers(db: AsyncSession = Depends(get_db)):
    repo = InfluencerRepo(db)
    return await repo.get_all()


@router.patch("/influencers/{influencer_id}/scrape-settings", response_model=InfluencerOut)
async def update_influencer_scrape_settings(
    influencer_id: UUID, data: InfluencerScrapeSettingsUpdate, db: AsyncSession = Depends(get_db)
):
    repo = InfluencerRepo(db)
    return await repo.update_scrape_settings(influencer_id, data)


@router.post("/scrape")
async def trigger_scrape(influencer_id: UUID, db: AsyncSession = Depends(get_db)):
    service = DispatchService(db)
    job_id = await service.dispatch_scrape_job(influencer_id)
    return {"status": "queued", "job_id": str(job_id)}


@router.get("/jobs", response_model=list[ScrapeJobOut])
async def list_jobs(db: AsyncSession = Depends(get_db)):
    repo = ScrapeJobRepo(db)
    return await repo.get_all()
