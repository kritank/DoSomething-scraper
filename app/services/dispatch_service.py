from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.queue.base import ScrapeJobMessage
from app.queue.factory import get_queue
from app.repositories.app_setting_repo import INSTAGRAM_BACKEND_KEY, AppSettingRepo
from app.repositories.influencer_repo import InfluencerRepo
from app.repositories.scrape_job_repo import ScrapeJobRepo


class DispatchService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.influencer_repo = InfluencerRepo(session)
        self.job_repo = ScrapeJobRepo(session)
        self.app_setting_repo = AppSettingRepo(session)

    async def _instagram_backend(self) -> str:
        """DB-backed override, falling back to the static settings.*
        default when no override row exists -- see AppSetting's docstring
        for why this can't just be settings.INSTAGRAM_BACKEND: the
        dashboard's toggle (PATCH /admin/settings/instagram-backend) only
        ever runs inside the api container's process, which never shares
        memory with the worker/scheduler containers that actually
        dispatch and route jobs."""
        override = await self.app_setting_repo.get(INSTAGRAM_BACKEND_KEY)
        return override or settings.INSTAGRAM_BACKEND

    async def _backend_for(self, influencer) -> str:
        """Decided once, here, at enqueue time -- stamped onto the message
        so worker_runner._run_one routes on the message alone, with no DB
        lookup of its own (see docs/INSTAGRAM_HYBRID_IMPLEMENTATION.md PR2
        §2.3/2.4). api_supported is not False lets both "true" (confirmed
        working) and "null" (never tried) attempt the API path; only a
        confirmed "false" (InstagramAccountNotProfessionalError)
        permanently routes to cookies."""
        backend = await self._instagram_backend()
        if influencer.platform == "instagram" and backend == "hybrid" and influencer.api_supported is not False:
            return "graph"
        return "cookies"

    async def dispatch_scrape_job(self, influencer_id: UUID) -> UUID:
        """Create a job in the database and enqueue it."""
        influencer = await self.influencer_repo.get_by_id(influencer_id)

        job = await self.job_repo.create(influencer.id)

        queue = get_queue()
        message = ScrapeJobMessage(
            job_id=job.id,
            influencer_id=influencer.id,
            handle=influencer.handle,
            platform=influencer.platform,
            backend=await self._backend_for(influencer),
        )
        await queue.enqueue(message)

        return job.id

    async def dispatch_enrich_job(self, influencer_id: UUID) -> UUID:
        """Cookie follow-on for a Graph API-scraped influencer (PR3) --
        lands now since the job_type plumbing (ScrapeJob.job_type,
        ScrapeJobMessage.job_type) is otherwise unused and harmless to
        land ahead of the processor that will actually consume it."""
        influencer = await self.influencer_repo.get_by_id(influencer_id)

        job = await self.job_repo.create(influencer.id, job_type="enrich")

        queue = get_queue()
        message = ScrapeJobMessage(
            job_id=job.id,
            influencer_id=influencer.id,
            handle=influencer.handle,
            platform=influencer.platform,
            job_type="enrich",
            backend="cookies",
        )
        await queue.enqueue(message)

        return job.id

    async def dispatch_verify_all(self, platform: str) -> tuple[int, int]:
        """Bulk "refresh all verified badges" for a platform -- the
        per-influencer button's fan-out, done server-side rather than as a
        client-side loop, so a page refresh/navigation mid-run can't leave
        it half-done. Skips any influencer with a job already in flight,
        same "don't pile on a duplicate" convention
        app.scheduler.runner.run_daily_scrapes uses. Returns
        (queued_count, skipped_count)."""
        influencers = [
            i for i in await self.influencer_repo.get_all()
            if i.is_active and i.platform == platform
        ]
        queued = 0
        skipped = 0
        for influencer in influencers:
            if await self.job_repo.has_active_job(influencer.id):
                skipped += 1
                continue
            await self.dispatch_verify_job(influencer.id)
            queued += 1
        return queued, skipped

    async def dispatch_verify_job(self, influencer_id: UUID) -> UUID:
        """On-demand is_verified refresh -- admin-triggered "refresh
        verified badge" button, either platform. See
        app/workers/verify_badge_processor.py for why neither platform's
        regular scrape can (re)learn this on its own."""
        influencer = await self.influencer_repo.get_by_id(influencer_id)

        job = await self.job_repo.create(influencer.id, job_type="verify")

        queue = get_queue()
        message = ScrapeJobMessage(
            job_id=job.id,
            influencer_id=influencer.id,
            handle=influencer.handle,
            platform=influencer.platform,
            job_type="verify",
            backend="cookies",
        )
        await queue.enqueue(message)

        return job.id
