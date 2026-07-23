from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.core.exceptions import ScraperBlockedError
from app.models.post import Post
from app.queue.base import ScrapeJobMessage
from app.schemas.instagram import InstagramMediaItem
from app.workers.job_processor import JobProcessor


def _processor() -> JobProcessor:
    return JobProcessor(
        ScrapeJobMessage(job_id=uuid4(), influencer_id=uuid4(), handle="myntra", platform="instagram", job_type="scrape")
    )


def _media_item(**overrides) -> InstagramMediaItem:
    defaults = dict(
        id="1", pk="1", code="ABC123", media_type=2,
        taken_at=int((datetime.now(timezone.utc) - timedelta(hours=1)).timestamp()),
        like_count=10, comment_count=2, view_count=5000, play_count=0, reshare_count=3,
        is_paid_partnership=True, product_type="clips",
        music_metadata={"song": "x"}, locations=[{"name": "Mumbai"}],
        coauthor_producers=[{"username": "y"}], tagged_usernames=[{"username": "z"}],
        accessibility_caption="a video", counts_disabled=False,
    )
    defaults.update(overrides)
    return InstagramMediaItem(**defaults)


@pytest.mark.asyncio
async def test_run_scrape_propagates_scraper_blocked_error_from_comment_sync(monkeypatch):
    """Regression: a dead cookie session made every single comment sync in
    a run fail with ScraperBlockedError, but _sync_one's blanket except
    Exception swallowed it as a per-post warning -- the job still reported
    status=completed and the account was never marked at fault, so a
    provably dead session kept getting leased for every future job.
    ScraperBlockedError/ScraperRateLimitError must propagate out of
    _run_scrape so process()'s except blocks can fail the job and flag
    the account. See instagram_enrich_processor's identical fix/test."""
    processor = _processor()
    influencer_id = processor.message.influencer_id
    influencer = SimpleNamespace(
        id=influencer_id, handle="myntra", scrape_posts_since=None, max_comments_per_post=None,
        backfill_completed=True, backfill_cursor=None, platform_user_id="123", profile_pic_url=None,
    )
    job = SimpleNamespace(id=uuid4(), comments_processed=0, posts_processed=0)

    existing_post = Post(id=uuid4(), shortcode="ABC123", media_pk="1", comments_synced_count=0)
    item = _media_item(code="ABC123")

    processor.client = MagicMock()
    processor.client.get_user_info = AsyncMock(return_value={})
    processor.client.get_user_feed = AsyncMock(return_value={"items": []})

    monkeypatch.setattr(
        "app.workers.job_processor.InstagramParser.parse_user_info",
        MagicMock(return_value=SimpleNamespace(
            pk=123, profile_pic_url=None, follower_count=1, following_count=1, media_count=1,
            biography="", biography_with_entities=None, bio_links=None, pronouns=None, external_url=None,
            is_verified=False, is_business_account=False, is_professional_account=False, category_name=None,
            category_enum=None, overall_category_name=None, business_contact_method=None, business_email=None,
            business_phone_number=None, highlight_reel_count=0, has_clips=False, has_guides=False,
            has_channel=False, mutual_followers_count=None, is_verified_by_mv4b=False,
            hide_like_and_view_counts=False, has_ar_effects=False, business_category_name=None,
        )),
    )
    monkeypatch.setattr(
        "app.workers.job_processor.InstagramParser.parse_feed",
        MagicMock(return_value=([item], "")),
    )
    monkeypatch.setattr("app.workers.job_processor.last_comment_count", AsyncMock(return_value=None))
    monkeypatch.setattr(
        "app.workers.job_processor.sync_comments_for_post",
        AsyncMock(side_effect=ScraperBlockedError(handle="myntra")),
    )
    monkeypatch.setattr("app.workers.job_processor.update_engagement_timing_features", AsyncMock())

    session = MagicMock()
    session.get = AsyncMock(return_value=influencer)
    session.commit = AsyncMock()
    execute_result = MagicMock()
    execute_result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[existing_post])))
    session.execute = AsyncMock(return_value=execute_result)

    session_cm = MagicMock()
    session_cm.__aenter__ = AsyncMock(return_value=session)
    session_cm.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr("app.workers.job_processor.get_session", MagicMock(return_value=session_cm))

    with patch.object(processor, "_record_metrics_snapshot", AsyncMock()):
        with pytest.raises(ScraperBlockedError):
            await processor._run_scrape(session, job)
