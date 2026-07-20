from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.scheduler.runner import retry_failed_scrapes


def _job(job_type="scrape", influencer_id=None):
    return SimpleNamespace(id=uuid4(), influencer_id=influencer_id or uuid4(), job_type=job_type, status="retry_pending")


async def _run(pending_jobs, influencer, backend_for_result="graph"):
    job_repo_instance = MagicMock()
    job_repo_instance.get_retry_pending = AsyncMock(return_value=pending_jobs)

    influencer_repo_instance = MagicMock()
    influencer_repo_instance.get_by_id = AsyncMock(return_value=influencer)

    dispatch_instance = MagicMock()
    dispatch_instance._backend_for = MagicMock(return_value=backend_for_result)

    mock_queue = AsyncMock()

    inner_session = MagicMock()
    inner_session.commit = AsyncMock()

    with (
        patch("app.scheduler.runner.get_session") as mock_get_session,
        patch("app.scheduler.runner.ScrapeJobRepo", return_value=job_repo_instance),
        patch("app.scheduler.runner.InfluencerRepo", return_value=influencer_repo_instance),
        patch("app.scheduler.runner.DispatchService", return_value=dispatch_instance),
        patch("app.scheduler.runner.get_queue", return_value=mock_queue),
    ):
        mock_get_session.return_value.__aenter__ = AsyncMock(return_value=inner_session)
        mock_get_session.return_value.__aexit__ = AsyncMock(return_value=False)
        await retry_failed_scrapes()

    return mock_queue


@pytest.mark.asyncio
async def test_enrich_job_retries_as_enrich_with_cookies_backend():
    """Regression guard: re-enqueuing a retry_pending job_type="enrich"
    row must NOT silently fall back to ScrapeJobMessage's defaults
    (job_type="scrape", backend="cookies") -- job_type must carry
    forward, and backend must stay "cookies" (enrich never uses graph),
    without even consulting _backend_for."""
    influencer_id = uuid4()
    job = _job(job_type="enrich", influencer_id=influencer_id)
    influencer = SimpleNamespace(id=influencer_id, handle="myntra", platform="instagram", is_active=True)

    mock_queue = await _run([job], influencer, backend_for_result="graph")

    message = mock_queue.enqueue.call_args.args[0]
    assert message.job_type == "enrich"
    assert message.backend == "cookies"


@pytest.mark.asyncio
async def test_scrape_job_retries_with_backend_re_derived():
    """A retry_pending job_type="scrape" row must re-derive its backend
    via the same logic DispatchService used originally (the job row
    itself doesn't persist which backend it used)."""
    influencer_id = uuid4()
    job = _job(job_type="scrape", influencer_id=influencer_id)
    influencer = SimpleNamespace(id=influencer_id, handle="myntra", platform="instagram", is_active=True)

    mock_queue = await _run([job], influencer, backend_for_result="graph")

    message = mock_queue.enqueue.call_args.args[0]
    assert message.job_type == "scrape"
    assert message.backend == "graph"


@pytest.mark.asyncio
async def test_inactive_influencer_is_skipped():
    influencer_id = uuid4()
    job = _job(job_type="scrape", influencer_id=influencer_id)
    influencer = SimpleNamespace(id=influencer_id, handle="myntra", platform="instagram", is_active=False)

    mock_queue = await _run([job], influencer)

    mock_queue.enqueue.assert_not_called()
