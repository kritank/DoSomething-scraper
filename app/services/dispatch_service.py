from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.queue.base import ScrapeJobMessage
from app.queue.factory import get_queue
from app.repositories.influencer_repo import InfluencerRepo
from app.repositories.scrape_job_repo import ScrapeJobRepo


class DispatchService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.influencer_repo = InfluencerRepo(session)
        self.job_repo = ScrapeJobRepo(session)

    def _backend_for(self, influencer) -> str:
        """Decided once, here, at enqueue time -- stamped onto the message
        so worker_runner._run_one routes on the message alone, with no DB
        lookup (see docs/INSTAGRAM_HYBRID_IMPLEMENTATION.md PR2 §2.3/2.4).
        api_supported is not False lets both "true" (confirmed working)
        and "null" (never tried) attempt the API path; only a confirmed
        "false" (InstagramAccountNotProfessionalError) permanently routes
        to cookies."""
        if (
            influencer.platform == "instagram"
            and settings.INSTAGRAM_BACKEND == "hybrid"
            and influencer.api_supported is not False
        ):
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
            backend=self._backend_for(influencer),
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
