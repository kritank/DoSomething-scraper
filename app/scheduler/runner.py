import asyncio
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core.config import settings
from app.core.database import get_session, init_db, close_db
from app.core.exceptions import InfluencerNotFoundError
from app.services.dispatch_service import DispatchService
from app.repositories.influencer_repo import InfluencerRepo
from app.repositories.scrape_job_repo import ScrapeJobRepo
from app.repositories.instagram_account_repo import InstagramAccountRepo
from app.queue.base import ScrapeJobMessage
from app.queue.factory import get_queue

logger = logging.getLogger(__name__)

async def run_daily_scrapes():
    async with get_session() as session:
        dispatch_service = DispatchService(session)
        influencer_repo = InfluencerRepo(session)

        influencers = await influencer_repo.get_all()
        count = 0
        for influencer in influencers:
            if influencer.is_active:
                await dispatch_service.dispatch_scrape_job(influencer.id)
                count += 1
        logger.info(f"Dispatched scrapes for {count} influencers")


async def retry_failed_scrapes():
    """Re-dispatch jobs left in retry_pending by JobProcessor, reusing the
    existing ScrapeJob row (and its retry_count) rather than
    DispatchService.dispatch_scrape_job, which always creates a new one."""
    async with get_session() as session:
        job_repo = ScrapeJobRepo(session)
        influencer_repo = InfluencerRepo(session)
        queue = get_queue()

        pending = await job_repo.get_retry_pending()
        count = 0
        for job in pending:
            try:
                influencer = await influencer_repo.get_by_id(job.influencer_id)
            except InfluencerNotFoundError:
                continue
            if not influencer.is_active:
                continue

            job.status = "queued"
            await session.commit()
            await queue.enqueue(
                ScrapeJobMessage(job_id=job.id, influencer_id=influencer.id, handle=influencer.handle)
            )
            count += 1
        logger.info(f"Re-dispatched {count} retry-pending scrape jobs")


async def reap_stale_account_leases():
    """Crash-recovery valve: a worker that dies mid-job otherwise leaves its
    Instagram account leased ("in_use") forever."""
    async with get_session() as session:
        released = await InstagramAccountRepo(session).release_stale_leases()
        if released:
            logger.info(f"Released {released} stale Instagram account lease(s)")


async def main():
    await init_db()

    scheduler = AsyncIOScheduler()
    scheduler.add_job(run_daily_scrapes, CronTrigger(hour=0, minute=0))
    scheduler.add_job(
        retry_failed_scrapes,
        CronTrigger.from_crontab(settings.CRON_RETRY_FAILED, timezone=settings.SCHEDULER_TIMEZONE),
    )
    scheduler.add_job(
        reap_stale_account_leases,
        CronTrigger.from_crontab(settings.CRON_RETRY_FAILED, timezone=settings.SCHEDULER_TIMEZONE),
    )
    scheduler.start()

    logger.info("Scheduler started. Running daily scrapes at midnight UTC.")

    try:
        while True:
            await asyncio.sleep(60)
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler shutting down...")
    finally:
        await close_db()

if __name__ == "__main__":
    asyncio.run(main())
