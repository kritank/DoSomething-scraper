from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.schemas.alert import AlertOut
from app.services.alert_notifier import push_critical_alerts


def _mock_client(post_mock):
    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    client.post = post_mock
    return client


@pytest.mark.asyncio
async def test_noop_when_webhook_not_configured():
    with (
        patch("app.services.alert_notifier.settings") as mock_settings,
        patch("app.services.alert_notifier.get_alerts") as mock_get_alerts,
    ):
        mock_settings.SLACK_ALERT_WEBHOOK_URL = ""
        await push_critical_alerts(session=None)
    mock_get_alerts.assert_not_called()


@pytest.mark.asyncio
async def test_no_critical_alerts_does_not_send():
    with (
        patch("app.services.alert_notifier.settings") as mock_settings,
        patch("app.services.alert_notifier.get_alerts", new=AsyncMock(return_value=[])),
        patch("app.services.alert_notifier.AppSettingRepo") as MockRepo,
        patch("app.services.alert_notifier.httpx.AsyncClient") as MockClient,
    ):
        mock_settings.SLACK_ALERT_WEBHOOK_URL = "https://hooks.slack.test/x"
        MockRepo.return_value.get = AsyncMock(return_value=None)
        MockRepo.return_value.set = AsyncMock()

        await push_critical_alerts(session=None)

    MockClient.assert_not_called()
    MockRepo.return_value.set.assert_not_called()


@pytest.mark.asyncio
async def test_resolved_incident_clears_state():
    with (
        patch("app.services.alert_notifier.settings") as mock_settings,
        patch("app.services.alert_notifier.get_alerts", new=AsyncMock(return_value=[])),
        patch("app.services.alert_notifier.AppSettingRepo") as MockRepo,
        patch("app.services.alert_notifier.httpx.AsyncClient") as MockClient,
    ):
        mock_settings.SLACK_ALERT_WEBHOOK_URL = "https://hooks.slack.test/x"
        MockRepo.return_value.get = AsyncMock(
            return_value=json.dumps({"signature": "x down", "sent_at": datetime.now(timezone.utc).isoformat()})
        )
        MockRepo.return_value.set = AsyncMock()

        await push_critical_alerts(session=None)

    MockClient.assert_not_called()
    MockRepo.return_value.set.assert_awaited_once_with("critical_alerts_notify_state", json.dumps({}))


@pytest.mark.asyncio
async def test_new_critical_incident_sends_and_stores_state():
    post_mock = AsyncMock(return_value=MagicMock(raise_for_status=MagicMock()))
    with (
        patch("app.services.alert_notifier.settings") as mock_settings,
        patch(
            "app.services.alert_notifier.get_alerts",
            new=AsyncMock(return_value=[AlertOut(severity="critical", message="all accounts down")]),
        ),
        patch("app.services.alert_notifier.AppSettingRepo") as MockRepo,
        patch("app.services.alert_notifier.httpx.AsyncClient", return_value=_mock_client(post_mock)),
    ):
        mock_settings.SLACK_ALERT_WEBHOOK_URL = "https://hooks.slack.test/x"
        mock_settings.ALERT_RENOTIFY_MINUTES = 60
        MockRepo.return_value.get = AsyncMock(return_value=None)
        MockRepo.return_value.set = AsyncMock()

        await push_critical_alerts(session=None)

    post_mock.assert_awaited_once()
    sent_text = post_mock.call_args.kwargs["json"]["text"]
    assert "all accounts down" in sent_text
    MockRepo.return_value.set.assert_awaited_once()
    stored = json.loads(MockRepo.return_value.set.call_args.args[1])
    assert stored["signature"] == "all accounts down"


@pytest.mark.asyncio
async def test_unresolved_incident_not_yet_due_skips_resend():
    post_mock = AsyncMock()
    recent = datetime.now(timezone.utc) - timedelta(minutes=5)
    with (
        patch("app.services.alert_notifier.settings") as mock_settings,
        patch(
            "app.services.alert_notifier.get_alerts",
            new=AsyncMock(return_value=[AlertOut(severity="critical", message="all accounts down")]),
        ),
        patch("app.services.alert_notifier.AppSettingRepo") as MockRepo,
        patch("app.services.alert_notifier.httpx.AsyncClient", return_value=_mock_client(post_mock)),
    ):
        mock_settings.SLACK_ALERT_WEBHOOK_URL = "https://hooks.slack.test/x"
        mock_settings.ALERT_RENOTIFY_MINUTES = 60
        MockRepo.return_value.get = AsyncMock(
            return_value=json.dumps({"signature": "all accounts down", "sent_at": recent.isoformat()})
        )
        MockRepo.return_value.set = AsyncMock()

        await push_critical_alerts(session=None)

    post_mock.assert_not_awaited()
    MockRepo.return_value.set.assert_not_called()


@pytest.mark.asyncio
async def test_unresolved_incident_past_renotify_window_resends():
    post_mock = AsyncMock(return_value=MagicMock(raise_for_status=MagicMock()))
    stale = datetime.now(timezone.utc) - timedelta(minutes=90)
    with (
        patch("app.services.alert_notifier.settings") as mock_settings,
        patch(
            "app.services.alert_notifier.get_alerts",
            new=AsyncMock(return_value=[AlertOut(severity="critical", message="all accounts down")]),
        ),
        patch("app.services.alert_notifier.AppSettingRepo") as MockRepo,
        patch("app.services.alert_notifier.httpx.AsyncClient", return_value=_mock_client(post_mock)),
    ):
        mock_settings.SLACK_ALERT_WEBHOOK_URL = "https://hooks.slack.test/x"
        mock_settings.ALERT_RENOTIFY_MINUTES = 60
        MockRepo.return_value.get = AsyncMock(
            return_value=json.dumps({"signature": "all accounts down", "sent_at": stale.isoformat()})
        )
        MockRepo.return_value.set = AsyncMock()

        await push_critical_alerts(session=None)

    post_mock.assert_awaited_once()
    MockRepo.return_value.set.assert_awaited_once()


@pytest.mark.asyncio
async def test_changed_incident_resends_immediately_even_if_recent():
    post_mock = AsyncMock(return_value=MagicMock(raise_for_status=MagicMock()))
    recent = datetime.now(timezone.utc) - timedelta(minutes=1)
    with (
        patch("app.services.alert_notifier.settings") as mock_settings,
        patch(
            "app.services.alert_notifier.get_alerts",
            new=AsyncMock(return_value=[AlertOut(severity="critical", message="a new different incident")]),
        ),
        patch("app.services.alert_notifier.AppSettingRepo") as MockRepo,
        patch("app.services.alert_notifier.httpx.AsyncClient", return_value=_mock_client(post_mock)),
    ):
        mock_settings.SLACK_ALERT_WEBHOOK_URL = "https://hooks.slack.test/x"
        mock_settings.ALERT_RENOTIFY_MINUTES = 60
        MockRepo.return_value.get = AsyncMock(
            return_value=json.dumps({"signature": "all accounts down", "sent_at": recent.isoformat()})
        )
        MockRepo.return_value.set = AsyncMock()

        await push_critical_alerts(session=None)

    post_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_webhook_failure_does_not_raise_or_store_state():
    post_mock = AsyncMock(side_effect=RuntimeError("connection refused"))
    with (
        patch("app.services.alert_notifier.settings") as mock_settings,
        patch(
            "app.services.alert_notifier.get_alerts",
            new=AsyncMock(return_value=[AlertOut(severity="critical", message="all accounts down")]),
        ),
        patch("app.services.alert_notifier.AppSettingRepo") as MockRepo,
        patch("app.services.alert_notifier.httpx.AsyncClient", return_value=_mock_client(post_mock)),
    ):
        mock_settings.SLACK_ALERT_WEBHOOK_URL = "https://hooks.slack.test/x"
        mock_settings.ALERT_RENOTIFY_MINUTES = 60
        MockRepo.return_value.get = AsyncMock(return_value=None)
        MockRepo.return_value.set = AsyncMock()

        await push_critical_alerts(session=None)  # must not raise

    MockRepo.return_value.set.assert_not_called()
