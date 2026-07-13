from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.core.exceptions import JobNotCancellableError
from app.repositories.scrape_job_repo import ScrapeJobRepo


def _repo_with_job(job) -> tuple[ScrapeJobRepo, MagicMock]:
    session = MagicMock()
    session.get = AsyncMock(return_value=job)
    session.commit = AsyncMock()
    return ScrapeJobRepo(session), session


@pytest.mark.asyncio
async def test_request_cancel_queued_job_cancels_immediately():
    job = SimpleNamespace(id=uuid4(), status="queued", finished_at=None)
    repo, session = _repo_with_job(job)

    result = await repo.request_cancel(job.id)

    assert result.status == "cancelled"
    assert result.finished_at is not None
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_request_cancel_retry_pending_job_cancels_immediately():
    job = SimpleNamespace(id=uuid4(), status="retry_pending", finished_at=None)
    repo, _ = _repo_with_job(job)

    result = await repo.request_cancel(job.id)

    assert result.status == "cancelled"


@pytest.mark.asyncio
async def test_request_cancel_running_job_sets_flag_only():
    """A running job can't be stopped from the repo directly -- it can only
    flag cancel_requested_at and let the worker's own heartbeat loop notice
    and unwind cooperatively. status must NOT change here."""
    job = SimpleNamespace(id=uuid4(), status="running", cancel_requested_at=None)
    repo, session = _repo_with_job(job)

    result = await repo.request_cancel(job.id)

    assert result.status == "running"
    assert result.cancel_requested_at is not None
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_request_cancel_terminal_job_raises():
    for terminal_status in ("completed", "failed", "cancelled"):
        job = SimpleNamespace(id=uuid4(), status=terminal_status)
        repo, session = _repo_with_job(job)

        with pytest.raises(JobNotCancellableError):
            await repo.request_cancel(job.id)

        session.commit.assert_not_awaited()


def _repo_with_exists_result(value: bool) -> ScrapeJobRepo:
    session = MagicMock()
    result = MagicMock()
    result.scalar = MagicMock(return_value=value)
    session.execute = AsyncMock(return_value=result)
    return ScrapeJobRepo(session)


@pytest.mark.asyncio
async def test_has_active_job_true():
    repo = _repo_with_exists_result(True)
    assert await repo.has_active_job(uuid4()) is True


@pytest.mark.asyncio
async def test_has_active_job_false():
    repo = _repo_with_exists_result(False)
    assert await repo.has_active_job(uuid4()) is False


@pytest.mark.asyncio
async def test_has_active_job_in_category_true():
    repo = _repo_with_exists_result(True)
    assert await repo.has_active_job_in_category(uuid4()) is True
