from datetime import date, timedelta
from typing import Sequence
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.security import require_api_key
from app.queue.factory import get_queue
from app.repositories.category_repo import CategoryRepo
from app.repositories.influencer_repo import InfluencerRepo
from app.repositories.instagram_account_repo import InstagramAccountRepo
from app.repositories.post_repo import PostRepo
from app.repositories.scrape_job_repo import ScrapeJobRepo
from app.schemas.account_registration import RegisterAccountCookiesRequest, RegisterAccountLoginRequest
from app.schemas.category import CategoryCreate, CategoryOut, CategoryUpdate
from app.schemas.dashboard import DashboardMetricsOut, DashboardStatusRow
from app.schemas.db_schema import SchemaTable
from app.schemas.influencer import (
    InfluencerActiveUpdate,
    InfluencerCreate,
    InfluencerDetailsUpdate,
    InfluencerOut,
    InfluencerScrapeSettingsUpdate,
)
from app.schemas.alert import AlertOut
from app.schemas.instagram_account import AccountStatusUpdate, InstagramAccountOut
from app.schemas.post import PostListOut, PostOut
from app.schemas.query_console import QueryRequest, QueryResult
from app.schemas.scrape_job import ScrapeJobOut
from app.services.alerts_service import get_alerts
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


@router.patch("/categories/{category_id}", response_model=CategoryOut)
async def update_category(category_id: UUID, data: CategoryUpdate, db: AsyncSession = Depends(get_db)):
    return await CategoryRepo(db).update(category_id, data)


@router.delete("/categories/{category_id}", status_code=204)
async def delete_category(category_id: UUID, db: AsyncSession = Depends(get_db)):
    # Hard delete -- cascades to every influencer in this category and, from
    # there, their posts/comments/snapshots. Irreversible; the dashboard
    # gates this behind an explicit confirm, deactivate (PATCH is_active)
    # is the default/reversible action.
    await CategoryRepo(db).delete(category_id)


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


@router.patch("/influencers/{influencer_id}/details", response_model=InfluencerOut)
async def update_influencer_details(
    influencer_id: UUID, data: InfluencerDetailsUpdate, db: AsyncSession = Depends(get_db)
):
    if data.category_id is not None:
        # Fail clean (404) on a bad category before touching the influencer
        # row, rather than letting a bogus UUID surface as an FK violation
        # at commit time.
        await CategoryRepo(db).get_by_id(data.category_id)
    return await InfluencerRepo(db).update_details(influencer_id, data)


@router.patch("/influencers/{influencer_id}/scrape-settings", response_model=InfluencerOut)
async def update_influencer_scrape_settings(
    influencer_id: UUID, data: InfluencerScrapeSettingsUpdate, db: AsyncSession = Depends(get_db)
):
    repo = InfluencerRepo(db)
    return await repo.update_scrape_settings(influencer_id, data)


@router.patch("/influencers/{influencer_id}/active", response_model=InfluencerOut)
async def update_influencer_active(
    influencer_id: UUID, data: InfluencerActiveUpdate, db: AsyncSession = Depends(get_db)
):
    return await InfluencerRepo(db).update_active(influencer_id, data)


@router.delete("/influencers/{influencer_id}", status_code=204)
async def delete_influencer(influencer_id: UUID, db: AsyncSession = Depends(get_db)):
    # Hard delete -- cascades to posts/comments/snapshots/feature_store.
    # Irreversible; the dashboard gates this behind an explicit confirm,
    # deactivate (PATCH active) is the default/reversible action.
    await InfluencerRepo(db).delete(influencer_id)


@router.get("/influencers/{influencer_id}/jobs", response_model=list[ScrapeJobOut])
async def list_influencer_jobs(influencer_id: UUID, db: AsyncSession = Depends(get_db)):
    return await ScrapeJobRepo(db).get_by_influencer(influencer_id)


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
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    # Defaults to the last 30 days if unset, matching the dashboard's
    # default preset. Bounded to a 366-day span so a stray far-apart
    # custom range can't trigger an unbounded full-table scan.
    resolved_end = end_date or date.today()
    resolved_start = start_date or (resolved_end - timedelta(days=30))
    if (resolved_end - resolved_start).days > 366:
        resolved_start = resolved_end - timedelta(days=366)
    return await DashboardService(db).get_daily_metrics(resolved_start, resolved_end)


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


@router.patch("/accounts/{account_id}", response_model=InstagramAccountOut)
async def update_account_status(
    account_id: UUID, data: AccountStatusUpdate, db: AsyncSession = Depends(get_db)
):
    return await InstagramAccountRepo(db).update_status(account_id, data.status)


@router.delete("/accounts/{account_id}", status_code=204)
async def delete_account(account_id: UUID, db: AsyncSession = Depends(get_db)):
    # Hard delete -- actually removes the row (cookies/password included).
    # Irreversible; the dashboard gates this behind an explicit confirm,
    # disabling (PATCH status) is the default/reversible action.
    await InstagramAccountRepo(db).delete(account_id)


@router.get("/alerts", response_model=list[AlertOut])
async def list_alerts(db: AsyncSession = Depends(get_db)):
    return await get_alerts(db)


@router.get("/posts", response_model=PostListOut)
async def list_posts(
    influencer_id: UUID | None = Query(default=None),
    category_id: UUID | None = Query(default=None),
    sort: str = Query(default="posted_at"),
    sort_dir: str = Query(default="desc"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    rows, total = await PostRepo(db).list_posts(
        influencer_id=influencer_id,
        category_id=category_id,
        sort=sort,
        sort_dir=sort_dir,
        limit=limit,
        offset=offset,
    )
    return PostListOut(posts=[PostOut(**row) for row in rows], total=total)


@router.get("/queue/status")
async def get_queue_status():
    if not settings.is_sqs_queue:
        # Redis backend has no dead-letter-queue concept in this codebase --
        # report the backend plainly rather than pretending depths exist.
        return {"backend": settings.QUEUE_BACKEND, "main_depth": None, "dlq_depth": None}
    queue = get_queue()
    return {
        "backend": "sqs",
        "main_depth": await queue.queue_depth(),
        "dlq_depth": await queue.dlq_depth(),
    }


@router.post("/query", response_model=QueryResult)
async def run_query(data: QueryRequest):
    # No `db: AsyncSession = Depends(get_db)` here on purpose -- this route
    # only ever touches the dedicated read-only engine, never the writable
    # pool used by every other route in this router.
    return await run_readonly_query(data.sql)


@router.get("/schema", response_model=list[SchemaTable])
async def get_schema():
    return await list_schema_tables()
