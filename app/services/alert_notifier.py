"""Push channel for critical alerts (alert_service.get_alerts is otherwise
pull-only -- see app/scheduler/runner.py's push_critical_alerts job).

Sends a Slack webhook message when the set of CRITICAL alerts changes, or
periodically re-notifies (ALERT_RENOTIFY_MINUTES) while an incident stays
unresolved, so a persistent outage doesn't page once and then go silent.
No-ops entirely when SLACK_ALERT_WEBHOOK_URL isn't configured -- this is an
additive channel, not a replacement for the dashboard's alert list.
"""

import json
from datetime import datetime, timezone

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.repositories.app_setting_repo import AppSettingRepo
from app.services.alerts_service import get_alerts

logger = get_logger(__name__)

_STATE_KEY = "critical_alerts_notify_state"


def _signature(messages: list[str]) -> str:
    # Order-independent -- get_alerts' internal iteration order isn't a
    # meaningful part of "did the incident change".
    return "\n".join(sorted(messages))


async def push_critical_alerts(session: AsyncSession) -> None:
    if not settings.SLACK_ALERT_WEBHOOK_URL:
        return

    alerts = await get_alerts(session)
    critical_messages = [a.message for a in alerts if a.severity == "critical"]

    setting_repo = AppSettingRepo(session)
    raw_state = await setting_repo.get(_STATE_KEY)
    state = json.loads(raw_state) if raw_state else {}

    if not critical_messages:
        # Resolved -- clear state so a future recurrence of the same
        # incident is treated as new rather than deduped against stale
        # signature from before it was fixed.
        if state:
            await setting_repo.set(_STATE_KEY, json.dumps({}))
        return

    signature = _signature(critical_messages)
    now = datetime.now(timezone.utc)
    last_signature = state.get("signature")
    last_sent_at = datetime.fromisoformat(state["sent_at"]) if state.get("sent_at") else None

    changed = signature != last_signature
    due_for_renotify = (
        last_sent_at is not None
        and (now - last_sent_at).total_seconds() >= settings.ALERT_RENOTIFY_MINUTES * 60
    )
    if not changed and not due_for_renotify:
        return

    text = "🚨 *Viralytics -- critical alert(s)*\n" + "\n".join(f"• {m}" for m in critical_messages)
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(settings.SLACK_ALERT_WEBHOOK_URL, json={"text": text})
            response.raise_for_status()
    except Exception as e:
        # Failure to notify shouldn't crash the scheduler tick -- the
        # dashboard's pull-based alert list is still there as a fallback,
        # and the next tick retries.
        logger.error("Failed to push critical alerts to Slack", error=str(e))
        return

    await setting_repo.set(_STATE_KEY, json.dumps({"signature": signature, "sent_at": now.isoformat()}))
