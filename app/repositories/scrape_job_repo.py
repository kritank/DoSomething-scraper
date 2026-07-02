from typing import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ScrapeJobNotFoundError
from app.models.scrape_job import ScrapeJob


class ScrapeJobRepo:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_all(self) -> Sequence[ScrapeJob]:
        result = await self.session.execute(select(ScrapeJob).order_by(ScrapeJob.created_at.desc()))
        return result.scalars().all()

    async def create(self, influencer_id: UUID) -> ScrapeJob:
        job = ScrapeJob(influencer_id=influencer_id, status="queued")
        self.session.add(job)
        await self.session.commit()
        return job

    async def get_by_id(self, job_id: UUID) -> ScrapeJob:
        job = await self.session.get(ScrapeJob, job_id)
        if not job:
            raise ScrapeJobNotFoundError(str(job_id))
        return job
