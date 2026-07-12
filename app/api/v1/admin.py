from typing import Sequence
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import require_api_key
from app.repositories.category_repo import CategoryRepo
from app.repositories.influencer_repo import InfluencerRepo
from app.repositories.instagram_account_repo import InstagramAccountRepo
from app.repositories.scrape_job_repo import ScrapeJobRepo
from app.schemas.account_registration import RegisterAccountCookiesRequest, RegisterAccountLoginRequest
from app.schemas.category import CategoryCreate, CategoryOut
from app.schemas.dashboard import DashboardMetricsOut, DashboardStatusRow
from app.schemas.db_schema import SchemaTable
from app.schemas.influencer import InfluencerCreate, InfluencerOut, InfluencerScrapeSettingsUpdate
from app.schemas.instagram_account import InstagramAccountOut
from app.schemas.query_console import QueryRequest, QueryResult
from app.schemas.scrape_job import ScrapeJobOut
from app.services.dashboard_service import DashboardService
from app.services.dispatch_service import DispatchService
from app.services.query_console_service import list_schema_tables, run_readonly_query


router = APIRouter(prefix="/admin", tags=["Admin"], dependencies=[Depends(require_api_key)])


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


@router.get("/dashboard/status", response_model=list[DashboardStatusRow])
async def get_dashboard_status(db: AsyncSession = Depends(get_db)):
    return await DashboardService(db).get_status_rows()


@router.get("/dashboard/metrics", response_model=DashboardMetricsOut)
async def get_dashboard_metrics(
    days: int = Query(default=30, ge=1, le=90), db: AsyncSession = Depends(get_db)
):
    return await DashboardService(db).get_daily_metrics(days)


@router.get("/accounts", response_model=list[InstagramAccountOut])
async def list_accounts(db: AsyncSession = Depends(get_db)):
    return await InstagramAccountRepo(db).get_all()


@router.post("/accounts/cookies", response_model=InstagramAccountOut)
async def register_account_via_cookies(
    data: RegisterAccountCookiesRequest, db: AsyncSession = Depends(get_db)
):
    cookies = {"sessionid": data.sessionid, "csrftoken": data.csrftoken, "ds_user_id": data.ds_user_id}
    if data.ig_did:
        cookies["ig_did"] = data.ig_did
    return await InstagramAccountRepo(db).create(
        data.username, cookies, data.user_agent, data.locale, data.timezone
    )


@router.post("/accounts/login", response_model=InstagramAccountOut)
async def register_account_via_login(
    data: RegisterAccountLoginRequest, db: AsyncSession = Depends(get_db)
):
    # Returns immediately with status="pending_login" -- the worker's
    # background poll loop (app.workers.account_login_processor) does the
    # actual Playwright login, since only the worker image has Chromium.
    return await InstagramAccountRepo(db).create_pending_login(
        data.username, data.password, data.user_agent, data.locale, data.timezone
    )


@router.post("/query", response_model=QueryResult)
async def run_query(data: QueryRequest):
    # No `db: AsyncSession = Depends(get_db)` here on purpose -- this route
    # only ever touches the dedicated read-only engine, never the writable
    # pool used by every other route in this router.
    return await run_readonly_query(data.sql)


@router.get("/schema", response_model=list[SchemaTable])
async def get_schema():
    return await list_schema_tables()
