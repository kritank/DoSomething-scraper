import asyncio
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core.config import settings
from app.core.database import get_session, init_db, close_db
from app.core.exceptions import InfluencerNotFoundError
from app.core.logging import configure_logging, get_logger
from app.services.dispatch_service import DispatchService
from app.repositories.credential_health_repo import CredentialHealthRepo
from app.repositories.influencer_repo import InfluencerRepo
from app.repositories.queue_depth_repo import QueueDepthRepo
from app.repositories.scrape_job_repo import ScrapeJobRepo
from app.repositories.instagram_account_repo import InstagramAccountRepo
from app.repositories.instagram_api_token_repo import InstagramApiTokenRepo
from app.queue.base import ScrapeJobMessage
from app.queue.factory import get_queue
import httpx

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
                ScrapeJobMessage(
                    job_id=job.id,
                    influencer_id=influencer.id,
                    handle=influencer.handle,
                    platform=influencer.platform,
                )
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


_TOKEN_REFRESH_WINDOW = timedelta(days=10)
_TOKEN_EXPIRY_ALERT_WINDOW = timedelta(days=3)


async def refresh_instagram_tokens():
    """Refreshes any instagram_login-flavor Graph API token expiring
    within _TOKEN_REFRESH_WINDOW -- see docs/INSTAGRAM_HYBRID_IMPLEMENTATION.md
    PR2 §2.5. facebook_login tokens are Page tokens and don't expire (see
    InstagramApiTokenRepo.create's token_expires_at=None convention for
    that flavor), so they're skipped entirely -- there's nothing to refresh.

    Failure to refresh, or any token still within _TOKEN_EXPIRY_ALERT_WINDOW
    of expiring, logs an error rather than raising -- these surface via
    alerts_service.get_alerts (the dashboard's existing pull-based alert
    list), not a push notification, matching how every other credential
    problem in this codebase is surfaced."""
    async with get_session() as session:
        repo = InstagramApiTokenRepo(session)
        tokens = await repo.get_all()

    now = datetime.now(timezone.utc)
    refreshed_ids: set = set()
    for token in tokens:
        if token.auth_flavor != "instagram_login" or token.token_expires_at is None:
            continue
        if token.token_expires_at - now > _TOKEN_REFRESH_WINDOW:
            continue

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(
                    "https://graph.instagram.com/refresh_access_token",
                    params={
                        "grant_type": "ig_refresh_token",
                        "access_token": repo.decrypt_token(token),
                    },
                )
                response.raise_for_status()
                data = response.json()
        except Exception as e:
            logger.error(
                "Instagram API token refresh failed",
                label=token.label,
                expires_at=token.token_expires_at.isoformat(),
                error=str(e),
            )
            continue

        new_expires_at = now + timedelta(seconds=data.get("expires_in", 0))
        async with get_session() as session:
            await InstagramApiTokenRepo(session).update_token(token.id, data["access_token"], new_expires_at)
        logger.info("Instagram API token refreshed", label=token.label, expires_at=new_expires_at.isoformat())
        refreshed_ids.add(token.id)

    # Still-near-expiry pass, after any refreshes above -- a token that
    # failed to refresh (or wasn't due yet but is already inside the
    # tighter alert window) gets one clear log line either way. Skips
    # anything refreshed just above -- token.token_expires_at here is
    # still the pre-refresh value (this loop iterates the same in-memory
    # list fetched before any refresh happened), so a successfully
    # refreshed token would otherwise false-positive on its stale expiry.
    for token in tokens:
        if token.id in refreshed_ids:
            continue
        if (
            token.auth_flavor == "instagram_login"
            and token.token_expires_at is not None
            and token.token_expires_at - now <= _TOKEN_EXPIRY_ALERT_WINDOW
        ):
            logger.error(
                "Instagram API token expiring soon and refresh did not clear it",
                label=token.label,
                expires_at=token.token_expires_at.isoformat(),
            )


async def snapshot_credential_health():
    """Point-in-time health snapshot of every Instagram account and YouTube
    key, on the same cadence as the crash-recovery jobs above -- see
    CredentialHealthSnapshot's docstring for why this exists (neither
    source table historizes its own status, so there's otherwise no way to
    chart health, or see a quota_exhausted/checkpoint *period*, over time)."""
    async with get_session() as session:
        count = await CredentialHealthRepo(session).record_snapshot()
        if count:
            logger.info(f"Recorded {count} credential health snapshot(s)")


async def snapshot_queue_depth():
    """Point-in-time sample of the scrape job queue's depth -- see
    QueueDepthSnapshot's docstring. main_depth is always sampled (both
    backends implement queue_depth()); dlq_depth only exists for SQS."""
    queue = get_queue()
    main_depth = await queue.queue_depth()
    dlq_depth = await queue.dlq_depth() if settings.is_sqs_queue else None
    async with get_session() as session:
        await QueueDepthRepo(session).record_snapshot(
            backend=settings.QUEUE_BACKEND, main_depth=main_depth, dlq_depth=dlq_depth
        )


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
    scheduler.add_job(
        snapshot_credential_health,
        CronTrigger.from_crontab(settings.CRON_RETRY_FAILED, timezone=settings.SCHEDULER_TIMEZONE),
    )
    scheduler.add_job(
        refresh_instagram_tokens,
        CronTrigger.from_crontab(settings.CRON_PROFILE_UPDATE, timezone=settings.SCHEDULER_TIMEZONE),
    )
    scheduler.add_job(
        snapshot_queue_depth,
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
