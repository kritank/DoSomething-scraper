from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.core.exceptions import (
    InfluencerHandleNotFoundError,
    InstagramAccountNotProfessionalError,
    NoUsableInstagramTokenError,
)
from app.models.post import Post
from app.models.scrape_job import ScrapeJob
from app.queue.base import ScrapeJobMessage
from app.schemas.instagram import InstagramMediaItem
from app.workers.instagram_graph_job_processor import InstagramGraphJobProcessor


def _session_cm(session):
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=session)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


@pytest.mark.asyncio
async def test_process_routes_to_retry_pending_when_no_usable_token():
    job_id = uuid4()
    message = ScrapeJobMessage(job_id=job_id, influencer_id=uuid4(), handle="myntra", platform="instagram", backend="graph")
    processor = InstagramGraphJobProcessor(message)

    job = SimpleNamespace(
        id=job_id, status="pending", started_at=None, last_heartbeat_at=None,
        posts_processed=0, retry_count=0, error_message=None, finished_at=None, duration_s=None,
    )
    session = MagicMock()
    session.get = AsyncMock(return_value=job)
    session.commit = AsyncMock()

    with (
        patch("app.workers.instagram_graph_job_processor.get_session", return_value=_session_cm(session)),
        patch(
            "app.workers.instagram_graph_job_processor.itp.provide_token",
            AsyncMock(side_effect=NoUsableInstagramTokenError()),
        ),
    ):
        await processor.process()

    assert job.status == "retry_pending"
    assert job.error_message == "no usable Instagram API token available"
    assert job.retry_count == 0  # never attempted a scrape -- must not spend retry_count


@pytest.mark.asyncio
async def test_process_deactivates_influencer_on_handle_not_found():
    job_id = uuid4()
    influencer_id = uuid4()
    message = ScrapeJobMessage(job_id=job_id, influencer_id=influencer_id, handle="doesnotexist", platform="instagram", backend="graph")
    processor = InstagramGraphJobProcessor(message)

    job = SimpleNamespace(
        id=job_id, status="pending", started_at=None, last_heartbeat_at=None,
        posts_processed=0, retry_count=0, error_message=None, finished_at=None, duration_s=None,
        instagram_api_token_id=None,
    )
    influencer = SimpleNamespace(id=influencer_id, is_active=True, deactivation_reason=None)

    async def _get(model, _id):
        return job if model is ScrapeJob else influencer

    session = MagicMock()
    session.get = AsyncMock(side_effect=_get)
    session.commit = AsyncMock()

    with (
        patch("app.workers.instagram_graph_job_processor.get_session", return_value=_session_cm(session)),
        patch("app.workers.instagram_graph_job_processor.itp.provide_token", AsyncMock(return_value=(uuid4(), "tok", "ig1"))),
        patch.object(processor, "_run_scrape", AsyncMock(side_effect=InfluencerHandleNotFoundError("doesnotexist", "instagram"))),
        patch.object(processor, "_heartbeat", AsyncMock()),
    ):
        await processor.process()

    assert job.status == "failed"
    assert job.retry_count == 0
    assert influencer.is_active is False
    assert influencer.deactivation_reason == "handle_not_found"


@pytest.mark.asyncio
async def test_process_falls_back_to_cookies_on_not_professional_account():
    """A personal (non-professional) account is permanent for this target,
    not this token -- every token would fail identically. Must flag
    api_supported=False (so future dispatches route straight to cookies)
    and re-dispatch a legacy scrape so the cycle isn't lost."""
    job_id = uuid4()
    influencer_id = uuid4()
    message = ScrapeJobMessage(job_id=job_id, influencer_id=influencer_id, handle="personal_acct", platform="instagram", backend="graph")
    processor = InstagramGraphJobProcessor(message)

    job = SimpleNamespace(
        id=job_id, status="pending", started_at=None, last_heartbeat_at=None,
        posts_processed=0, retry_count=0, error_message=None, finished_at=None, duration_s=None,
        instagram_api_token_id=None,
    )
    influencer = SimpleNamespace(
        id=influencer_id, handle="personal_acct", platform="instagram", api_supported=None,
    )

    async def _get(model, _id):
        return job if model is ScrapeJob else influencer

    session = MagicMock()
    session.get = AsyncMock(side_effect=_get)
    session.commit = AsyncMock()

    fallback_job = SimpleNamespace(id=uuid4())
    mock_job_repo = MagicMock()
    mock_job_repo.create = AsyncMock(return_value=fallback_job)
    mock_queue = MagicMock()
    mock_queue.enqueue = AsyncMock()

    with (
        patch("app.workers.instagram_graph_job_processor.get_session", return_value=_session_cm(session)),
        patch("app.workers.instagram_graph_job_processor.itp.provide_token", AsyncMock(return_value=(uuid4(), "tok", "ig1"))),
        patch.object(
            processor, "_run_scrape",
            AsyncMock(side_effect=InstagramAccountNotProfessionalError("personal_acct")),
        ),
        patch.object(processor, "_heartbeat", AsyncMock()),
        patch("app.workers.instagram_graph_job_processor.ScrapeJobRepo", return_value=mock_job_repo),
        patch("app.workers.instagram_graph_job_processor.get_queue", return_value=mock_queue),
    ):
        await processor.process()

    assert job.status == "failed"  # this attempt is done -- fallback is a NEW job
    assert influencer.api_supported is False
    mock_job_repo.create.assert_awaited_once_with(influencer_id)
    mock_queue.enqueue.assert_awaited_once()
    enqueued_message = mock_queue.enqueue.call_args.args[0]
    assert enqueued_message.backend == "cookies"
    assert enqueued_message.handle == "personal_acct"


# ── _upsert_post / _record_metrics_snapshot (pure-ish helpers) ──────────

def _media_item(**overrides) -> InstagramMediaItem:
    defaults = dict(
        id="123", pk="123", code="ABC123", media_type=2,
        taken_at=int(datetime.now(timezone.utc).timestamp()),
        like_count=10, comment_count=2,
        media_url="https://cdn/video.mp4", thumbnail_url="https://cdn/thumb.jpg",
        children=None, permalink="https://instagram.com/reel/ABC123/",
    )
    defaults.update(overrides)
    return InstagramMediaItem(**defaults)


@pytest.mark.asyncio
async def test_upsert_post_refreshes_urls_on_existing_post_without_touching_other_fields():
    processor = InstagramGraphJobProcessor(
        ScrapeJobMessage(job_id=uuid4(), influencer_id=uuid4(), handle="x", platform="instagram", backend="graph")
    )
    existing = Post(id=uuid4(), shortcode="ABC123", caption="old caption", media_url="https://stale/old.mp4")
    item = _media_item(media_url="https://cdn/fresh.mp4", thumbnail_url="https://cdn/fresh_thumb.jpg")

    result = await processor._upsert_post(session=MagicMock(), item=item, existing=existing)

    assert result is existing
    assert result.media_url == "https://cdn/fresh.mp4"
    assert result.thumbnail_url == "https://cdn/fresh_thumb.jpg"
    assert result.caption == "old caption"  # untouched -- comments/caption aren't this processor's job to update


@pytest.mark.asyncio
async def test_upsert_post_creates_new_post_with_expected_fields():
    processor = InstagramGraphJobProcessor(
        ScrapeJobMessage(job_id=uuid4(), influencer_id=uuid4(), handle="x", platform="instagram", backend="graph")
    )
    session = MagicMock()
    item = InstagramMediaItem(
        id="1", pk="1", code="NEW1", media_type=1, taken_at=int(datetime.now(timezone.utc).timestamp()),
        caption={"text": "hello world"}, like_count=5, comment_count=1,
        media_url="https://cdn/img.jpg", thumbnail_url=None, children=None, permalink="https://instagram.com/p/NEW1/",
    )

    result = await processor._upsert_post(session=session, item=item, existing=None)

    session.add.assert_called_once_with(result)
    assert result.shortcode == "NEW1"
    assert result.caption == "hello world"
    assert result.media_url == "https://cdn/img.jpg"


@pytest.mark.asyncio
async def test_record_metrics_snapshot_never_sets_views_on_new_row():
    processor = InstagramGraphJobProcessor(
        ScrapeJobMessage(job_id=uuid4(), influencer_id=uuid4(), handle="x", platform="instagram", backend="graph")
    )
    post = Post(id=uuid4(), shortcode="ABC123")
    item = _media_item(like_count=42, comment_count=7)

    session = MagicMock()
    execute_result = MagicMock()
    execute_result.scalar_one_or_none = MagicMock(return_value=None)  # no existing same-day snapshot
    session.execute = AsyncMock(return_value=execute_result)

    await processor._record_metrics_snapshot(session, post, item)

    session.add.assert_called_once()
    snapshot = session.add.call_args.args[0]
    assert snapshot.likes == 42
    assert snapshot.comments == 7
    assert snapshot.views is None
    assert snapshot.reposts is None


@pytest.mark.asyncio
async def test_record_metrics_snapshot_updates_in_place_without_touching_views():
    """If an enrichment job already wrote today's snapshot with a real
    view count, this processor's re-run must update likes/comments on
    that SAME row -- not insert a duplicate, and not touch views."""
    processor = InstagramGraphJobProcessor(
        ScrapeJobMessage(job_id=uuid4(), influencer_id=uuid4(), handle="x", platform="instagram", backend="graph")
    )
    post = Post(id=uuid4(), shortcode="ABC123")
    item = _media_item(like_count=99, comment_count=12)

    existing_snapshot = SimpleNamespace(likes=10, comments=2, views=50000, reposts=3)
    session = MagicMock()
    execute_result = MagicMock()
    execute_result.scalar_one_or_none = MagicMock(return_value=existing_snapshot)
    session.execute = AsyncMock(return_value=execute_result)

    await processor._record_metrics_snapshot(session, post, item)

    session.add.assert_not_called()
    assert existing_snapshot.likes == 99
    assert existing_snapshot.comments == 12
    assert existing_snapshot.views == 50000  # untouched
    assert existing_snapshot.reposts == 3  # untouched


# ── _run_scrape respects scrape_posts_since (regression: found live against
# real myntra data -- this cutoff was silently never checked at all) ──────

@pytest.mark.asyncio
async def test_run_scrape_stops_pagination_at_scrape_posts_since_cutoff(monkeypatch):
    influencer_id = uuid4()
    processor = InstagramGraphJobProcessor(
        ScrapeJobMessage(job_id=uuid4(), influencer_id=influencer_id, handle="myntra", platform="instagram", backend="graph")
    )
    influencer = SimpleNamespace(
        id=influencer_id, platform_user_id=None, profile_pic_url=None,
        scrape_posts_since=datetime(2026, 1, 1).date(),
    )
    job = SimpleNamespace(id=uuid4(), posts_processed=0)

    in_window_item = _media_item(code="IN_WINDOW", taken_at=int(datetime(2026, 6, 1, tzinfo=timezone.utc).timestamp()))
    out_of_window_item = _media_item(code="TOO_OLD", taken_at=int(datetime(2025, 11, 15, tzinfo=timezone.utc).timestamp()))

    processor.client = MagicMock()
    processor.client.get_business_profile = AsyncMock(return_value={"placeholder": "bd"})
    processor.client.get_business_media = AsyncMock()  # must never be called -- pagination stops first

    monkeypatch.setattr("app.workers.instagram_graph_job_processor.parse_profile", MagicMock(return_value=SimpleNamespace(
        username="myntra", pk="1", profile_pic_url=None, follower_count=1, following_count=1, media_count=1,
        biography="", external_url=None, is_business_account=True, is_professional_account=True,
    )))
    monkeypatch.setattr(
        "app.workers.instagram_graph_job_processor.parse_media_items",
        MagicMock(return_value=[in_window_item, out_of_window_item]),
    )
    monkeypatch.setattr(
        "app.workers.instagram_graph_job_processor.extract_media_cursor", MagicMock(return_value="some_cursor")
    )

    session = MagicMock()
    session.get = AsyncMock(return_value=influencer)
    session.commit = AsyncMock()
    session.flush = AsyncMock()
    execute_result = MagicMock()
    execute_result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
    session.execute = AsyncMock(return_value=execute_result)

    await processor._run_scrape(session, job)

    assert job.posts_processed == 1  # only the in-window item
    processor.client.get_business_media.assert_not_called()  # stopped before needing page 2


# ── steady-state early-stop (regression: found live -- a repeat scrape of
# the same account re-walked up to _MAX_MEDIA_PAGES from scratch every run) ─

@pytest.mark.asyncio
async def test_run_scrape_stops_at_known_post_outside_refresh_window(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "COMMENT_SYNC_WINDOW_DAYS", 90)
    influencer_id = uuid4()
    processor = InstagramGraphJobProcessor(
        ScrapeJobMessage(job_id=uuid4(), influencer_id=influencer_id, handle="myntra", platform="instagram", backend="graph")
    )
    influencer = SimpleNamespace(
        id=influencer_id, platform_user_id=None, profile_pic_url=None, scrape_posts_since=None,
    )
    job = SimpleNamespace(id=uuid4(), posts_processed=0)

    new_item = _media_item(code="BRAND_NEW", taken_at=int(datetime.now(timezone.utc).timestamp()))
    old_known_item = _media_item(
        code="ALREADY_KNOWN_OLD",
        taken_at=int((datetime.now(timezone.utc) - timedelta(days=200)).timestamp()),
    )
    existing_old_post = Post(id=uuid4(), shortcode="ALREADY_KNOWN_OLD")

    processor.client = MagicMock()
    processor.client.get_business_profile = AsyncMock(return_value={"placeholder": "bd"})
    processor.client.get_business_media = AsyncMock()  # must never be called -- stops on page 1

    monkeypatch.setattr("app.workers.instagram_graph_job_processor.parse_profile", MagicMock(return_value=SimpleNamespace(
        username="myntra", pk="1", profile_pic_url=None, follower_count=1, following_count=1, media_count=1,
        biography="", external_url=None, is_business_account=True, is_professional_account=True,
    )))
    monkeypatch.setattr(
        "app.workers.instagram_graph_job_processor.parse_media_items",
        MagicMock(return_value=[new_item, old_known_item]),
    )
    monkeypatch.setattr(
        "app.workers.instagram_graph_job_processor.extract_media_cursor", MagicMock(return_value="some_cursor")
    )

    session = MagicMock()
    session.get = AsyncMock(return_value=influencer)
    session.commit = AsyncMock()
    session.flush = AsyncMock()
    execute_result = MagicMock()
    execute_result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[existing_old_post])))
    session.execute = AsyncMock(return_value=execute_result)

    await processor._run_scrape(session, job)

    assert job.posts_processed == 1  # only BRAND_NEW counted as new
    processor.client.get_business_media.assert_not_called()  # stopped before page 2


@pytest.mark.asyncio
async def test_run_scrape_keeps_refreshing_known_post_inside_window(monkeypatch):
    """A known post still inside the refresh window must have its metrics
    refreshed AND pagination must continue past it (unlike the
    outside-window case above)."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "COMMENT_SYNC_WINDOW_DAYS", 90)
    influencer_id = uuid4()
    processor = InstagramGraphJobProcessor(
        ScrapeJobMessage(job_id=uuid4(), influencer_id=influencer_id, handle="myntra", platform="instagram", backend="graph")
    )
    influencer = SimpleNamespace(
        id=influencer_id, platform_user_id=None, profile_pic_url=None, scrape_posts_since=None,
    )
    job = SimpleNamespace(id=uuid4(), posts_processed=0)

    recent_known_item = _media_item(
        code="KNOWN_RECENT", taken_at=int((datetime.now(timezone.utc) - timedelta(days=5)).timestamp())
    )
    existing_recent_post = Post(id=uuid4(), shortcode="KNOWN_RECENT", media_url="https://stale/old.mp4")

    processor.client = MagicMock()
    processor.client.get_business_profile = AsyncMock(return_value={"placeholder": "bd"})
    processor.client.get_business_media = AsyncMock(return_value={"placeholder": "bd2"})

    monkeypatch.setattr("app.workers.instagram_graph_job_processor.parse_profile", MagicMock(return_value=SimpleNamespace(
        username="myntra", pk="1", profile_pic_url=None, follower_count=1, following_count=1, media_count=1,
        biography="", external_url=None, is_business_account=True, is_professional_account=True,
    )))
    monkeypatch.setattr(
        "app.workers.instagram_graph_job_processor.parse_media_items",
        MagicMock(side_effect=[[recent_known_item], []]),  # page 2 empty -> loop ends naturally
    )
    cursor_mock = MagicMock(side_effect=["next_cursor", ""])
    monkeypatch.setattr("app.workers.instagram_graph_job_processor.extract_media_cursor", cursor_mock)

    session = MagicMock()
    session.get = AsyncMock(return_value=influencer)
    session.commit = AsyncMock()
    session.flush = AsyncMock()
    execute_result = MagicMock()
    execute_result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[existing_recent_post])))
    session.execute = AsyncMock(return_value=execute_result)

    await processor._run_scrape(session, job)

    assert job.posts_processed == 0  # no NEW posts -- only a known one refreshed
    assert existing_recent_post.media_url == "https://cdn/video.mp4"  # refreshed, not the stale value
    processor.client.get_business_media.assert_called_once()  # pagination continued past it

