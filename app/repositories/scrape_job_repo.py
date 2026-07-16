from datetime import date, datetime, timedelta, timezone
from typing import Sequence
from uuid import UUID

from sqlalchemy import Row, case, exists, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.sql import func

from app.core.exceptions import JobNotCancellableError, ScrapeJobNotFoundError
from app.models.influencer import Influencer
from app.models.scrape_job import ScrapeJob

ACTIVE_JOB_STATUSES = ("queued", "running", "retry_pending")

# ScrapeJob.scraper_account (a plain Python property, not a mapped column)
# reads .instagram_account/.youtube_api_key directly -- in async SQLAlchemy
# an unloaded relationship raises MissingGreenlet instead of lazy-loading,
# so every query that returns a ScrapeJob to a caller that might read
# scraper_account (i.e. anything mapped through ScrapeJobOut) must eager-load
# both here.
_WITH_SCRAPER_ACCOUNT = (
    selectinload(ScrapeJob.instagram_account),
    selectinload(ScrapeJob.youtube_api_key),
)


class ScrapeJobRepo:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_all(self) -> Sequence[ScrapeJob]:
        stmt = (
            select(ScrapeJob)
            .options(*_WITH_SCRAPER_ACCOUNT)
            .order_by(ScrapeJob.created_at.desc())
        )
        result = await self.session.execute(stmt)
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

    async def heartbeat(self, job_id: UUID) -> bool:
        """Proves a running job's worker is still alive, independent of
        which phase of the scrape is currently executing -- see
        JobProcessor._heartbeat. reap_stale_running() below keys off
        staleness of this instead of total elapsed time since started_at,
        so a job that's legitimately taking a long time is never falsely
        reaped as long as this keeps landing every JOB_HEARTBEAT_INTERVAL_S.

        Returns True if cancellation has been requested for this job, so
        the same tick that proves liveness also delivers the one signal
        that should interrupt it -- no separate query needed."""
        result = await self.session.execute(
            update(ScrapeJob)
            .where(ScrapeJob.id == job_id)
            .values(last_heartbeat_at=func.now())
            .returning(ScrapeJob.cancel_requested_at)
        )
        await self.session.commit()
        return result.scalar_one_or_none() is not None

    async def reap_stale_running(self, timeout_s: int, max_retries: int) -> int:
        """Crash-recovery valve: mirrors InstagramAccountRepo.release_stale_leases,
        but for the job row itself -- a worker killed mid-job (SIGKILL, OOM,
        or a Watchtower rolling deploy sending SIGTERM) otherwise leaves it
        stuck in "running" forever, since only retry_pending/failed jobs are
        ever revisited by the scheduler.

        Keys off last_heartbeat_at (falling back to started_at for a job
        reaped before its first heartbeat tick), not total job duration --
        a job that's still ticking is still alive, no matter how long the
        scrape itself legitimately takes."""
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=timeout_s)
        stmt = (
            update(ScrapeJob)
            .where(ScrapeJob.status == "running")
            .where(func.coalesce(ScrapeJob.last_heartbeat_at, ScrapeJob.started_at) < cutoff)
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

    async def request_cancel(self, job_id: UUID) -> ScrapeJob:
        """queued/retry_pending jobs aren't being worked on by anything --
        cancel them outright, no worker involvement needed. A "running" job
        can't be stopped from here directly (this repo has no reach into
        the worker process); it can only flag cancel_requested_at and let
        JobProcessor._heartbeat notice on its next tick and unwind the
        scrape cooperatively (see JobCancelledError)."""
        job = await self.get_by_id(job_id)
        if job.status in ("queued", "retry_pending"):
            job.status = "cancelled"
            job.finished_at = datetime.now(timezone.utc)
        elif job.status == "running":
            job.cancel_requested_at = datetime.now(timezone.utc)
        else:
            raise JobNotCancellableError(str(job_id), job.status)
        await self.session.commit()
        return job

    async def has_active_job(self, influencer_id: UUID) -> bool:
        stmt = select(
            exists().where(
                ScrapeJob.influencer_id == influencer_id,
                ScrapeJob.status.in_(ACTIVE_JOB_STATUSES),
            )
        )
        result = await self.session.execute(stmt)
        return bool(result.scalar())

    async def has_active_job_in_category(self, category_id: UUID) -> bool:
        stmt = select(
            exists()
            .where(
                ScrapeJob.influencer_id == Influencer.id,
                Influencer.category_id == category_id,
                ScrapeJob.status.in_(ACTIVE_JOB_STATUSES),
            )
        )
        result = await self.session.execute(stmt)
        return bool(result.scalar())

    async def get_by_influencer(self, influencer_id: UUID, limit: int = 50) -> Sequence[ScrapeJob]:
        stmt = (
            select(ScrapeJob)
            .options(*_WITH_SCRAPER_ACCOUNT)
            .where(ScrapeJob.influencer_id == influencer_id)
            .order_by(ScrapeJob.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_latest_per_influencer(self) -> Sequence[ScrapeJob]:
        """One row per influencer: its most recent scrape job (by created_at).

        Postgres DISTINCT ON via SQLAlchemy Core -- a single indexed scan,
        no derived table needed. The app is Postgres-only end to end
        (asyncpg, RDS), so there's no portability being traded away.
        Influencers with zero jobs simply don't appear here; the caller
        merges this against the full influencer list separately so "never
        scraped" stays representable.
        """
        stmt = (
            select(ScrapeJob)
            .options(*_WITH_SCRAPER_ACCOUNT)
            .distinct(ScrapeJob.influencer_id)
            .order_by(ScrapeJob.influencer_id, ScrapeJob.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_daily_metrics(self, start_date: date, end_date: date) -> Sequence[Row]:
        # end_date is inclusive -- bump to the start of the next day so a
        # single-day range (start_date == end_date) still captures that
        # whole day's jobs rather than matching zero rows.
        range_start = datetime.combine(start_date, datetime.min.time()).replace(tzinfo=timezone.utc)
        range_end = datetime.combine(end_date, datetime.min.time()).replace(tzinfo=timezone.utc) + timedelta(days=1)
        day = func.date_trunc("day", ScrapeJob.created_at).label("day")
        # Joined to Influencer for platform -- one row per (day, status,
        # platform) triple, so the dashboard can show a per-platform
        # breakdown (jobs/throughput split by Instagram vs YouTube) instead
        # of only ever an all-platforms-combined total.
        stmt = (
            select(
                day,
                ScrapeJob.status,
                Influencer.platform,
                func.count().label("job_count"),
                func.avg(ScrapeJob.duration_s).label("avg_duration_s"),
                # min/max alongside avg -- a day where avg looks fine can
                # still hide a handful of jobs that took far longer, which
                # the average alone can't surface.
                func.min(ScrapeJob.duration_s).label("min_duration_s"),
                func.max(ScrapeJob.duration_s).label("max_duration_s"),
                func.coalesce(func.sum(ScrapeJob.posts_processed), 0).label("posts_processed"),
                func.coalesce(func.sum(ScrapeJob.comments_processed), 0).label("comments_processed"),
                # NULL (not 0) for an all-Instagram group -- quota_units_used
                # is only ever set on YouTube jobs, and sum() over an
                # all-NULL group already returns NULL, which is exactly the
                # "not applicable" signal this should carry.
                func.sum(ScrapeJob.quota_units_used).label("quota_units_used"),
            )
            .select_from(ScrapeJob)
            .join(Influencer, Influencer.id == ScrapeJob.influencer_id)
            .where(ScrapeJob.created_at >= range_start)
            .where(ScrapeJob.created_at < range_end)
            .group_by(day, ScrapeJob.status, Influencer.platform)
            .order_by(day)
        )
        result = await self.session.execute(stmt)
        return result.all()
