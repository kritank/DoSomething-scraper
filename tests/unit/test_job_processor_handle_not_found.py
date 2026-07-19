from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.core.exceptions import InfluencerHandleNotFoundError
from app.models.scrape_job import ScrapeJob
from app.queue.base import ScrapeJobMessage
from app.workers.job_processor import JobProcessor


@pytest.mark.asyncio
async def test_process_deactivates_influencer_on_handle_not_found():
    """A handle that Instagram itself confirms doesn't exist
    (InfluencerHandleNotFoundError, raised by InstagramClient.get_user_info
    on an empty profile lookup) must fail the job outright -- no
    retry_count spent -- and deactivate the influencer with a reason,
    instead of endlessly retrying a handle that will never resolve. The
    account must be released as a clean success (no failure_count spent),
    same as the pre-existing InfluencerNotFoundError contract."""
    job_id = uuid4()
    influencer_id = uuid4()
    message = ScrapeJobMessage(job_id=job_id, influencer_id=influencer_id, handle="doesnotexist")
    processor = JobProcessor(message)

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
        instagram_account_id=None,
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

    account = SimpleNamespace(id=uuid4(), user_agent="test-agent")
    account_repo_instance = MagicMock()
    account_repo_instance.acquire_healthy_account = AsyncMock(return_value=account)
    account_repo_instance.decrypt_cookies = MagicMock(return_value={})
    account_repo_instance.decrypt_proxy = MagicMock(return_value=None)
    account_repo_instance.release = AsyncMock()

    with (
        patch("app.workers.job_processor.get_session", return_value=session_cm),
        patch("app.workers.job_processor.InstagramAccountRepo", return_value=account_repo_instance),
        patch("app.workers.job_processor.InstagramClient", return_value=MagicMock(close=AsyncMock())),
        patch.object(
            processor, "_run_scrape",
            AsyncMock(side_effect=InfluencerHandleNotFoundError("doesnotexist", "instagram")),
        ),
        patch.object(processor, "_heartbeat", AsyncMock()),
    ):
        await processor.process()

    assert job.status == "failed"
    assert job.retry_count == 0
    assert influencer.is_active is False
    assert influencer.deactivation_reason == "handle_not_found"
    # The account's session did nothing wrong -- released as a clean
    # success, not penalized with a failure_count bump.
    account_repo_instance.release.assert_awaited_once_with(account.id, "success", retry_after=None)
