from __future__ import annotations

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
