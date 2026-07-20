from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.models.post import Post
from app.queue.base import ScrapeJobMessage
from app.schemas.instagram import InstagramMediaItem
from app.workers.instagram_enrich_processor import InstagramEnrichProcessor


def _processor() -> InstagramEnrichProcessor:
    return InstagramEnrichProcessor(
        ScrapeJobMessage(job_id=uuid4(), influencer_id=uuid4(), handle="myntra", platform="instagram", job_type="enrich")
    )


def _media_item(**overrides) -> InstagramMediaItem:
    defaults = dict(
        id="1", pk="1", code="ABC123", media_type=2, taken_at=0,
        like_count=10, comment_count=2, view_count=5000, play_count=0, reshare_count=3,
        is_paid_partnership=True, product_type="clips",
        music_metadata={"song": "x"}, locations=[{"name": "Mumbai"}],
        coauthor_producers=[{"username": "y"}], tagged_usernames=[{"username": "z"}],
        accessibility_caption="a video", counts_disabled=False,
    )
    defaults.update(overrides)
    return InstagramMediaItem(**defaults)


# ── _apply_cookie_only_fields (pure) ─────────────────────────────────────

def test_apply_cookie_only_fields_sets_expected_columns():
    processor = _processor()
    post = Post(id=uuid4(), shortcode="ABC123")
    item = _media_item()

    processor._apply_cookie_only_fields(post, item)

    assert post.is_paid_partnership is True
    assert post.music_metadata == {"song": "x"}
    assert post.locations == [{"name": "Mumbai"}]
    assert post.coauthor_producers == [{"username": "y"}]
    assert post.tagged_usernames == [{"username": "z"}]
    assert post.accessibility_caption == "a video"
    assert post.counts_disabled is False


def test_apply_cookie_only_fields_backfills_original_dimensions():
    """Regression: Business Discovery never returns original media
    dimensions, so a Graph-created post's original_height/width stayed
    None forever until enrichment backfills them from the cookie feed."""
    processor = _processor()
    post = Post(id=uuid4(), shortcode="ABC123", original_height=None, original_width=None)
    item = _media_item(original_height=1920, original_width=1080)

    processor._apply_cookie_only_fields(post, item)

    assert post.original_height == 1920
    assert post.original_width == 1080


# ── _merge_metrics_snapshot ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_merge_metrics_snapshot_updates_existing_row_no_duplicate():
    """Regression guard for docs/INSTAGRAM_HYBRID_IMPLEMENTATION.md PR3 §3.4:
    if the API scrape already wrote today's snapshot, enrichment must
    update it in place -- never insert a second same-day row -- and must
    not touch likes/comments (the API's to own)."""
    processor = _processor()
    post = Post(id=uuid4(), shortcode="ABC123")
    item = _media_item(view_count=99999, reshare_count=7)

    existing_snapshot = SimpleNamespace(likes=10, comments=2, views=None, reposts=None)
    session = MagicMock()
    execute_result = MagicMock()
    execute_result.scalar_one_or_none = MagicMock(return_value=existing_snapshot)
    session.execute = AsyncMock(return_value=execute_result)

    await processor._merge_metrics_snapshot(session, post, item)

    session.add.assert_not_called()  # no duplicate row inserted
    assert existing_snapshot.views == 99999
    assert existing_snapshot.reposts == 7
    assert existing_snapshot.likes == 10  # untouched -- API owns this
    assert existing_snapshot.comments == 2  # untouched -- API owns this


@pytest.mark.asyncio
async def test_merge_metrics_snapshot_inserts_full_row_when_none_exists_today():
    """No API scrape ran today for this post -- enrichment inserts a
    complete row from the cookie item (same shape JobProcessor writes)."""
    processor = _processor()
    post = Post(id=uuid4(), shortcode="ABC123")
    item = _media_item(like_count=42, comment_count=8, view_count=1234, reshare_count=1)

    session = MagicMock()
    execute_result = MagicMock()
    execute_result.scalar_one_or_none = MagicMock(return_value=None)
    session.execute = AsyncMock(return_value=execute_result)

    await processor._merge_metrics_snapshot(session, post, item)

    session.add.assert_called_once()
    snapshot = session.add.call_args.args[0]
    assert snapshot.likes == 42
    assert snapshot.comments == 8
    assert snapshot.views == 1234
    assert snapshot.reposts == 1


@pytest.mark.asyncio
async def test_merge_metrics_snapshot_views_none_for_non_video_non_reel():
    """Image/carousel posts have no public view metric -- must stay None,
    not a fabricated 0, matching JobProcessor._record_metrics_snapshot's
    has_view_metric rule."""
    processor = _processor()
    post = Post(id=uuid4(), shortcode="ABC123")
    item = _media_item(media_type=1, product_type=None, view_count=999)  # IMAGE, not a reel

    session = MagicMock()
    execute_result = MagicMock()
    execute_result.scalar_one_or_none = MagicMock(return_value=None)
    session.execute = AsyncMock(return_value=execute_result)

    await processor._merge_metrics_snapshot(session, post, item)

    snapshot = session.add.call_args.args[0]
    assert snapshot.views is None


# ── _run_enrich: unmatched items, comment sync invocation ────────────────

@pytest.mark.asyncio
async def test_run_enrich_skips_unmatched_feed_items_without_erroring(monkeypatch):
    """A feed item posted since the last API scrape has no matching Post
    row yet -- must be skipped (counted, logged), not create a Post or
    raise. The next API cycle picks it up."""
    processor = _processor()
    influencer_id = processor.message.influencer_id
    influencer = SimpleNamespace(id=influencer_id, handle="myntra", scrape_posts_since=None)

    job = SimpleNamespace(id=uuid4(), comments_processed=0)

    unmatched_item = _media_item(code="NEW_UNMATCHED")

    processor.client = MagicMock()
    processor.client.get_user_feed = AsyncMock(return_value={"items": []})

    monkeypatch.setattr(
        "app.workers.instagram_enrich_processor.InstagramParser.parse_feed",
        MagicMock(return_value=([unmatched_item], "")),
    )

    session = MagicMock()
    session.get = AsyncMock(return_value=influencer)
    session.commit = AsyncMock()
    execute_result = MagicMock()
    execute_result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))  # no existing posts
    session.execute = AsyncMock(return_value=execute_result)

    await processor._run_enrich(session, job)

    # Nothing to sync -- no Post matched, so comment sync gathers zero tasks.
    assert job.comments_processed == 0


@pytest.mark.asyncio
async def test_run_enrich_syncs_comments_for_matched_posts(monkeypatch):
    processor = _processor()
    influencer_id = processor.message.influencer_id
    influencer = SimpleNamespace(id=influencer_id, handle="myntra", scrape_posts_since=None)
    job = SimpleNamespace(id=uuid4(), comments_processed=0)

    existing_post = Post(id=uuid4(), shortcode="ABC123", media_pk="1")
    item = _media_item(code="ABC123")

    processor.client = MagicMock()
    processor.client.get_user_feed = AsyncMock(return_value={"items": []})

    monkeypatch.setattr(
        "app.workers.instagram_enrich_processor.InstagramParser.parse_feed",
        MagicMock(return_value=([item], "")),
    )
    monkeypatch.setattr("app.workers.instagram_enrich_processor.sync_comments_for_post", AsyncMock(return_value=5))
    monkeypatch.setattr("app.workers.instagram_enrich_processor.update_engagement_timing_features", AsyncMock())

    session = MagicMock()
    session.get = AsyncMock(return_value=influencer)
    session.commit = AsyncMock()
    execute_result = MagicMock()
    execute_result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[existing_post])))
    session.execute = AsyncMock(return_value=execute_result)

    # _run_enrich opens its own get_session() for the concurrent comment-sync
    # tasks -- patch it to hand back the same mocked session.
    session_cm = MagicMock()
    session_cm.__aenter__ = AsyncMock(return_value=session)
    session_cm.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr("app.workers.instagram_enrich_processor.get_session", MagicMock(return_value=session_cm))

    await processor._run_enrich(session, job)

    assert job.comments_processed == 5


@pytest.mark.asyncio
async def test_run_enrich_skips_comment_sync_when_count_unchanged(monkeypatch):
    """Regression: every matched post was re-synced for comments on every
    single enrich run, even when nothing about its comment count had
    changed since last time -- same diffing optimization JobProcessor
    already has, just never ported here."""
    processor = _processor()
    influencer_id = processor.message.influencer_id
    influencer = SimpleNamespace(id=influencer_id, handle="myntra", scrape_posts_since=None)
    job = SimpleNamespace(id=uuid4(), comments_processed=0)

    existing_post = Post(id=uuid4(), shortcode="ABC123", media_pk="1")
    item = _media_item(code="ABC123", comment_count=5)

    processor.client = MagicMock()
    processor.client.get_user_feed = AsyncMock(return_value={"items": []})

    monkeypatch.setattr(
        "app.workers.instagram_enrich_processor.InstagramParser.parse_feed",
        MagicMock(return_value=([item], "")),
    )
    sync_mock = AsyncMock(return_value=5)
    monkeypatch.setattr("app.workers.instagram_enrich_processor.sync_comments_for_post", sync_mock)
    monkeypatch.setattr("app.workers.instagram_enrich_processor.update_engagement_timing_features", AsyncMock())

    post_lookup_result = MagicMock()
    post_lookup_result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[existing_post])))
    metrics_lookup_result = MagicMock()
    metrics_lookup_result.scalar_one_or_none = MagicMock(return_value=None)  # no same-day snapshot yet
    comment_count_result = MagicMock()
    comment_count_result.scalar_one_or_none = MagicMock(return_value=5)  # matches item.comment_count -- unchanged

    session = MagicMock()
    session.get = AsyncMock(return_value=influencer)
    session.commit = AsyncMock()
    session.execute = AsyncMock(side_effect=[post_lookup_result, metrics_lookup_result, comment_count_result])

    session_cm = MagicMock()
    session_cm.__aenter__ = AsyncMock(return_value=session)
    session_cm.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr("app.workers.instagram_enrich_processor.get_session", MagicMock(return_value=session_cm))

    await processor._run_enrich(session, job)

    sync_mock.assert_not_called()
    assert job.comments_processed == 0


@pytest.mark.asyncio
async def test_run_enrich_stops_pagination_at_scrape_posts_since_cutoff(monkeypatch):
    """Regression: enrichment never checked scrape_posts_since either --
    it would walk INSTAGRAM_ENRICH_FEED_PAGES worth of history regardless
    of a configured cutoff."""
    processor = _processor()
    influencer_id = processor.message.influencer_id
    influencer = SimpleNamespace(
        id=influencer_id, handle="myntra", scrape_posts_since=datetime(2026, 1, 1).date(),
    )
    job = SimpleNamespace(id=uuid4(), comments_processed=0)

    old_item = _media_item(code="TOO_OLD", taken_at=int(datetime(2025, 11, 15, tzinfo=timezone.utc).timestamp()))

    processor.client = MagicMock()
    processor.client.get_user_feed = AsyncMock(return_value={"items": []})

    monkeypatch.setattr(
        "app.workers.instagram_enrich_processor.InstagramParser.parse_feed",
        MagicMock(return_value=([old_item], "next_cursor")),  # has a next page, but must not be fetched
    )

    session = MagicMock()
    session.get = AsyncMock(return_value=influencer)
    session.commit = AsyncMock()
    execute_result = MagicMock()
    execute_result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
    session.execute = AsyncMock(return_value=execute_result)

    await processor._run_enrich(session, job)

    assert processor.client.get_user_feed.call_count == 1  # stopped, didn't fetch page 2


@pytest.mark.asyncio
async def test_run_enrich_captures_raw_response(monkeypatch):
    """Regression: enrichment never captured a RawResponse at all for its
    get_user_feed calls, unlike JobProcessor's own "one raw payload per
    run" convention used for diagnosing field-shape drift."""
    processor = _processor()
    influencer_id = processor.message.influencer_id
    influencer = SimpleNamespace(id=influencer_id, handle="myntra", scrape_posts_since=None)
    job = SimpleNamespace(id=uuid4(), comments_processed=0)

    processor.client = MagicMock()
    processor.client.get_user_feed = AsyncMock(return_value={"items": []})

    monkeypatch.setattr(
        "app.workers.instagram_enrich_processor.InstagramParser.parse_feed", MagicMock(return_value=([], ""))
    )

    session = MagicMock()
    session.get = AsyncMock(return_value=influencer)
    session.commit = AsyncMock()

    await processor._run_enrich(session, job)

    from app.models.raw_response import RawResponse
    added = [call.args[0] for call in session.add.call_args_list]
    assert any(isinstance(obj, RawResponse) and obj.endpoint == "ig_enrich_get_user_feed" for obj in added)


# ── _maybe_dispatch_enrich cycle gating ───────────────────────────────────

@pytest.mark.asyncio
async def test_maybe_dispatch_enrich_skipped_when_cycles_is_zero(monkeypatch):
    from app.workers.instagram_graph_job_processor import InstagramGraphJobProcessor
    from app.core.config import settings

    monkeypatch.setattr(settings, "INSTAGRAM_ENRICH_EVERY_N_CYCLES", 0)
    processor = InstagramGraphJobProcessor(
        ScrapeJobMessage(job_id=uuid4(), influencer_id=uuid4(), handle="x", platform="instagram", backend="graph")
    )
    mock_dispatch = AsyncMock()
    monkeypatch.setattr(
        "app.workers.instagram_graph_job_processor.DispatchService",
        MagicMock(return_value=SimpleNamespace(dispatch_enrich_job=mock_dispatch)),
    )

    await processor._maybe_dispatch_enrich(session=MagicMock())

    mock_dispatch.assert_not_called()


@pytest.mark.asyncio
async def test_maybe_dispatch_enrich_dispatches_every_cycle_when_n_is_one(monkeypatch):
    from app.workers.instagram_graph_job_processor import InstagramGraphJobProcessor
    from app.core.config import settings

    monkeypatch.setattr(settings, "INSTAGRAM_ENRICH_EVERY_N_CYCLES", 1)
    influencer_id = uuid4()
    processor = InstagramGraphJobProcessor(
        ScrapeJobMessage(job_id=uuid4(), influencer_id=influencer_id, handle="x", platform="instagram", backend="graph")
    )
    mock_dispatch = AsyncMock()
    monkeypatch.setattr(
        "app.workers.instagram_graph_job_processor.DispatchService",
        MagicMock(return_value=SimpleNamespace(dispatch_enrich_job=mock_dispatch)),
    )

    await processor._maybe_dispatch_enrich(session=MagicMock())

    mock_dispatch.assert_awaited_once_with(influencer_id)
