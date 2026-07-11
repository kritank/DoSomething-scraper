from datetime import datetime, timedelta, timezone
from typing import Sequence
from uuid import UUID

from sqlalchemy import case, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func

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

    async def get_retry_pending(self) -> Sequence[ScrapeJob]:
        result = await self.session.execute(
            select(ScrapeJob).where(ScrapeJob.status == "retry_pending")
        )
        return result.scalars().all()

    async def reap_stale_running(self, timeout_s: int, max_retries: int) -> int:
        """Crash-recovery valve: mirrors InstagramAccountRepo.release_stale_leases,
        but for the job row itself -- a worker killed mid-job (SIGKILL, OOM,
        or a Watchtower rolling deploy sending SIGTERM) otherwise leaves it
        stuck in "running" forever, since only retry_pending/failed jobs are
        ever revisited by the scheduler."""
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=timeout_s)
        stmt = (
            update(ScrapeJob)
            .where(ScrapeJob.status == "running")
            .where(ScrapeJob.started_at < cutoff)
            .values(
                status=case(
                    (ScrapeJob.retry_count < max_retries, "retry_pending"),
                    else_="failed",
                ),
                retry_count=ScrapeJob.retry_count + 1,
                error_message="Worker died mid-job (reaped as stale)",
                finished_at=func.now(),
            )
        )
        result = await self.session.execute(stmt)
        await self.session.commit()
        return result.rowcount or 0
