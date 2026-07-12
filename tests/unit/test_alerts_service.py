from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.services.alerts_service import get_alerts


def _account(username="acct1", status="active"):
    return SimpleNamespace(username=username, status=status)


def _job(status="completed"):
    return SimpleNamespace(status=status)


@pytest.mark.asyncio
async def test_all_healthy_produces_no_alerts():
    with (
        patch("app.services.alerts_service.InstagramAccountRepo") as MockAccountRepo,
        patch("app.services.alerts_service.ScrapeJobRepo") as MockJobRepo,
        patch("app.services.alerts_service.settings") as mock_settings,
    ):
        MockAccountRepo.return_value.get_all = AsyncMock(return_value=[_account()])
        MockJobRepo.return_value.get_latest_per_influencer = AsyncMock(return_value=[_job()])
        mock_settings.is_sqs_queue = False

        alerts = await get_alerts(session=None)

    assert alerts == []


@pytest.mark.asyncio
async def test_zero_active_accounts_is_critical():
    with (
        patch("app.services.alerts_service.InstagramAccountRepo") as MockAccountRepo,
        patch("app.services.alerts_service.ScrapeJobRepo") as MockJobRepo,
        patch("app.services.alerts_service.settings") as mock_settings,
    ):
        MockAccountRepo.return_value.get_all = AsyncMock(return_value=[_account(status="disabled")])
        MockJobRepo.return_value.get_latest_per_influencer = AsyncMock(return_value=[])
        mock_settings.is_sqs_queue = False

        alerts = await get_alerts(session=None)

    assert any(a.severity == "critical" and "No healthy" in a.message for a in alerts)


@pytest.mark.asyncio
async def test_account_needing_manual_resolution_is_warning():
    with (
        patch("app.services.alerts_service.InstagramAccountRepo") as MockAccountRepo,
        patch("app.services.alerts_service.ScrapeJobRepo") as MockJobRepo,
        patch("app.services.alerts_service.settings") as mock_settings,
    ):
        MockAccountRepo.return_value.get_all = AsyncMock(
            return_value=[_account(username="stuck", status="checkpoint_required")]
        )
        MockJobRepo.return_value.get_latest_per_influencer = AsyncMock(return_value=[])
        mock_settings.is_sqs_queue = False

        alerts = await get_alerts(session=None)

    assert any(a.severity == "warning" and "@stuck" in a.message for a in alerts)
    # No active accounts either, in this fixture -- both alerts should fire
    assert any("No healthy" in a.message for a in alerts)
