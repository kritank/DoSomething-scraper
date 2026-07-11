import asyncio
import logging
import random

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
    """Dispatch a scrape job for every active influencer.

    Spread across DAILY_SCRAPE_STAGGER_WINDOW_S instead of enqueuing all of
    them in one instant burst at midnight -- a smoother arrival rate is
    easier on the queue and on the Instagram account pool (jobs still
    queue up if there are fewer accounts than influencers, but they arrive
    over hours instead of all at once). Each dispatch uses its own
    short-lived session rather than holding one connection open for the
    whole (potentially hours-long) stagger window.
    """
    async with get_session() as session:
        influencer_repo = InfluencerRepo(session)
        influencers = [i for i in await influencer_repo.get_all() if i.is_active]

    if not influencers:
        logger.info("No active influencers to dispatch")
        return

    stagger_window_s = settings.DAILY_SCRAPE_STAGGER_WINDOW_S
    interval_s = stagger_window_s / len(influencers) if stagger_window_s > 0 else 0

    count = 0
    for influencer in influencers:
        async with get_session() as session:
            dispatch_service = DispatchService(session)
            await dispatch_service.dispatch_scrape_job(influencer.id)
        count += 1

        if interval_s > 0 and count < len(influencers):
            await asyncio.sleep(interval_s * random.uniform(0.5, 1.5))

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


async def reap_stale_jobs():
    """Crash-recovery valve for the ScrapeJob row itself -- see
    reap_stale_account_leases. Uses the same timeout as the account lease
    (ACCOUNT_LEASE_TIMEOUT_S): a job outliving its account's lease means the
    worker that held both is presumed dead."""
    async with get_session() as session:
        reaped = await ScrapeJobRepo(session).reap_stale_running(
            timeout_s=settings.ACCOUNT_LEASE_TIMEOUT_S,
            max_retries=settings.SCRAPER_MAX_RETRIES,
        )
        if reaped:
            logger.info(f"Reaped {reaped} stale running scrape job(s)")


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
    scheduler.add_job(
        reap_stale_jobs,
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
