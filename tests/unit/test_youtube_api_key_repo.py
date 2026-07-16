from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.models.youtube_api_key import YouTubeApiKey
from app.repositories.youtube_api_key_repo import YouTubeApiKeyRepo
from app.scraper.youtube_client import next_midnight_pacific


def test_next_midnight_pacific_is_always_in_the_future():
    now = datetime.now(timezone.utc)
    reset = next_midnight_pacific(now)
    assert reset > now
    assert reset - now <= timedelta(days=1, hours=1)  # DST-safe upper bound


@pytest.mark.asyncio
async def test_reset_if_due_zeroes_usage_and_reactivates_exhausted_key():
    repo = YouTubeApiKeyRepo(session=None)  # _reset_if_due never touches the session
    key = YouTubeApiKey(
        label="k1",
        status="quota_exhausted",
        quota_used_today=9999,
        quota_reset_at=datetime.now(timezone.utc) - timedelta(seconds=1),  # already due
    )

    await repo._reset_if_due(key)

    assert key.status == "active"
    assert key.quota_used_today == 0
    assert key.quota_reset_at is None


@pytest.mark.asyncio
async def test_reset_if_due_leaves_key_untouched_before_reset_time():
    repo = YouTubeApiKeyRepo(session=None)
    reset_at = datetime.now(timezone.utc) + timedelta(hours=1)
    key = YouTubeApiKey(label="k1", status="quota_exhausted", quota_used_today=500, quota_reset_at=reset_at)

    await repo._reset_if_due(key)

    assert key.status == "quota_exhausted"
    assert key.quota_used_today == 500
    assert key.quota_reset_at == reset_at


@pytest.mark.asyncio
async def test_reset_if_due_is_a_noop_for_active_key_with_no_reset_pending():
    repo = YouTubeApiKeyRepo(session=None)
    key = YouTubeApiKey(label="k1", status="active", quota_used_today=10, quota_reset_at=None)

    await repo._reset_if_due(key)

    assert key.status == "active"
    assert key.quota_used_today == 10
