from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from datetime import datetime, timezone

from app.core.config import settings
from app.queue.factory import get_queue
from app.repositories.app_setting_repo import INSTAGRAM_BACKEND_KEY, AppSettingRepo
from app.repositories.instagram_account_repo import InstagramAccountRepo
from app.repositories.instagram_api_token_repo import InstagramApiTokenRepo
from app.repositories.scrape_job_repo import ScrapeJobRepo
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

    latest_jobs = await ScrapeJobRepo(session).get_latest_per_influencer()
    failed_count = sum(1 for job in latest_jobs if job.status == "failed")
    if failed_count > 0:
        alerts.append(AlertOut(
            severity="warning",
            message=f"{failed_count} influencer(s) failed their last scrape",
        ))

    return alerts
