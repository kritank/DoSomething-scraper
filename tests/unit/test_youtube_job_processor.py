from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.core.exceptions import InfluencerHandleNotFoundError, NoUsableYouTubeKeyError
from app.models.scrape_job import ScrapeJob
from app.queue.base import ScrapeJobMessage
from app.workers.youtube_job_processor import YouTubeJobProcessor


class _StopLoop(Exception):
    pass


@pytest.mark.asyncio
async def test_heartbeat_renews_job_liveness_only():
    """Unlike JobProcessor, there's no leased account to renew -- a
    YouTube API key is shared, not exclusively held per job (see
    YouTubeApiKeyRepo.get_usable_key)."""
    job_id = uuid4()
    processor = YouTubeJobProcessor(
        ScrapeJobMessage(job_id=job_id, influencer_id=uuid4(), handle="@someone", platform="youtube")
    )

    job_repo_instance = MagicMock()
    job_repo_instance.heartbeat = AsyncMock()

    calls = {"n": 0}

    async def _sleep_then_stop(*_args, **_kwargs):
        calls["n"] += 1
        if calls["n"] >= 2:
            raise _StopLoop()

    with (
        patch("app.workers.youtube_job_processor.get_session") as mock_get_session,
        patch("app.workers.youtube_job_processor.ScrapeJobRepo", return_value=job_repo_instance),
        patch("app.workers.youtube_job_processor.asyncio.sleep", _sleep_then_stop),
    ):
        mock_get_session.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
        mock_get_session.return_value.__aexit__ = AsyncMock(return_value=False)
        with pytest.raises(_StopLoop):
            await processor._heartbeat(job_id)

    job_repo_instance.heartbeat.assert_awaited_once_with(job_id)


@pytest.mark.asyncio
async def test_heartbeat_survives_a_transient_failure():
    job_id = uuid4()
    processor = YouTubeJobProcessor(
        ScrapeJobMessage(job_id=job_id, influencer_id=uuid4(), handle="@someone", platform="youtube")
    )

    calls = {"n": 0}

    async def _sleep_then_stop(*_args, **_kwargs):
        calls["n"] += 1
        if calls["n"] >= 2:
            raise _StopLoop()

    with (
        patch("app.workers.youtube_job_processor.get_session", side_effect=RuntimeError("db blip")),
        patch("app.workers.youtube_job_processor.asyncio.sleep", _sleep_then_stop),
    ):
        with pytest.raises(_StopLoop):
            await processor._heartbeat(job_id)

    assert calls["n"] == 2


@pytest.mark.asyncio
async def test_cancel_requested_during_heartbeat_sets_cancel_event():
    job_id = uuid4()
    processor = YouTubeJobProcessor(
        ScrapeJobMessage(job_id=job_id, influencer_id=uuid4(), handle="@someone", platform="youtube")
    )

    job_repo_instance = MagicMock()
    job_repo_instance.heartbeat = AsyncMock(return_value=True)  # cancellation requested

    calls = {"n": 0}

    async def _sleep_once_then_stop(*_args, **_kwargs):
        calls["n"] += 1
        if calls["n"] >= 2:
            raise _StopLoop()

    with (
        patch("app.workers.youtube_job_processor.get_session") as mock_get_session,
        patch("app.workers.youtube_job_processor.ScrapeJobRepo", return_value=job_repo_instance),
        patch("app.workers.youtube_job_processor.asyncio.sleep", _sleep_once_then_stop),
    ):
        mock_get_session.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
        mock_get_session.return_value.__aexit__ = AsyncMock(return_value=False)
        # First sleep call succeeds (calls["n"] == 1), letting one full
        # heartbeat tick run and set cancel_event; the second sleep call
        # raises _StopLoop to end the test.
        with pytest.raises(_StopLoop):
            await processor._heartbeat(job_id)

    assert processor._cancel_event.is_set()


@pytest.mark.asyncio
async def test_process_routes_to_retry_pending_when_no_usable_key():
    """Mirrors JobProcessor's "no healthy accounts" branch: a totally
    exhausted/empty key pool must not spend a retry_count on a job that
    never got to attempt anything."""
    job_id = uuid4()
    message = ScrapeJobMessage(job_id=job_id, influencer_id=uuid4(), handle="@someone", platform="youtube")
    processor = YouTubeJobProcessor(message)

    job = SimpleNamespace(
        id=job_id,
        status="pending",
        started_at=None,
        last_heartbeat_at=None,
        posts_processed=0,
        comments_processed=0,
        retry_count=0,
        error_message=None,
        finished_at=None,
        duration_s=None,
    )

    session = MagicMock()
    session.get = AsyncMock(return_value=job)
    session.commit = AsyncMock()

    session_cm = MagicMock()
    session_cm.__aenter__ = AsyncMock(return_value=session)
    session_cm.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("app.workers.youtube_job_processor.get_session", return_value=session_cm),
        patch(
            "app.workers.youtube_job_processor.ykp.provide_key",
            AsyncMock(side_effect=NoUsableYouTubeKeyError()),
        ),
    ):
        await processor.process()

    assert job.status == "retry_pending"
    assert job.error_message == "no usable YouTube API key available"
    # retry_count must NOT be spent -- this job never attempted a scrape.
    assert job.retry_count == 0


@pytest.mark.asyncio
async def test_process_deactivates_influencer_on_handle_not_found():
    """A channel that doesn't resolve (InfluencerHandleNotFoundError, e.g.
    raised when channels.list comes back empty) must fail the job outright
    -- no retry_count spent -- and deactivate the influencer with a reason,
    instead of endlessly retrying a handle that will never resolve."""
    job_id = uuid4()
    influencer_id = uuid4()
    message = ScrapeJobMessage(job_id=job_id, influencer_id=influencer_id, handle="@doesnotexist", platform="youtube")
    processor = YouTubeJobProcessor(message)

    job = SimpleNamespace(
        id=job_id,
        status="pending",
        started_at=None,
        last_heartbeat_at=None,
        posts_processed=0,
        comments_processed=0,
        retry_count=0,
        error_message=None,
        finished_at=None,
        duration_s=None,
        youtube_api_key_id=None,
        quota_units_used=None,
    )
    influencer = SimpleNamespace(id=influencer_id, is_active=True, deactivation_reason=None)

    async def _get(model, _id):
        return job if model is ScrapeJob else influencer

    session = MagicMock()
    session.get = AsyncMock(side_effect=_get)
    session.commit = AsyncMock()

    session_cm = MagicMock()
    session_cm.__aenter__ = AsyncMock(return_value=session)
    session_cm.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("app.workers.youtube_job_processor.get_session", return_value=session_cm),
        patch("app.workers.youtube_job_processor.ykp.provide_key", AsyncMock(return_value=MagicMock())),
        patch.object(
            processor, "_run_scrape",
            AsyncMock(side_effect=InfluencerHandleNotFoundError("@doesnotexist", "youtube")),
        ),
        patch.object(processor, "_heartbeat", AsyncMock()),
    ):
        await processor.process()

    assert job.status == "failed"
    assert job.retry_count == 0
    assert influencer.is_active is False
    assert influencer.deactivation_reason == "handle_not_found"
