from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.core.exceptions import InfluencerHandleNotFoundError
from app.models.scrape_job import ScrapeJob
from app.models.influencer import Influencer
from app.queue.base import ScrapeJobMessage
from app.workers.verify_badge_processor import VerifyBadgeProcessor, _CARRY_FORWARD_FIELDS


def _job(job_id):
    return SimpleNamespace(
        id=job_id, status="pending", started_at=None, retry_count=0,
        error_message=None, finished_at=None, duration_s=None,
    )


def _session_cm(session):
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=session)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


def _latest_snapshot():
    """A SimpleNamespace carrying a distinguishable, non-default value for
    every carried-forward field, plus is_verified=False (the value this
    job should overwrite)."""
    values = {field: f"carried::{field}" for field in _CARRY_FORWARD_FIELDS}
    # A couple of these are booleans/ints in the real schema -- doesn't
    # matter for these tests, which only assert identity is preserved.
    values["is_verified"] = False
    return SimpleNamespace(**values)


def _snapshot_select_result(latest):
    execute_result = MagicMock()
    execute_result.scalar_one_or_none = MagicMock(return_value=latest)
    return execute_result


@pytest.mark.asyncio
async def test_instagram_happy_path_writes_carried_forward_snapshot():
    job_id, influencer_id = uuid4(), uuid4()
    message = ScrapeJobMessage(job_id=job_id, influencer_id=influencer_id, handle="myntra", platform="instagram", job_type="verify")
    processor = VerifyBadgeProcessor(message)

    job = _job(job_id)
    latest = _latest_snapshot()

    session = MagicMock()
    session.get = AsyncMock(side_effect=lambda model, _id: job if model is ScrapeJob else None)
    session.execute = AsyncMock(return_value=_snapshot_select_result(latest))
    session.commit = AsyncMock()
    session.add = MagicMock()

    account = SimpleNamespace(id=uuid4(), user_agent="test-agent")
    account_repo_instance = MagicMock()
    account_repo_instance.acquire_healthy_account = AsyncMock(return_value=account)
    account_repo_instance.decrypt_cookies = MagicMock(return_value={})
    account_repo_instance.decrypt_proxy = MagicMock(return_value=None)
    account_repo_instance.release = AsyncMock()

    parsed_user = SimpleNamespace(is_verified=True)

    with (
        patch("app.workers.verify_badge_processor.get_session", return_value=_session_cm(session)),
        patch("app.workers.verify_badge_processor.InstagramAccountRepo", return_value=account_repo_instance),
        patch("app.workers.verify_badge_processor.InstagramClient", return_value=MagicMock(
            get_user_info=AsyncMock(return_value={}), close=AsyncMock(),
        )),
        patch("app.workers.verify_badge_processor.InstagramParser.parse_user_info", return_value=parsed_user),
    ):
        await processor.process()

    assert job.status == "completed"
    assert job.error_message is None
    session.add.assert_called_once()
    written = session.add.call_args.args[0]
    assert written.is_verified is True
    assert written.influencer_id == influencer_id
    for field in _CARRY_FORWARD_FIELDS:
        assert getattr(written, field) == f"carried::{field}"
    account_repo_instance.release.assert_awaited_once_with(account.id, "success", retry_after=None)


@pytest.mark.asyncio
async def test_youtube_prefers_channel_id_over_handle():
    job_id, influencer_id = uuid4(), uuid4()
    message = ScrapeJobMessage(job_id=job_id, influencer_id=influencer_id, handle="mkbhd", platform="youtube", job_type="verify")
    processor = VerifyBadgeProcessor(message)

    job = _job(job_id)
    influencer = SimpleNamespace(id=influencer_id, platform_user_id="UCabc123")
    latest = _latest_snapshot()

    session = MagicMock()
    session.get = AsyncMock(side_effect=lambda model, _id: job if model is ScrapeJob else influencer)
    session.execute = AsyncMock(return_value=_snapshot_select_result(latest))
    session.commit = AsyncMock()
    session.add = MagicMock()

    mock_fetch = AsyncMock(return_value=True)
    with (
        patch("app.workers.verify_badge_processor.get_session", return_value=_session_cm(session)),
        patch("app.workers.verify_badge_processor.fetch_is_verified", mock_fetch),
    ):
        await processor.process()

    mock_fetch.assert_awaited_once_with(channel_id="UCabc123")
    assert job.status == "completed"
    written = session.add.call_args.args[0]
    assert written.is_verified is True


@pytest.mark.asyncio
async def test_youtube_falls_back_to_handle_without_channel_id():
    job_id, influencer_id = uuid4(), uuid4()
    message = ScrapeJobMessage(job_id=job_id, influencer_id=influencer_id, handle="mkbhd", platform="youtube", job_type="verify")
    processor = VerifyBadgeProcessor(message)

    job = _job(job_id)
    influencer = SimpleNamespace(id=influencer_id, platform_user_id=None)
    latest = _latest_snapshot()

    session = MagicMock()
    session.get = AsyncMock(side_effect=lambda model, _id: job if model is ScrapeJob else influencer)
    session.execute = AsyncMock(return_value=_snapshot_select_result(latest))
    session.commit = AsyncMock()
    session.add = MagicMock()

    mock_fetch = AsyncMock(return_value=False)
    with (
        patch("app.workers.verify_badge_processor.get_session", return_value=_session_cm(session)),
        patch("app.workers.verify_badge_processor.fetch_is_verified", mock_fetch),
    ):
        await processor.process()

    mock_fetch.assert_awaited_once_with(handle="mkbhd")


@pytest.mark.asyncio
async def test_no_prior_snapshot_is_a_clean_noop():
    """An influencer never successfully scraped has nothing to carry
    forward -- the job completes without writing, with a clear reason."""
    job_id, influencer_id = uuid4(), uuid4()
    message = ScrapeJobMessage(job_id=job_id, influencer_id=influencer_id, handle="newbrand", platform="youtube", job_type="verify")
    processor = VerifyBadgeProcessor(message)

    job = _job(job_id)
    influencer = SimpleNamespace(id=influencer_id, platform_user_id=None)

    session = MagicMock()
    session.get = AsyncMock(side_effect=lambda model, _id: job if model is ScrapeJob else influencer)
    session.execute = AsyncMock(return_value=_snapshot_select_result(None))
    session.commit = AsyncMock()
    session.add = MagicMock()

    with (
        patch("app.workers.verify_badge_processor.get_session", return_value=_session_cm(session)),
        patch("app.workers.verify_badge_processor.fetch_is_verified", AsyncMock(return_value=True)),
    ):
        await processor.process()

    session.add.assert_not_called()
    assert job.status == "completed"
    assert "no prior snapshot" in job.error_message


@pytest.mark.asyncio
async def test_no_healthy_instagram_accounts_spends_a_retry():
    """Unlike JobProcessor/YouTubeJobProcessor's identical branch, a verify
    job DOES spend a retry here -- it's a manual, non-critical action, not
    the critical path those processors are, so it must not retry forever
    against a pool that's genuinely, permanently unhealthy (confirmed
    live: 71 verify jobs stuck in retry_pending indefinitely before this
    fix). See the processor's inline comment for the full reasoning."""
    job_id, influencer_id = uuid4(), uuid4()
    message = ScrapeJobMessage(job_id=job_id, influencer_id=influencer_id, handle="myntra", platform="instagram", job_type="verify")
    processor = VerifyBadgeProcessor(message)

    job = _job(job_id)
    session = MagicMock()
    session.get = AsyncMock(return_value=job)
    session.commit = AsyncMock()

    account_repo_instance = MagicMock()
    account_repo_instance.acquire_healthy_account = AsyncMock(return_value=None)

    with (
        patch("app.workers.verify_badge_processor.get_session", return_value=_session_cm(session)),
        patch("app.workers.verify_badge_processor.InstagramAccountRepo", return_value=account_repo_instance),
    ):
        await processor.process()

    assert job.status == "retry_pending"
    assert job.retry_count == 1
    assert job.error_message == "no healthy Instagram accounts available"


@pytest.mark.asyncio
async def test_no_healthy_instagram_accounts_fails_after_max_retries():
    job_id, influencer_id = uuid4(), uuid4()
    message = ScrapeJobMessage(job_id=job_id, influencer_id=influencer_id, handle="myntra", platform="instagram", job_type="verify")
    processor = VerifyBadgeProcessor(message)

    job = _job(job_id)
    job.retry_count = 2  # one short of SCRAPER_MAX_RETRIES (3)
    session = MagicMock()
    session.get = AsyncMock(return_value=job)
    session.commit = AsyncMock()

    account_repo_instance = MagicMock()
    account_repo_instance.acquire_healthy_account = AsyncMock(return_value=None)

    with (
        patch("app.workers.verify_badge_processor.get_session", return_value=_session_cm(session)),
        patch("app.workers.verify_badge_processor.InstagramAccountRepo", return_value=account_repo_instance),
    ):
        await processor.process()

    assert job.status == "failed"
    assert job.retry_count == 3


@pytest.mark.asyncio
async def test_handle_not_found_completes_without_retry_and_releases_account_clean():
    job_id, influencer_id = uuid4(), uuid4()
    message = ScrapeJobMessage(job_id=job_id, influencer_id=influencer_id, handle="doesnotexist", platform="instagram", job_type="verify")
    processor = VerifyBadgeProcessor(message)

    job = _job(job_id)
    session = MagicMock()
    session.get = AsyncMock(return_value=job)
    session.commit = AsyncMock()

    account = SimpleNamespace(id=uuid4(), user_agent="test-agent")
    account_repo_instance = MagicMock()
    account_repo_instance.acquire_healthy_account = AsyncMock(return_value=account)
    account_repo_instance.decrypt_cookies = MagicMock(return_value={})
    account_repo_instance.decrypt_proxy = MagicMock(return_value=None)
    account_repo_instance.release = AsyncMock()

    with (
        patch("app.workers.verify_badge_processor.get_session", return_value=_session_cm(session)),
        patch("app.workers.verify_badge_processor.InstagramAccountRepo", return_value=account_repo_instance),
        patch("app.workers.verify_badge_processor.InstagramClient", return_value=MagicMock(
            get_user_info=AsyncMock(side_effect=InfluencerHandleNotFoundError("doesnotexist", "instagram")),
            close=AsyncMock(),
        )),
    ):
        await processor.process()

    assert job.status == "completed"
    assert job.retry_count == 0
    account_repo_instance.release.assert_awaited_once_with(account.id, "success", retry_after=None)
