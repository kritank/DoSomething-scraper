from types import SimpleNamespace

import pytest
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from app.core.config import settings
from app.services.dispatch_service import DispatchService
from app.queue.base import ScrapeJobMessage


@pytest.mark.asyncio
async def test_dispatch_scrape_job():
    influencer_id = uuid4()
    job_id = uuid4()
    
    mock_session = AsyncMock()
    
    with patch("app.services.dispatch_service.InfluencerRepo") as MockInfluencerRepo, \
         patch("app.services.dispatch_service.ScrapeJobRepo") as MockJobRepo, \
         patch("app.services.dispatch_service.get_queue") as mock_get_queue:
        
        # Setup mocks
        mock_influencer_repo = MockInfluencerRepo.return_value
        mock_influencer = AsyncMock()
        mock_influencer.id = influencer_id
        mock_influencer.handle = "testuser"
        mock_influencer_repo.get_by_id.return_value = mock_influencer
        
        mock_job_repo = MockJobRepo.return_value
        mock_job = AsyncMock()
        mock_job.id = job_id
        mock_job_repo.create.return_value = mock_job
        
        mock_queue = AsyncMock()
        mock_get_queue.return_value = mock_queue
        
        # Run service
        service = DispatchService(mock_session)
        result_job_id = await service.dispatch_scrape_job(influencer_id)
        
        # Verify
        assert result_job_id == job_id
        mock_influencer_repo.get_by_id.assert_called_once_with(influencer_id)
        mock_job_repo.create.assert_called_once_with(influencer_id)
        mock_queue.enqueue.assert_called_once()
        
        called_msg = mock_queue.enqueue.call_args[0][0]
        assert isinstance(called_msg, ScrapeJobMessage)
        assert called_msg.job_id == job_id
        assert called_msg.influencer_id == influencer_id
        assert called_msg.handle == "testuser"


# ── _backend_for (influencer-like object + the DB-backed setting, falling
# back to the static settings.INSTAGRAM_BACKEND default) ──────────────────

def _influencer(platform="instagram", api_supported=None):
    return SimpleNamespace(platform=platform, api_supported=api_supported)


async def _backend_for_with_override(monkeypatch, override, backend_setting, platform, api_supported):
    """override=None means no AppSetting row exists -- falls back to the
    static settings.INSTAGRAM_BACKEND default, same as a fresh environment
    that's never had the dashboard toggle touched."""
    monkeypatch.setattr(settings, "INSTAGRAM_BACKEND", backend_setting)
    service = DispatchService(session=None)  # never touched directly -- app_setting_repo is swapped below
    service.app_setting_repo = SimpleNamespace(get=AsyncMock(return_value=override))
    return await service._backend_for(_influencer(platform, api_supported))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "backend_setting,platform,api_supported,expected",
    [
        ("cookies", "instagram", None, "cookies"),  # flag off -- always cookies
        ("hybrid", "instagram", None, "graph"),  # never tried -- attempt the API
        ("hybrid", "instagram", True, "graph"),  # confirmed working
        ("hybrid", "instagram", False, "cookies"),  # confirmed personal account -- permanent fallback
        ("hybrid", "youtube", None, "cookies"),  # hybrid flag is Instagram-only
    ],
)
async def test_backend_for_matrix_using_static_default(monkeypatch, backend_setting, platform, api_supported, expected):
    # No DB override row (get() -> None) -- falls back to settings.INSTAGRAM_BACKEND.
    result = await _backend_for_with_override(monkeypatch, None, backend_setting, platform, api_supported)
    assert result == expected


@pytest.mark.asyncio
async def test_backend_for_db_override_wins_over_static_default(monkeypatch):
    """Regression guard for the dashboard toggle: a DB override must take
    priority over settings.INSTAGRAM_BACKEND, in both directions."""
    result = await _backend_for_with_override(
        monkeypatch, override="hybrid", backend_setting="cookies", platform="instagram", api_supported=None
    )
    assert result == "graph"  # DB says hybrid even though the static default says cookies

    result = await _backend_for_with_override(
        monkeypatch, override="cookies", backend_setting="hybrid", platform="instagram", api_supported=None
    )
    assert result == "cookies"  # DB says cookies even though the static default says hybrid


@pytest.mark.asyncio
async def test_dispatch_enrich_job_creates_job_type_enrich():
    influencer_id = uuid4()
    job_id = uuid4()

    with (
        patch("app.services.dispatch_service.InfluencerRepo") as MockInfluencerRepo,
        patch("app.services.dispatch_service.ScrapeJobRepo") as MockJobRepo,
        patch("app.services.dispatch_service.get_queue") as mock_get_queue,
    ):
        mock_influencer_repo = MockInfluencerRepo.return_value
        mock_influencer_repo.get_by_id = AsyncMock(
            return_value=SimpleNamespace(id=influencer_id, handle="testuser", platform="instagram")
        )

        mock_job_repo = MockJobRepo.return_value
        mock_job_repo.create = AsyncMock(return_value=SimpleNamespace(id=job_id))

        mock_queue = AsyncMock()
        mock_get_queue.return_value = mock_queue

        service = DispatchService(session=None)
        result_job_id = await service.dispatch_enrich_job(influencer_id)

        assert result_job_id == job_id
        mock_job_repo.create.assert_awaited_once_with(influencer_id, job_type="enrich")

        called_msg = mock_queue.enqueue.call_args[0][0]
        assert called_msg.job_type == "enrich"
        assert called_msg.backend == "cookies"


@pytest.mark.asyncio
async def test_dispatch_verify_job_creates_job_type_verify():
    influencer_id = uuid4()
    job_id = uuid4()

    with (
        patch("app.services.dispatch_service.InfluencerRepo") as MockInfluencerRepo,
        patch("app.services.dispatch_service.ScrapeJobRepo") as MockJobRepo,
        patch("app.services.dispatch_service.get_queue") as mock_get_queue,
    ):
        mock_influencer_repo = MockInfluencerRepo.return_value
        mock_influencer_repo.get_by_id = AsyncMock(
            return_value=SimpleNamespace(id=influencer_id, handle="testuser", platform="youtube")
        )

        mock_job_repo = MockJobRepo.return_value
        mock_job_repo.create = AsyncMock(return_value=SimpleNamespace(id=job_id))

        mock_queue = AsyncMock()
        mock_get_queue.return_value = mock_queue

        service = DispatchService(session=None)
        result_job_id = await service.dispatch_verify_job(influencer_id)

        assert result_job_id == job_id
        mock_job_repo.create.assert_awaited_once_with(influencer_id, job_type="verify")

        called_msg = mock_queue.enqueue.call_args[0][0]
        assert called_msg.job_type == "verify"
        assert called_msg.platform == "youtube"


@pytest.mark.asyncio
async def test_dispatch_verify_all_skips_influencers_with_active_jobs():
    active_id, idle_id, other_platform_id, inactive_id = uuid4(), uuid4(), uuid4(), uuid4()

    with (
        patch("app.services.dispatch_service.InfluencerRepo") as MockInfluencerRepo,
        patch("app.services.dispatch_service.ScrapeJobRepo") as MockJobRepo,
        patch("app.services.dispatch_service.get_queue") as mock_get_queue,
    ):
        mock_influencer_repo = MockInfluencerRepo.return_value
        mock_influencer_repo.get_all = AsyncMock(
            return_value=[
                SimpleNamespace(id=active_id, handle="has_active_job", platform="instagram", is_active=True),
                SimpleNamespace(id=idle_id, handle="idle", platform="instagram", is_active=True),
                SimpleNamespace(id=other_platform_id, handle="yt_account", platform="youtube", is_active=True),
                SimpleNamespace(id=inactive_id, handle="paused", platform="instagram", is_active=False),
            ]
        )
        mock_influencer_repo.get_by_id = AsyncMock(
            return_value=SimpleNamespace(id=idle_id, handle="idle", platform="instagram")
        )

        mock_job_repo = MockJobRepo.return_value
        mock_job_repo.has_active_job = AsyncMock(side_effect=lambda iid: iid == active_id)
        mock_job_repo.create = AsyncMock(return_value=SimpleNamespace(id=uuid4()))

        mock_get_queue.return_value = AsyncMock()

        service = DispatchService(session=None)
        queued, skipped = await service.dispatch_verify_all("instagram")

        # Only "idle" (instagram, active, no in-flight job) gets dispatched --
        # "has_active_job" is skipped, "yt_account" is the wrong platform,
        # "paused" isn't active.
        assert queued == 1
        assert skipped == 1
        mock_job_repo.create.assert_awaited_once_with(idle_id, job_type="verify")
