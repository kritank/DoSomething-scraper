from __future__ import annotations

from datetime import date
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


def _repo_with_two_query_results(counts_rows, streak_rows) -> ScrapeJobRepo:
    """get_job_stats_by_influencer runs two SELECTs in sequence -- the
    counts GROUP BY first, then the ordered terminal-status fetch."""
    session = MagicMock()
    counts_result = MagicMock()
    counts_result.all = MagicMock(return_value=counts_rows)
    streak_result = MagicMock()
    streak_result.all = MagicMock(return_value=streak_rows)
    session.execute = AsyncMock(side_effect=[counts_result, streak_result])
    return ScrapeJobRepo(session)


@pytest.mark.asyncio
async def test_job_stats_success_rate_and_streak_reset_by_recent_success():
    influencer_id = uuid4()
    counts_rows = [
        SimpleNamespace(influencer_id=influencer_id, total_job_runs=3, completed_job_runs=2, failed_job_runs=1),
    ]
    # Most recent (first, since streak query orders created_at desc) is a
    # success -- the streak must be 0 even though there's an older failure.
    streak_rows = [
        SimpleNamespace(influencer_id=influencer_id, status="completed"),
        SimpleNamespace(influencer_id=influencer_id, status="failed"),
        SimpleNamespace(influencer_id=influencer_id, status="completed"),
    ]
    repo = _repo_with_two_query_results(counts_rows, streak_rows)

    stats = await repo.get_job_stats_by_influencer()

    assert stats[influencer_id].job_success_rate == round(2 / 3, 4)
    assert stats[influencer_id].consecutive_job_failures == 0


@pytest.mark.asyncio
async def test_job_stats_flags_a_failing_streak():
    influencer_id = uuid4()
    counts_rows = [
        SimpleNamespace(influencer_id=influencer_id, total_job_runs=5, completed_job_runs=2, failed_job_runs=3),
    ]
    # Three failures in a row (most recent first), then an older success --
    # the streak must stop counting at that success, not keep going.
    streak_rows = [
        SimpleNamespace(influencer_id=influencer_id, status="failed"),
        SimpleNamespace(influencer_id=influencer_id, status="failed"),
        SimpleNamespace(influencer_id=influencer_id, status="failed"),
        SimpleNamespace(influencer_id=influencer_id, status="completed"),
    ]
    repo = _repo_with_two_query_results(counts_rows, streak_rows)

    stats = await repo.get_job_stats_by_influencer()

    assert stats[influencer_id].consecutive_job_failures == 3
    assert stats[influencer_id].job_success_rate == round(2 / 5, 4)


@pytest.mark.asyncio
async def test_job_stats_success_rate_none_with_no_terminal_runs():
    influencer_id = uuid4()
    counts_rows = [
        SimpleNamespace(influencer_id=influencer_id, total_job_runs=1, completed_job_runs=0, failed_job_runs=0),
    ]
    repo = _repo_with_two_query_results(counts_rows, [])

    stats = await repo.get_job_stats_by_influencer()

    assert stats[influencer_id].job_success_rate is None
    assert stats[influencer_id].consecutive_job_failures == 0


def _compiled(stmt) -> str:
    return str(stmt.compile(compile_kwargs={"literal_binds": True}))


@pytest.mark.asyncio
async def test_get_latest_per_influencer_filters_to_scrape_job_type():
    """Regression: without this filter, an "enrich" or "verify" job (both
    near-instant, 0 posts/comments by design) becomes the "latest job" the
    moment it runs, silently overwriting the real last scrape's status on
    the Overview page's "Last Scrape" column with unrelated numbers."""
    session = MagicMock()
    result = MagicMock()
    result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
    session.execute = AsyncMock(return_value=result)
    repo = ScrapeJobRepo(session)

    await repo.get_latest_per_influencer()

    stmt = session.execute.call_args.args[0]
    assert "job_type = 'scrape'" in _compiled(stmt)


@pytest.mark.asyncio
async def test_get_job_stats_by_influencer_filters_to_scrape_job_type():
    session = MagicMock()
    counts_result = MagicMock()
    counts_result.all = MagicMock(return_value=[])
    streak_result = MagicMock()
    streak_result.all = MagicMock(return_value=[])
    session.execute = AsyncMock(side_effect=[counts_result, streak_result])
    repo = ScrapeJobRepo(session)

    await repo.get_job_stats_by_influencer()

    counts_stmt = session.execute.call_args_list[0].args[0]
    streak_stmt = session.execute.call_args_list[1].args[0]
    assert "job_type = 'scrape'" in _compiled(counts_stmt)
    assert "job_type = 'scrape'" in _compiled(streak_stmt)


@pytest.mark.asyncio
async def test_get_daily_metrics_excludes_verify_job_type():
    """Verify jobs contribute nothing real (0 posts/comments, sub-second
    duration) -- left in, they'd drag down avg_duration_s and inflate
    "completed" counts on the Overview charts for no real throughput."""
    session = MagicMock()
    result = MagicMock()
    result.all = MagicMock(return_value=[])
    session.execute = AsyncMock(return_value=result)
    repo = ScrapeJobRepo(session)

    await repo.get_daily_metrics(date(2026, 1, 1), date(2026, 1, 1))

    stmt = session.execute.call_args.args[0]
    assert "job_type != 'verify'" in _compiled(stmt)
