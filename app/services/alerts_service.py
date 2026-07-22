from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from datetime import datetime, timedelta, timezone

from app.core.config import settings
from app.queue.factory import get_queue
from app.repositories.app_setting_repo import INSTAGRAM_BACKEND_KEY, AppSettingRepo
from app.repositories.instagram_account_repo import InstagramAccountRepo
from app.repositories.instagram_api_token_repo import InstagramApiTokenRepo
from app.repositories.scrape_job_repo import ScrapeJobRepo
from app.repositories.youtube_api_key_repo import YouTubeApiKeyRepo
from app.schemas.alert import AlertOut

_TOKEN_EXPIRY_ALERT_DAYS = 3

_NEEDS_MANUAL_RESOLUTION = ("login_failed", "checkpoint_required")
# "in_use" is a healthy account actively leased for a running job, not a
# problem state -- acquire_healthy_account() sets exactly this status the
# whole time a scrape is in flight. Checking only "active" here previously
# fired a false "no healthy accounts" critical alert during every single
# legitimate scrape.
_HEALTHY_STATUSES = ("active", "in_use")


async def get_alerts(session: AsyncSession) -> list[AlertOut]:
    alerts: list[AlertOut] = []

    accounts = await InstagramAccountRepo(session).get_all()
    if not any(a.status in _HEALTHY_STATUSES for a in accounts):
        alerts.append(AlertOut(
            severity="critical",
            message="No healthy Instagram accounts -- all scraping is blocked",
        ))
    for account in accounts:
        if account.status in _NEEDS_MANUAL_RESOLUTION:
            alerts.append(AlertOut(
                severity="warning",
                message=f"@{account.username} needs manual resolution ({account.status.replace('_', ' ')})",
            ))

    if settings.is_sqs_queue:
        dlq_depth = await get_queue().dlq_depth()
        if dlq_depth > 0:
            alerts.append(AlertOut(
                severity="critical",
                message=f"{dlq_depth} job(s) in the dead-letter queue -- check for a systemic failure",
            ))

    instagram_backend = await AppSettingRepo(session).get(INSTAGRAM_BACKEND_KEY) or settings.INSTAGRAM_BACKEND
    if instagram_backend == "hybrid":
        tokens = await InstagramApiTokenRepo(session).get_all()
        if tokens and not any(t.status == "active" for t in tokens):
            alerts.append(AlertOut(
                severity="critical",
                message="No usable Instagram Graph API tokens -- API-backed scraping is blocked",
            ))
        now = datetime.now(timezone.utc)
        for token in tokens:
            if token.status == "invalid":
                alerts.append(AlertOut(
                    severity="warning",
                    message=f"Instagram Graph API token '{token.label}' is invalid and needs re-registration",
                ))
            elif (
                token.token_expires_at is not None
                and (token.token_expires_at - now).days <= _TOKEN_EXPIRY_ALERT_DAYS
            ):
                alerts.append(AlertOut(
                    severity="warning",
                    message=f"Instagram Graph API token '{token.label}' expires {token.token_expires_at.date().isoformat()}",
                ))

    youtube_keys = await YouTubeApiKeyRepo(session).get_all()
    if youtube_keys and not any(k.status == "active" for k in youtube_keys):
        alerts.append(AlertOut(
            severity="critical",
            message="No healthy YouTube API keys -- all YouTube scraping is blocked",
        ))
    for key in youtube_keys:
        if key.status == "invalid":
            alerts.append(AlertOut(
                severity="warning",
                message=f"YouTube API key '{key.label}' is invalid and needs rotation",
            ))

    job_repo = ScrapeJobRepo(session)
    latest_jobs = await job_repo.get_latest_per_influencer()
    failed_count = sum(1 for job in latest_jobs if job.status == "failed")
    if failed_count > 0:
        alerts.append(AlertOut(
            severity="warning",
            message=f"{failed_count} influencer(s) failed their last scrape",
        ))

    # Fleet-wide failure RATE over a recent window -- distinct from the
    # per-influencer "latest job failed" check above, which is blind to a
    # systemic issue where jobs fail-then-eventually-succeed on retry (each
    # influencer's *latest* job looks fine, but most runs in the window
    # aren't).
    since = datetime.now(timezone.utc) - timedelta(hours=settings.ALERT_FAILURE_RATE_WINDOW_HOURS)
    recent_stats = await job_repo.get_job_stats_by_influencer(since=since)
    total_terminal = sum(s.completed_job_runs + s.failed_job_runs for s in recent_stats.values())
    total_failed = sum(s.failed_job_runs for s in recent_stats.values())
    if total_terminal >= settings.ALERT_FAILURE_RATE_MIN_JOBS:
        failure_rate = total_failed / total_terminal
        if failure_rate >= settings.ALERT_FAILURE_RATE_THRESHOLD:
            alerts.append(AlertOut(
                severity="critical",
                message=(
                    f"{total_failed}/{total_terminal} jobs failed in the last "
                    f"{settings.ALERT_FAILURE_RATE_WINDOW_HOURS}h ({failure_rate:.0%}) -- "
                    "possible systemic issue"
                ),
            ))

    # Jobs that would be reaped as stale on the scheduler's next tick --
    # surfaces a crashed/hung worker in real time instead of only after
    # reap_stale_running's silent info-log cleanup, and distinctly from an
    # ordinary scrape failure (this fires while the job is still "running").
    stale_running = await job_repo.count_stale_running(settings.ACCOUNT_LEASE_TIMEOUT_S)
    if stale_running > 0:
        alerts.append(AlertOut(
            severity="warning",
            message=f"{stale_running} job(s) stuck running with no heartbeat -- likely a crashed worker",
        ))

    return alerts
