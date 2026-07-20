from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.models.post import Post
from app.schemas.instagram import InstagramComment
from app.workers.comment_sync import normalize_comment, sync_comments_for_post, sync_replies


def _comment(**overrides) -> InstagramComment:
    defaults = dict(comment_id="c1", username="fan_account", text="nice post", child_comment_count=0, created_at=0)
    defaults.update(overrides)
    return InstagramComment(**defaults)


# ── normalize_comment (pure) ─────────────────────────────────────────────

def test_normalize_comment_flags_creator_by_case_insensitive_username_match():
    comment = _comment(username="MyntraOfficial")
    result = normalize_comment(comment, creator_handle="myntraofficial")
    assert result.is_from_creator is True


def test_normalize_comment_non_creator_username():
    comment = _comment(username="random_fan")
    result = normalize_comment(comment, creator_handle="myntraofficial")
    assert result.is_from_creator is False


def test_normalize_comment_falls_back_to_now_when_created_at_missing():
    comment = _comment(created_at=0)
    before = datetime.now(timezone.utc)
    result = normalize_comment(comment, creator_handle="x")
    assert result.commented_at >= before


# ── sync_comments_for_post / sync_replies (shared, client+session mocked) ─

@pytest.mark.asyncio
async def test_sync_comments_for_post_walks_replies_only_when_count_changed(monkeypatch):
    """Regression guard for the PR3 extraction (docs/INSTAGRAM_HYBRID_IMPLEMENTATION.md
    §3.1): a thread whose child_comment_count matches what's already
    stored must NOT trigger a reply-fetch call."""
    post = Post(id=uuid4(), media_pk="pk1", permalink="https://instagram.com/p/x/", shortcode="x")

    unchanged_thread = _comment(comment_id="c1", child_comment_count=2)
    changed_thread = _comment(comment_id="c2", child_comment_count=3)

    client = MagicMock()
    client.get_media_comments = AsyncMock(
        return_value={"edges": []}  # actual content doesn't matter -- parser is monkeypatched below
    )
    client.get_comment_replies = AsyncMock(return_value={"edges": []})

    monkeypatch.setattr(
        "app.workers.comment_sync.InstagramParser.parse_comments",
        MagicMock(return_value=([unchanged_thread, changed_thread], "", False)),
    )
    monkeypatch.setattr(
        "app.workers.comment_sync.InstagramParser.parse_replies",
        MagicMock(return_value=([], "", False)),
    )
    monkeypatch.setattr(
        "app.workers.comment_sync.previous_child_counts",
        AsyncMock(return_value={"c1": 2, "c2": 1}),  # c1 unchanged, c2 changed (1 -> 3)
    )
    monkeypatch.setattr("app.workers.comment_sync.upsert_comments_bulk", AsyncMock())

    session = MagicMock()
    session.commit = AsyncMock()

    total = await sync_comments_for_post(session, client, post, creator_handle="myntra")

    client.get_comment_replies.assert_awaited_once()  # only for c2, not c1
    called_parent_id = client.get_comment_replies.call_args.args[1]
    assert called_parent_id == "c2"
    assert total == 2  # 2 top-level comments (reply fetch itself returned 0 replies)


@pytest.mark.asyncio
async def test_sync_replies_paginates_until_has_more_is_false(monkeypatch):
    post = Post(id=uuid4(), media_pk="pk1", permalink="https://instagram.com/p/x/", shortcode="x")
    parent = _comment(comment_id="parent1", child_comment_count=5)

    client = MagicMock()
    client.get_comment_replies = AsyncMock(return_value={"edges": []})

    page1 = ([_comment(comment_id="r1")], "cursor2", True)
    page2 = ([_comment(comment_id="r2")], "", False)
    parse_replies_mock = MagicMock(side_effect=[page1, page2])
    monkeypatch.setattr("app.workers.comment_sync.InstagramParser.parse_replies", parse_replies_mock)
    monkeypatch.setattr("app.workers.comment_sync.upsert_comments_bulk", AsyncMock())

    session = MagicMock()
    session.commit = AsyncMock()

    total = await sync_replies(session, client, post, parent, creator_handle="myntra")

    assert total == 2
    assert client.get_comment_replies.call_count == 2
