from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.workers import worker_runner


@pytest.fixture(autouse=True)
def _reset_workers_cache():
    """The cache is module-level and time.monotonic()-gated -- reset it
    before/after each test so tests don't leak state into each other via
    import order or real elapsed wall-clock time."""
    original = dict(worker_runner._workers_cache)
    worker_runner._workers_cache["value"] = 3
    worker_runner._workers_cache["refreshed_at"] = 0.0
    yield
    worker_runner._workers_cache.clear()
    worker_runner._workers_cache.update(original)


def _session_cm(session):
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=session)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


@pytest.mark.asyncio
async def test_effective_max_workers_uses_static_floor_when_accounts_are_fewer():
    with (
        patch("app.workers.worker_runner.get_session", return_value=_session_cm(MagicMock())),
        patch("app.workers.worker_runner.InstagramAccountRepo") as MockRepo,
        patch("app.workers.worker_runner.settings") as mock_settings,
    ):
        mock_settings.MAX_SCRAPER_WORKERS = 3
        mock_settings.MAX_SCRAPER_WORKERS_YOUTUBE_BUFFER = 2
        mock_settings.MAX_SCRAPER_WORKERS_REFRESH_S = 60
        MockRepo.return_value.count_healthy = AsyncMock(return_value=1)  # 1 + 2 buffer = 3, ties the floor

        result = await worker_runner._effective_max_workers()

    assert result == 3


@pytest.mark.asyncio
async def test_effective_max_workers_scales_up_with_more_healthy_accounts():
    with (
        patch("app.workers.worker_runner.get_session", return_value=_session_cm(MagicMock())),
        patch("app.workers.worker_runner.InstagramAccountRepo") as MockRepo,
        patch("app.workers.worker_runner.settings") as mock_settings,
    ):
        mock_settings.MAX_SCRAPER_WORKERS = 3
        mock_settings.MAX_SCRAPER_WORKERS_YOUTUBE_BUFFER = 2
        mock_settings.MAX_SCRAPER_WORKERS_REFRESH_S = 60
        MockRepo.return_value.count_healthy = AsyncMock(return_value=8)

        result = await worker_runner._effective_max_workers()

    assert result == 10  # 8 healthy accounts + 2 YouTube buffer


@pytest.mark.asyncio
async def test_effective_max_workers_caches_within_refresh_window():
    worker_runner._workers_cache["value"] = 7
    worker_runner._workers_cache["refreshed_at"] = worker_runner.time.monotonic()

    with (
        patch("app.workers.worker_runner.get_session") as mock_get_session,
        patch("app.workers.worker_runner.settings") as mock_settings,
    ):
        mock_settings.MAX_SCRAPER_WORKERS_REFRESH_S = 60

        result = await worker_runner._effective_max_workers()

    mock_get_session.assert_not_called()
    assert result == 7


@pytest.mark.asyncio
async def test_effective_max_workers_falls_back_to_cached_value_on_db_error():
    worker_runner._workers_cache["value"] = 5
    worker_runner._workers_cache["refreshed_at"] = 0.0  # force a refresh attempt

    with (
        patch("app.workers.worker_runner.get_session", side_effect=RuntimeError("db down")),
        patch("app.workers.worker_runner.settings") as mock_settings,
    ):
        mock_settings.MAX_SCRAPER_WORKERS_REFRESH_S = 60

        result = await worker_runner._effective_max_workers()  # must not raise

    assert result == 5
