from __future__ import annotations

from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.repositories.scrape_job_repo import JobStats
from app.services.alerts_service import get_alerts


def _account(username="acct1", status="active"):
    return SimpleNamespace(username=username, status=status)


def _job(status="completed"):
    return SimpleNamespace(status=status)


def _youtube_key(label="key1", status="active"):
    return SimpleNamespace(label=label, status=status)


def _alert_mocks(
    stack: ExitStack,
    accounts=None,
    latest_jobs=None,
    youtube_keys=None,
    job_stats=None,
    stale_running=0,
    is_sqs_queue=False,
):
    """Shared mock rig for get_alerts -- every dependency defaults to a
    fully-healthy fleet so each test only needs to override what it's
    actually exercising."""
    MockAccountRepo = stack.enter_context(patch("app.services.alerts_service.InstagramAccountRepo"))
    MockYoutubeRepo = stack.enter_context(patch("app.services.alerts_service.YouTubeApiKeyRepo"))
    MockJobRepo = stack.enter_context(patch("app.services.alerts_service.ScrapeJobRepo"))
    MockAppSettingRepo = stack.enter_context(patch("app.services.alerts_service.AppSettingRepo"))
    mock_settings = stack.enter_context(patch("app.services.alerts_service.settings"))

    MockAppSettingRepo.return_value.get = AsyncMock(return_value=None)  # no DB override
    MockAccountRepo.return_value.get_all = AsyncMock(return_value=accounts if accounts is not None else [_account()])
    MockYoutubeRepo.return_value.get_all = AsyncMock(
        return_value=youtube_keys if youtube_keys is not None else [_youtube_key()]
    )
    MockJobRepo.return_value.get_latest_per_influencer = AsyncMock(
        return_value=latest_jobs if latest_jobs is not None else [_job()]
    )
    MockJobRepo.return_value.get_job_stats_by_influencer = AsyncMock(return_value=job_stats or {})
    MockJobRepo.return_value.count_stale_running = AsyncMock(return_value=stale_running)
    mock_settings.is_sqs_queue = is_sqs_queue
    mock_settings.ALERT_FAILURE_RATE_WINDOW_HOURS = 6
    mock_settings.ALERT_FAILURE_RATE_MIN_JOBS = 5
    mock_settings.ALERT_FAILURE_RATE_THRESHOLD = 0.5
    mock_settings.ACCOUNT_LEASE_TIMEOUT_S = 180


@pytest.mark.asyncio
async def test_all_healthy_produces_no_alerts():
    with ExitStack() as stack:
        _alert_mocks(stack)
        alerts = await get_alerts(session=None)

    assert alerts == []


@pytest.mark.asyncio
async def test_in_use_account_does_not_trigger_no_healthy_alert():
    """Regression test: in_use is a healthy account actively leased for a
    running job (see acquire_healthy_account), not a problem state. This
    previously fired a false "no healthy accounts" alert during every
    single legitimate scrape."""
    with ExitStack() as stack:
        _alert_mocks(stack, accounts=[_account(status="in_use")])
        alerts = await get_alerts(session=None)

    assert alerts == []


@pytest.mark.asyncio
async def test_zero_active_accounts_is_critical():
    with ExitStack() as stack:
        _alert_mocks(stack, accounts=[_account(status="disabled")], latest_jobs=[])
        alerts = await get_alerts(session=None)

    assert any(a.severity == "critical" and "No healthy Instagram" in a.message for a in alerts)


@pytest.mark.asyncio
async def test_account_needing_manual_resolution_is_warning():
    with ExitStack() as stack:
        _alert_mocks(stack, accounts=[_account(username="stuck", status="checkpoint_required")], latest_jobs=[])
        alerts = await get_alerts(session=None)

    assert any(a.severity == "warning" and "@stuck" in a.message for a in alerts)
    # No active accounts either, in this fixture -- both alerts should fire
    assert any("No healthy Instagram" in a.message for a in alerts)


@pytest.mark.asyncio
async def test_zero_active_youtube_keys_is_critical():
    with ExitStack() as stack:
        _alert_mocks(stack, youtube_keys=[_youtube_key(status="quota_exhausted")])
        alerts = await get_alerts(session=None)

    assert any(a.severity == "critical" and "No healthy YouTube" in a.message for a in alerts)


@pytest.mark.asyncio
async def test_invalid_youtube_key_is_warning():
    with ExitStack() as stack:
        _alert_mocks(stack, youtube_keys=[_youtube_key(label="bad-key", status="invalid"), _youtube_key()])
        alerts = await get_alerts(session=None)

    assert any(a.severity == "warning" and "bad-key" in a.message and "invalid" in a.message for a in alerts)


@pytest.mark.asyncio
async def test_no_youtube_keys_registered_does_not_alert():
    """An empty pool (feature just never set up) is not the same as a
    pool that WAS healthy and went to zero -- shouldn't false-positive on
    an Instagram-only deployment."""
    with ExitStack() as stack:
        _alert_mocks(stack, youtube_keys=[])
        alerts = await get_alerts(session=None)

    assert alerts == []


@pytest.mark.asyncio
async def test_elevated_failure_rate_is_critical():
    with ExitStack() as stack:
        _alert_mocks(
            stack,
            job_stats={
                "inf-1": JobStats(
                    total_job_runs=10, completed_job_runs=2, failed_job_runs=8,
                    job_success_rate=0.2, consecutive_job_failures=3,
                ),
            },
        )
        alerts = await get_alerts(session=None)

    assert any(a.severity == "critical" and "possible systemic issue" in a.message for a in alerts)


@pytest.mark.asyncio
async def test_small_sample_failure_rate_does_not_alert():
    """Below ALERT_FAILURE_RATE_MIN_JOBS -- one failure out of one job
    shouldn't page anyone."""
    with ExitStack() as stack:
        _alert_mocks(
            stack,
            job_stats={
                "inf-1": JobStats(
                    total_job_runs=1, completed_job_runs=0, failed_job_runs=1,
                    job_success_rate=0.0, consecutive_job_failures=1,
                ),
            },
        )
        alerts = await get_alerts(session=None)

    assert not any("systemic issue" in a.message for a in alerts)


@pytest.mark.asyncio
async def test_healthy_failure_rate_does_not_alert():
    with ExitStack() as stack:
        _alert_mocks(
            stack,
            job_stats={
                "inf-1": JobStats(
                    total_job_runs=20, completed_job_runs=19, failed_job_runs=1,
                    job_success_rate=0.95, consecutive_job_failures=0,
                ),
            },
        )
        alerts = await get_alerts(session=None)

    assert not any("systemic issue" in a.message for a in alerts)


@pytest.mark.asyncio
async def test_stale_running_jobs_is_warning():
    with ExitStack() as stack:
        _alert_mocks(stack, stale_running=2)
        alerts = await get_alerts(session=None)

    assert any(a.severity == "warning" and "2 job(s) stuck" in a.message for a in alerts)
