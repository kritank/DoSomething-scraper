from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.queue.base import ScrapeJobMessage
from app.workers.job_processor import JobProcessor


class _StopLoop(Exception):
    pass


async def _run_one_heartbeat_tick(job_id, account):
    """Runs JobProcessor._heartbeat for exactly one tick by making the
    second sleep call raise to break the while loop."""
    processor = JobProcessor(
        ScrapeJobMessage(job_id=job_id, influencer_id=uuid4(), handle="someone")
    )
    processor._account = account

    job_repo_instance = MagicMock()
    job_repo_instance.heartbeat = AsyncMock()
    account_repo_instance = MagicMock()
    account_repo_instance.renew_lease = AsyncMock()

    calls = {"n": 0}

    async def _sleep_then_stop(*_args, **_kwargs):
        calls["n"] += 1
        if calls["n"] >= 2:
            raise _StopLoop()

    with (
        patch("app.workers.job_processor.get_session") as mock_get_session,
        patch("app.workers.job_processor.ScrapeJobRepo", return_value=job_repo_instance),
        patch("app.workers.job_processor.InstagramAccountRepo", return_value=account_repo_instance),
        patch("app.workers.job_processor.asyncio.sleep", _sleep_then_stop),
    ):
        mock_get_session.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
        mock_get_session.return_value.__aexit__ = AsyncMock(return_value=False)
        with pytest.raises(_StopLoop):
            await processor._heartbeat(job_id)

    return job_repo_instance, account_repo_instance


@pytest.mark.asyncio
async def test_heartbeat_renews_job_and_account_lease():
    job_id = uuid4()
    account = SimpleNamespace(id=uuid4())

    job_repo, account_repo = await _run_one_heartbeat_tick(job_id, account)

    job_repo.heartbeat.assert_awaited_once_with(job_id)
    account_repo.renew_lease.assert_awaited_once_with(account.id)


@pytest.mark.asyncio
async def test_heartbeat_before_account_acquired_only_renews_job():
    """Between job.status="running" and a successful acquire_healthy_account,
    self._account is still None -- the heartbeat must not blow up trying to
    renew a lease that doesn't exist yet."""
    job_id = uuid4()

    job_repo, account_repo = await _run_one_heartbeat_tick(job_id, None)

    job_repo.heartbeat.assert_awaited_once_with(job_id)
    account_repo.renew_lease.assert_not_awaited()


@pytest.mark.asyncio
async def test_heartbeat_survives_a_transient_failure():
    """A single failed tick (e.g. a DB blip) must not kill the heartbeat
    loop -- it should log and keep ticking, not propagate."""
    job_id = uuid4()
    processor = JobProcessor(
        ScrapeJobMessage(job_id=job_id, influencer_id=uuid4(), handle="someone")
    )
    processor._account = None

    calls = {"n": 0}

    async def _sleep_then_stop(*_args, **_kwargs):
        calls["n"] += 1
        if calls["n"] >= 2:
            raise _StopLoop()

    with (
        patch("app.workers.job_processor.get_session", side_effect=RuntimeError("db blip")),
        patch("app.workers.job_processor.asyncio.sleep", _sleep_then_stop),
    ):
        with pytest.raises(_StopLoop):
            await processor._heartbeat(job_id)

    assert calls["n"] == 2
