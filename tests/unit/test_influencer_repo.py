from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from app.core.exceptions import DuplicateInfluencerError
from app.models.influencer import Influencer
from app.repositories.influencer_repo import InfluencerRepo
from app.schemas.influencer import InfluencerDetailsUpdate


def _repo_with_influencer(influencer: Influencer) -> tuple[InfluencerRepo, MagicMock]:
    session = MagicMock()
    session.get = AsyncMock(return_value=influencer)
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
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
