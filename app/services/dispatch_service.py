from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.queue.base import ScrapeJobMessage
from app.queue.factory import get_queue
from app.repositories.influencer_repo import InfluencerRepo
from app.repositories.scrape_job_repo import ScrapeJobRepo


class DispatchService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.influencer_repo = InfluencerRepo(session)
        self.job_repo = ScrapeJobRepo(session)

    async def dispatch_scrape_job(self, influencer_id: UUID) -> UUID:
        """Create a job in the database and enqueue it."""
        influencer = await self.influencer_repo.get_by_id(influencer_id)
        
        job = await self.job_repo.create(influencer.id)
        
        queue = get_queue()
        message = ScrapeJobMessage(
            job_id=job.id,
            influencer_id=influencer.id,
            handle=influencer.handle,
        )
        await queue.enqueue(message)
        
        return job.id
