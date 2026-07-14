from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.scheduler.runner import run_daily_scrapes


def _influencer(is_active=True):
    return SimpleNamespace(id=uuid4(), handle="someone", is_active=is_active)


def _job(influencer_id, created_at):
    return SimpleNamespace(influencer_id=influencer_id, created_at=created_at)


async def _run(influencers, latest_jobs, has_active_job_map=None):
    """has_active_job_map: {influencer_id: bool}, defaults to all False."""
    has_active_job_map = has_active_job_map or {}

    influencer_repo_instance = MagicMock()
    influencer_repo_instance.get_all = AsyncMock(return_value=influencers)

    job_repo_instance = MagicMock()
    job_repo_instance.get_latest_per_influencer = AsyncMock(return_value=latest_jobs)
    job_repo_instance.has_active_job = AsyncMock(
        side_effect=lambda influencer_id: has_active_job_map.get(influencer_id, False)
    )

    dispatch_instance = MagicMock()
    dispatch_instance.dispatch_scrape_job = AsyncMock()

    with (
        patch("app.scheduler.runner.get_session") as mock_get_session,
        patch("app.scheduler.runner.InfluencerRepo", return_value=influencer_repo_instance),
        patch("app.scheduler.runner.ScrapeJobRepo", return_value=job_repo_instance),
        patch("app.scheduler.runner.DispatchService", return_value=dispatch_instance),
    ):
        mock_get_session.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
        mock_get_session.return_value.__aexit__ = AsyncMock(return_value=False)
        await run_daily_scrapes()

    return dispatch_instance, job_repo_instance


@pytest.mark.asyncio
async def test_never_scraped_influencer_gets_dispatched():
    """The exact bug scenario: an active influencer with zero job history
    (missing from get_latest_per_influencer entirely) must be dispatched."""
    influencer = _influencer()
    dispatch, _ = await _run([influencer], [])

    dispatch.dispatch_scrape_job.assert_awaited_once_with(influencer.id)


@pytest.mark.asyncio
async def test_recently_scraped_influencer_not_redispatched():
    influencer = _influencer()
    recent_job = _job(influencer.id, datetime.now(timezone.utc) - timedelta(hours=1))
    dispatch, _ = await _run([influencer], [recent_job])

    dispatch.dispatch_scrape_job.assert_not_awaited()


@pytest.mark.asyncio
async def test_overdue_influencer_gets_redispatched():
    influencer = _influencer()
    old_job = _job(influencer.id, datetime.now(timezone.utc) - timedelta(hours=48))
    dispatch, _ = await _run([influencer], [old_job])

    dispatch.dispatch_scrape_job.assert_awaited_once_with(influencer.id)


@pytest.mark.asyncio
async def test_overdue_but_already_has_active_job_not_duplicated():
    """A job can sit queued for longer than DAILY_SCRAPE_INTERVAL_H under
    heavy single-account contention -- must not pile on a second dispatch
    for the same influencer just because its (still in-flight) job looks
    old by created_at."""
    influencer = _influencer()
    old_job = _job(influencer.id, datetime.now(timezone.utc) - timedelta(hours=48))
    dispatch, _ = await _run(
        [influencer], [old_job], has_active_job_map={influencer.id: True}
    )

    dispatch.dispatch_scrape_job.assert_not_awaited()


@pytest.mark.asyncio
async def test_inactive_influencer_never_dispatched():
    influencer = _influencer(is_active=False)
    dispatch, _ = await _run([influencer], [])

    dispatch.dispatch_scrape_job.assert_not_awaited()
