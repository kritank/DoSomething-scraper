from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from datetime import date

from app.core.exceptions import DuplicateInfluencerError
from app.models.influencer import Influencer
from app.repositories.influencer_repo import InfluencerRepo
from app.schemas.influencer import InfluencerDetailsUpdate, InfluencerScrapeSettingsUpdate


def _repo_with_influencer(influencer: Influencer) -> tuple[InfluencerRepo, MagicMock]:
    session = MagicMock()
    session.get = AsyncMock(return_value=influencer)
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.execute = AsyncMock()
    return InfluencerRepo(session), session


@pytest.mark.asyncio
async def test_update_details_applies_both_provided_fields():
    influencer = Influencer(id=uuid4(), handle="old_handle", category_id=uuid4())
    repo, session = _repo_with_influencer(influencer)
    new_category_id = uuid4()

    result = await repo.update_details(
        influencer.id,
        InfluencerDetailsUpdate(handle="new_handle", category_id=new_category_id),
    )

    assert result.handle == "new_handle"
    assert result.category_id == new_category_id
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_details_handle_change_backfills_is_from_creator():
    """Regression test: a handle rename must recompute is_from_creator for
    every existing comment against the NEW handle -- otherwise the
    creator's own past replies stay permanently mislabeled for any post
    outside the rolling comment-sync window, which a rename does nothing
    to re-trigger."""
    influencer = Influencer(id=uuid4(), handle="old_handle", category_id=uuid4())
    repo, session = _repo_with_influencer(influencer)

    await repo.update_details(influencer.id, InfluencerDetailsUpdate(handle="new_handle"))

    session.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_details_same_handle_case_change_only_skips_backfill():
    """The old/new comparison is case-insensitive -- correcting only
    casing (or resubmitting the same handle) isn't a real rename and
    shouldn't pay for a bulk UPDATE across every comment."""
    influencer = Influencer(id=uuid4(), handle="myntraofficial", category_id=uuid4())
    repo, session = _repo_with_influencer(influencer)

    await repo.update_details(influencer.id, InfluencerDetailsUpdate(handle="MyntraOfficial"))

    session.execute.assert_not_called()


@pytest.mark.asyncio
async def test_update_details_no_handle_change_skips_backfill():
    influencer = Influencer(id=uuid4(), handle="stays_the_same", category_id=uuid4())
    repo, session = _repo_with_influencer(influencer)

    await repo.update_details(influencer.id, InfluencerDetailsUpdate(category_id=uuid4()))

    session.execute.assert_not_called()


@pytest.mark.asyncio
async def test_update_details_leaves_unset_field_unchanged():
    """Partial update semantics -- omitting a field must not clobber it,
    same convention as CategoryRepo.update."""
    influencer = Influencer(id=uuid4(), handle="stays_the_same", category_id=uuid4())
    repo, _ = _repo_with_influencer(influencer)

    result = await repo.update_details(
        influencer.id, InfluencerDetailsUpdate(category_id=uuid4())
    )

    assert result.handle == "stays_the_same"


@pytest.mark.asyncio
async def test_update_details_duplicate_handle_raises_friendly_error():
    influencer = Influencer(id=uuid4(), handle="existing", category_id=uuid4())
    repo, session = _repo_with_influencer(influencer)
    session.commit = AsyncMock(side_effect=IntegrityError("stmt", {}, Exception("dup")))

    with pytest.raises(DuplicateInfluencerError):
        await repo.update_details(influencer.id, InfluencerDetailsUpdate(handle="taken"))

    session.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_scrape_settings_applies_both_when_both_provided():
    influencer = Influencer(id=uuid4(), handle="x", category_id=uuid4())
    repo, _ = _repo_with_influencer(influencer)

    result = await repo.update_scrape_settings(
        influencer.id,
        InfluencerScrapeSettingsUpdate(scrape_posts_since=date(2026, 1, 1), max_comments_per_post=2000),
    )

    assert result.scrape_posts_since == date(2026, 1, 1)
    assert result.max_comments_per_post == 2000


@pytest.mark.asyncio
async def test_update_scrape_settings_partial_update_leaves_other_field_untouched():
    """Regression test: both fields default to None on the schema, so an
    unconditional overwrite of both would silently wipe whichever one the
    caller didn't intend to touch -- a request setting only
    max_comments_per_post must not reset scrape_posts_since back to null,
    and vice versa."""
    influencer = Influencer(
        id=uuid4(), handle="x", category_id=uuid4(),
        scrape_posts_since=date(2026, 1, 1), max_comments_per_post=2000,
    )
    repo, _ = _repo_with_influencer(influencer)

    result = await repo.update_scrape_settings(
        influencer.id, InfluencerScrapeSettingsUpdate(max_comments_per_post=500)
    )

    assert result.max_comments_per_post == 500
    assert result.scrape_posts_since == date(2026, 1, 1)  # untouched


@pytest.mark.asyncio
async def test_update_scrape_settings_explicit_null_clears_field():
    """Distinguishing "omitted" from "explicitly sent as null" -- a
    caller that DOES send max_comments_per_post=None is intentionally
    clearing the override back to "use the platform default"."""
    influencer = Influencer(
        id=uuid4(), handle="x", category_id=uuid4(), max_comments_per_post=2000,
    )
    repo, _ = _repo_with_influencer(influencer)

    result = await repo.update_scrape_settings(
        influencer.id, InfluencerScrapeSettingsUpdate(max_comments_per_post=None)
    )

    assert result.max_comments_per_post is None


@pytest.mark.asyncio
async def test_get_public_accounts_empty_ids_skips_query():
    """No influencer_ids (e.g. a Creator with no linked accounts) should
    short-circuit rather than issue a `WHERE id IN ()` query."""
    session = MagicMock()
    session.execute = AsyncMock()
    repo = InfluencerRepo(session)

    result = await repo.get_public_accounts([])

    assert result == []
    session.execute.assert_not_awaited()


def test_get_top_ranked_platform_filter_applied_to_query():
    """Regression guard for the /influencers/top platform query param --
    the compiled statement must gain a `WHERE ... platform = :platform`
    predicate when one is given, and must not when omitted."""
    session = MagicMock()
    repo = InfluencerRepo(session)

    stmt, _ = repo._leaderboard_base_stmt()
    filtered_stmt = stmt.where(Influencer.platform == "youtube")
    unfiltered_where = str(stmt.whereclause).lower()
    filtered_where = str(filtered_stmt.whereclause).lower()

    assert "platform" not in unfiltered_where
    assert "platform" in filtered_where


def _fake_leaderboard_row(**overrides):
    """Stand-in for the Row objects _leaderboard_base_stmt's query returns
    -- get_top_ranked only ever accesses these via attribute access, so a
    plain namespace is enough without a real DB round-trip."""
    defaults = dict(
        id=uuid4(),
        handle="handle",
        platform="instagram",
        creator_id=None,
        category_name="Category",
        followers=100,
        following=10,
        posts=5,
        is_verified=False,
        last_updated=date(2026, 1, 1),
        avg_engagement=None,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


@pytest.mark.asyncio
async def test_get_top_ranked_merges_multi_platform_creator_into_one_row():
    """Two Influencer rows sharing a creator_id (one per platform) must
    collapse into a single leaderboard entry with summed followers/posts
    and the combined engagement rate averaged across accounts -- otherwise
    a cross-platform creator would occupy two leaderboard slots instead of
    ranking as one."""
    creator_id = uuid4()
    ig_id, yt_id = uuid4(), uuid4()
    ig_row = _fake_leaderboard_row(
        id=ig_id, creator_id=creator_id, platform="instagram", handle="ashishchanchlani",
        followers=17_800_000, posts=1800, avg_engagement=546_460, is_verified=True,
    )
    yt_row = _fake_leaderboard_row(
        id=yt_id, creator_id=creator_id, platform="youtube", handle="@geekyranjit",
        followers=3_300_000, posts=3400, avg_engagement=1320,
    )
    solo_row = _fake_leaderboard_row(followers=50, handle="solo")

    session = MagicMock()
    session.execute = AsyncMock(return_value=MagicMock(all=lambda: [ig_row, yt_row, solo_row]))
    repo = InfluencerRepo(session)

    entries = await repo.get_top_ranked(limit=10)

    assert len(entries) == 2
    merged = next(e for e in entries if e.link_id == creator_id)
    assert merged.id == ig_id  # representative = highest-follower account
    assert merged.platforms == ["instagram", "youtube"]
    assert merged.followers == 17_800_000 + 3_300_000
    assert merged.posts == 1800 + 3400
    assert merged.is_verified is True
    assert merged.engagement_rate == round((3.07 + 0.04) / 2, 2)

    solo = next(e for e in entries if e.link_id == solo_row.id)
    assert solo.platforms == ["instagram"]
    assert solo.followers == 50


@pytest.mark.asyncio
async def test_get_top_ranked_sort_by_posts_and_engagement():
    """`sort` re-ranks by posts/engagement instead of followers, and
    entries missing the sorted field (e.g. no engagement history) sort
    last rather than floating to the top as a false zero."""
    most_followers = _fake_leaderboard_row(followers=1000, posts=10, avg_engagement=None, handle="a")
    most_posts = _fake_leaderboard_row(followers=10, posts=1000, avg_engagement=None, handle="b")
    most_engagement = _fake_leaderboard_row(followers=10, posts=10, avg_engagement=500, handle="c")  # 5% rate
    no_engagement_history = _fake_leaderboard_row(followers=5, posts=5, avg_engagement=None, handle="d")

    session = MagicMock()
    rows = [most_followers, most_posts, most_engagement, no_engagement_history]
    session.execute = AsyncMock(return_value=MagicMock(all=lambda: rows))
    repo = InfluencerRepo(session)

    by_posts = await repo.get_top_ranked(limit=10, sort="posts")
    assert [e.handle for e in by_posts][:2] == ["b", "a"]

    by_engagement = await repo.get_top_ranked(limit=10, sort="engagement")
    assert by_engagement[0].handle == "c"
    assert by_engagement[-1].handle in ("a", "b", "d")  # None-engagement rows sort last
    assert by_engagement[-1].engagement_rate is None
