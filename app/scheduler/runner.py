import asyncio
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core.config import settings
from app.core.database import get_session, init_db, close_db
from app.core.exceptions import InfluencerNotFoundError
from app.core.logging import configure_logging, get_logger
from app.services.dispatch_service import DispatchService
from app.repositories.influencer_repo import InfluencerRepo
from app.repositories.scrape_job_repo import ScrapeJobRepo
from app.repositories.instagram_account_repo import InstagramAccountRepo
from app.queue.base import ScrapeJobMessage
from app.queue.factory import get_queue

# Unlike main.py (the API process), nothing was calling configure_logging()
# here -- this logger was plain stdlib logging with no handler configured,
# so every INFO log (including crash-recovery reaper output) was silently
# dropped rather than just missing from a log tail.
configure_logging(log_level=settings.LOG_LEVEL, json_logs=not settings.DEBUG)
logger = get_logger(__name__)

async def run_daily_scrapes():
    """Dispatch a scrape job for every active influencer whose latest job
    (if any) is older than DAILY_SCRAPE_INTERVAL_H, skipping any that
    already have one queued/running/retry_pending.

    Runs on the same frequent CRON_RETRY_FAILED cadence as the other
    crash-recovery jobs below, NOT once at midnight. The previous version
    dispatched all active influencers in one single function call, staggered
    with asyncio.sleep() across up to 20 hours, with the "which influencers
    are left" state held only in that call's local loop variable. A
    scheduler restart at any point during that window -- a routine deploy,
    this codebase's own Watchtower-driven ones included -- silently and
    permanently dropped every influencer not yet reached that day, with no
    error and no retry until the *next* midnight (which had the same
    problem). Confirmed in production: 18 of 46 active influencers had
    never been dispatched a single job, ever.

    Checking "who's overdue" fresh on every tick instead makes this
    resumable for free -- a restart just means the next tick (within
    CRON_RETRY_FAILED, currently 10 minutes) picks up from wherever things
    actually stand, and it self-heals any backlog (like the one above)
    without needing a manual catch-up.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=settings.DAILY_SCRAPE_INTERVAL_H)
    async with get_session() as session:
        influencer_repo = InfluencerRepo(session)
        job_repo = ScrapeJobRepo(session)
        influencers = [i for i in await influencer_repo.get_all() if i.is_active]
        latest_jobs = {job.influencer_id: job for job in await job_repo.get_latest_per_influencer()}

    due = [
        influencer
        for influencer in influencers
        if (job := latest_jobs.get(influencer.id)) is None or job.created_at < cutoff
    ]
    if not due:
        return

    count = 0
    for influencer in due:
        async with get_session() as session:
            job_repo = ScrapeJobRepo(session)
            if await job_repo.has_active_job(influencer.id):
                # Already queued/running/retry_pending from an earlier
                # dispatch that just hasn't been reached yet (single-account
                # contention can leave a job queued for well over
                # DAILY_SCRAPE_INTERVAL_H) -- don't pile on a duplicate.
                continue
            await DispatchService(session).dispatch_scrape_job(influencer.id)
        count += 1

    if count:
        logger.info(f"Dispatched scrapes for {count} influencer(s) due for a daily scrape")


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
    # Not CronTrigger(hour=0, minute=0) -- see run_daily_scrapes()'s
    # docstring for why a once-a-day trigger silently dropped influencers
    # on every scheduler restart. Same cadence as the crash-recovery jobs
    # below.
    scheduler.add_job(
        run_daily_scrapes,
        CronTrigger.from_crontab(settings.CRON_RETRY_FAILED, timezone=settings.SCHEDULER_TIMEZONE),
    )
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

    logger.info(f"Scheduler started. Checking for overdue daily scrapes every tick ({settings.CRON_RETRY_FAILED}).")

    try:
        while True:
            await asyncio.sleep(60)
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler shutting down...")
    finally:
        await close_db()

if __name__ == "__main__":
    asyncio.run(main())
