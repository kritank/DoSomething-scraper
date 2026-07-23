from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.models.post import Post
from app.schemas.instagram import InstagramComment
from app.workers.comment_sync import (
    _UPDATE_COLUMNS,
    get_latest_comment_synced_at,
    normalize_comment,
    sync_comments_for_post,
    sync_replies,
)


def _comment(**overrides) -> InstagramComment:
    defaults = dict(comment_id="c1", username="fan_account", text="nice post", child_comment_count=0, created_at=0)
    defaults.update(overrides)
    return InstagramComment(**defaults)


def _session(deleted_ids: list[str] | None = None, stored_count: int = 0) -> MagicMock:
    """A mocked session whose .execute() supports both the DELETE...RETURNING
    call _delete_missing_comments makes (in addition to commit) and the
    COUNT(*) call count_stored_comments/refresh_comments_synced_count
    makes -- used by every test whose walk completes, since that path
    always attempts a tombstone pass and always refreshes the completeness
    counter at the end."""
    session = MagicMock()
    session.commit = AsyncMock()
    execute_result = MagicMock()
    execute_result.all = MagicMock(return_value=[(cid,) for cid in (deleted_ids or [])])
    execute_result.scalar_one = MagicMock(return_value=stored_count)
    session.execute = AsyncMock(return_value=execute_result)
    return session


def test_update_columns_refreshes_verified_badge_and_display_name():
    """Regression test: a commenter's verified badge or display name can
    change between syncs -- these were only ever written on first INSERT,
    silently going stale on every re-sync after that."""
    assert "is_verified" in _UPDATE_COLUMNS
    assert "full_name" in _UPDATE_COLUMNS


# ── get_latest_comment_synced_at (pure query shape) ──────────────────────

@pytest.mark.asyncio
async def test_get_latest_comment_synced_at_returns_max_created_at():
    expected = datetime(2026, 7, 23, 11, 20, tzinfo=timezone.utc)
    session = MagicMock()
    execute_result = MagicMock()
    execute_result.scalar_one_or_none = MagicMock(return_value=expected)
    session.execute = AsyncMock(return_value=execute_result)

    result = await get_latest_comment_synced_at(session)

    assert result == expected


@pytest.mark.asyncio
async def test_get_latest_comment_synced_at_returns_none_when_no_comments_ever():
    session = MagicMock()
    execute_result = MagicMock()
    execute_result.scalar_one_or_none = MagicMock(return_value=None)
    session.execute = AsyncMock(return_value=execute_result)

    result = await get_latest_comment_synced_at(session)

    assert result is None


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

    session = _session()

    total = await sync_comments_for_post(session, client, post, creator_handle="myntra")

    client.get_comment_replies.assert_awaited_once()  # only for c2, not c1
    called_parent_id = client.get_comment_replies.call_args.args[1]
    assert called_parent_id == "c2"
    assert total == 2  # 2 top-level comments (reply fetch itself returned 0 replies)


@pytest.mark.asyncio
async def test_sync_comments_persists_cursor_when_truncated_by_page_cap(monkeypatch):
    """Regression test: a post with more top-level comments than one walk
    can cover (MAX_COMMENT_PAGES) must remember where it left off, or
    every future sync restarts from page 1 and never makes progress past
    the cap."""
    post = Post(id=uuid4(), media_pk="pk1", permalink="https://instagram.com/p/x/", shortcode="x")
    assert post.comment_sync_cursor is None

    monkeypatch.setattr("app.workers.comment_sync.MAX_COMMENT_PAGES", 2)
    client = MagicMock()
    client.get_media_comments = AsyncMock(return_value={})
    monkeypatch.setattr(
        "app.workers.comment_sync.InstagramParser.parse_comments",
        MagicMock(side_effect=[
            ([_comment(comment_id="c1")], "cursor2", True),
            ([_comment(comment_id="c2")], "cursor3", True),  # still has_more=True when the cap hits
        ]),
    )
    monkeypatch.setattr("app.workers.comment_sync.previous_child_counts", AsyncMock(return_value={}))
    monkeypatch.setattr("app.workers.comment_sync.upsert_comments_bulk", AsyncMock())

    session = _session()

    await sync_comments_for_post(session, client, post, creator_handle="myntra")

    # Cursor for the next unfetched page is persisted, not lost.
    assert post.comment_sync_cursor == "cursor3"
    # First call used the post's (initially None) stored cursor.
    assert client.get_media_comments.call_args_list[0].args[2] is None
    assert client.get_media_comments.call_args_list[1].args[2] == "cursor2"
    # Truncated by the page cap -- only saw c1/c2, not the post's full
    # top-level set, so must not tombstone anything else that's stored.
    # The one execute() call is the completeness-counter refresh, which
    # always runs regardless of how the walk stopped.
    assert session.execute.await_count == 1


@pytest.mark.asyncio
async def test_sync_comments_tombstones_deleted_top_level_comment(monkeypatch):
    """Regression test: a fresh walk that completes naturally has seen
    the post's COMPLETE current top-level set -- any stored comment not
    in it was removed on Instagram's side (author-deleted or moderated)
    and must be tombstoned, not left visible forever."""
    post = Post(id=uuid4(), media_pk="pk1", permalink="https://instagram.com/p/x/", shortcode="x")

    client = MagicMock()
    client.get_media_comments = AsyncMock(return_value={})
    monkeypatch.setattr(
        "app.workers.comment_sync.InstagramParser.parse_comments",
        MagicMock(return_value=([_comment(comment_id="c1")], "", False)),
    )
    monkeypatch.setattr("app.workers.comment_sync.previous_child_counts", AsyncMock(return_value={}))
    monkeypatch.setattr("app.workers.comment_sync.upsert_comments_bulk", AsyncMock())

    # "c2" no longer comes back from Instagram -- simulates a deleted
    # top-level comment. Its own reply "r1" should be cascade-removed too.
    session = _session(deleted_ids=["c2"])

    await sync_comments_for_post(session, client, post, creator_handle="myntra")

    # Three execute() calls: the top-level tombstone pass, the cascade
    # pass for c2's now-orphaned replies (since c2 came back non-empty),
    # and the completeness-counter refresh at the end.
    assert session.execute.await_count == 3


@pytest.mark.asyncio
async def test_sync_comments_resumes_from_stored_cursor(monkeypatch):
    post = Post(
        id=uuid4(), media_pk="pk1", permalink="https://instagram.com/p/x/", shortcode="x",
        comment_sync_cursor="resume_here",
    )

    client = MagicMock()
    client.get_media_comments = AsyncMock(return_value={})
    monkeypatch.setattr(
        "app.workers.comment_sync.InstagramParser.parse_comments",
        MagicMock(return_value=([_comment(comment_id="c1")], "", False)),
    )
    monkeypatch.setattr("app.workers.comment_sync.previous_child_counts", AsyncMock(return_value={}))
    monkeypatch.setattr("app.workers.comment_sync.upsert_comments_bulk", AsyncMock())

    session = _session()

    await sync_comments_for_post(session, client, post, creator_handle="myntra")

    client.get_media_comments.assert_awaited_once()
    assert client.get_media_comments.call_args.args[2] == "resume_here"
    # Walk completed naturally (has_more=False) -- cursor cleared so the
    # NEXT sync restarts from page 1 and re-diffs already-seen comments.
    assert post.comment_sync_cursor is None
    # Completed naturally, but this was a RESUMED walk (not started from
    # page 1) -- it only saw comments from the cursor onward, not the full
    # top-level set, so it must not tombstone anything it never reached.
    # The one execute() call is the completeness-counter refresh.
    assert session.execute.await_count == 1


@pytest.mark.asyncio
async def test_sync_comments_clears_stale_cursor_when_no_comments_returned(monkeypatch):
    """A stored cursor that no longer resolves to anything (expired,
    post's comments all deleted, etc.) must not leave the post stuck --
    clearing it lets the next sync restart from page 1 instead of
    repeating a dead cursor forever."""
    post = Post(
        id=uuid4(), media_pk="pk1", permalink="https://instagram.com/p/x/", shortcode="x",
        comment_sync_cursor="stale_cursor",
    )

    client = MagicMock()
    client.get_media_comments = AsyncMock(return_value={})
    monkeypatch.setattr(
        "app.workers.comment_sync.InstagramParser.parse_comments",
        MagicMock(return_value=([], "", False)),
    )
    session = _session()

    total = await sync_comments_for_post(session, client, post, creator_handle="myntra")

    assert total == 0
    assert post.comment_sync_cursor is None


@pytest.mark.asyncio
async def test_sync_comments_stops_at_per_post_cap_without_fetching(monkeypatch):
    """Regression test: a mega-viral post's true comment count can be
    mathematically unreachable at the account's rate limit -- once
    already at the cap, the walk must stop before even fetching another
    page, not burn a request only to discard the result."""
    post = Post(id=uuid4(), media_pk="pk1", permalink="https://instagram.com/p/x/", shortcode="x")

    client = MagicMock()
    client.get_media_comments = AsyncMock(return_value={})
    monkeypatch.setattr(
        "app.workers.comment_sync.InstagramParser.parse_comments",
        MagicMock(return_value=([_comment(comment_id="c1")], "cursor2", True)),
    )

    # Already at (in fact over) the cap.
    session = _session(stored_count=5000)

    total = await sync_comments_for_post(session, client, post, creator_handle="myntra", max_comments=5000)

    client.get_media_comments.assert_not_awaited()
    assert total == 0
    # Cap-hit is treated like a truncation (partial view) -- cursor
    # preserved in case the cap is raised later, no tombstone attempted.
    assert post.comment_sync_cursor is None  # never had one to begin with; unaffected by cap-hit path


@pytest.mark.asyncio
async def test_sync_comments_cap_hit_mid_walk_preserves_cursor(monkeypatch):
    post = Post(id=uuid4(), media_pk="pk1", permalink="https://instagram.com/p/x/", shortcode="x")

    client = MagicMock()
    client.get_media_comments = AsyncMock(return_value={})
    monkeypatch.setattr(
        "app.workers.comment_sync.InstagramParser.parse_comments",
        MagicMock(return_value=([_comment(comment_id="c1")], "cursor2", True)),
    )
    monkeypatch.setattr("app.workers.comment_sync.previous_child_counts", AsyncMock(return_value={}))
    monkeypatch.setattr("app.workers.comment_sync.upsert_comments_bulk", AsyncMock())

    # Under the cap on the page-1 check (so it fetches), at/over it by the
    # page-2 check (page 1 pushed it over), same value again for the
    # final completeness-refresh call.
    session = MagicMock()
    session.commit = AsyncMock()
    execute_result = MagicMock()
    execute_result.scalar_one = MagicMock(side_effect=[0, 5000, 5000])
    session.execute = AsyncMock(return_value=execute_result)

    total = await sync_comments_for_post(session, client, post, creator_handle="myntra", max_comments=5000)

    assert client.get_media_comments.await_count == 1  # fetched page 1, stopped before page 2
    assert total == 1
    # Cursor preserved (cap-hit, not a natural stop) -- a later cap raise
    # can resume from here instead of restarting from page 1.
    assert post.comment_sync_cursor == "cursor2"


@pytest.mark.asyncio
async def test_sync_comments_unlimited_by_default(monkeypatch):
    """max_comments=0 (the default) must never engage the cap check --
    existing behavior for any caller that doesn't pass one explicitly."""
    post = Post(id=uuid4(), media_pk="pk1", permalink="https://instagram.com/p/x/", shortcode="x")

    client = MagicMock()
    client.get_media_comments = AsyncMock(return_value={})
    monkeypatch.setattr(
        "app.workers.comment_sync.InstagramParser.parse_comments",
        MagicMock(return_value=([_comment(comment_id="c1")], "", False)),
    )
    monkeypatch.setattr("app.workers.comment_sync.previous_child_counts", AsyncMock(return_value={}))
    monkeypatch.setattr("app.workers.comment_sync.upsert_comments_bulk", AsyncMock())

    session = _session(stored_count=999_999)  # would be "at cap" under almost any real limit

    total = await sync_comments_for_post(session, client, post, creator_handle="myntra")

    client.get_media_comments.assert_awaited_once()
    assert total == 1


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

    session = _session()

    total = await sync_replies(session, client, post, parent, creator_handle="myntra")

    assert total == 2
    assert client.get_comment_replies.call_count == 2
    # Completed naturally (has_more=False on page 2) -- attempts a
    # tombstone pass for this parent's reply thread.
    session.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_sync_replies_skips_tombstone_when_truncated(monkeypatch):
    """A thread with more replies than MAX_REPLY_PAGES can cover has only
    seen a partial slice -- must not tombstone replies it never reached."""
    post = Post(id=uuid4(), media_pk="pk1", permalink="https://instagram.com/p/x/", shortcode="x")
    parent = _comment(comment_id="parent1", child_comment_count=100)

    client = MagicMock()
    client.get_comment_replies = AsyncMock(return_value={"edges": []})

    monkeypatch.setattr("app.workers.comment_sync.MAX_REPLY_PAGES", 2)
    monkeypatch.setattr(
        "app.workers.comment_sync.InstagramParser.parse_replies",
        MagicMock(side_effect=[
            ([_comment(comment_id="r1")], "cursor2", True),
            ([_comment(comment_id="r2")], "cursor3", True),  # still has_more=True when the cap hits
        ]),
    )
    monkeypatch.setattr("app.workers.comment_sync.upsert_comments_bulk", AsyncMock())

    session = _session()

    await sync_replies(session, client, post, parent, creator_handle="myntra")

    session.execute.assert_not_awaited()
