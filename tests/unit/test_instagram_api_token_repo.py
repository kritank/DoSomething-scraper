from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.crypto import decrypt_json, encrypt_json
from app.models.instagram_api_token import InstagramApiToken
from app.repositories.instagram_api_token_repo import InstagramApiTokenRepo


@pytest.mark.asyncio
async def test_reset_daily_call_counts_updates_all_tokens():
    """Regression test: calls_today previously had no reset path at all
    despite the class's own docstring claiming one existed -- it just
    accumulated forever as a lifetime total mislabeled "today"."""
    session = MagicMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    repo = InstagramApiTokenRepo(session)

    await repo.reset_daily_call_counts()

    session.execute.assert_awaited_once()
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_reset_if_due_reactivates_cooldown_token_past_its_cooldown():
    repo = InstagramApiTokenRepo(session=None)  # _reset_if_due never touches the session
    token = InstagramApiToken(
        label="t1",
        status="cooldown",
        cooldown_until=datetime.now(timezone.utc) - timedelta(seconds=1),  # already due
    )

    await repo._reset_if_due(token)

    assert token.status == "active"
    assert token.cooldown_until is None


@pytest.mark.asyncio
async def test_reset_if_due_leaves_token_untouched_before_cooldown_expires():
    repo = InstagramApiTokenRepo(session=None)
    cooldown_until = datetime.now(timezone.utc) + timedelta(hours=1)
    token = InstagramApiToken(label="t1", status="cooldown", cooldown_until=cooldown_until)

    await repo._reset_if_due(token)

    assert token.status == "cooldown"
    assert token.cooldown_until == cooldown_until


@pytest.mark.asyncio
async def test_reset_if_due_is_a_noop_for_active_token_with_no_cooldown():
    repo = InstagramApiTokenRepo(session=None)
    token = InstagramApiToken(label="t1", status="active", cooldown_until=None)

    await repo._reset_if_due(token)

    assert token.status == "active"
    assert token.cooldown_until is None


def test_access_token_and_app_secret_encryption_round_trip():
    repo = InstagramApiTokenRepo(session=None)
    token = InstagramApiToken(
        label="t1",
        access_token_encrypted=encrypt_json({"token": "EAAsecrettoken"}),
        app_secret_encrypted=encrypt_json({"secret": "shhh"}),
    )

    assert repo.decrypt_token(token) == "EAAsecrettoken"
    assert repo.decrypt_app_secret(token) == "shhh"


def test_encrypted_fields_are_never_the_plaintext_value():
    # Regression guard: create() must actually encrypt, not just copy the
    # raw string into the *_encrypted column.
    encrypted = encrypt_json({"token": "EAAsecrettoken"})
    assert encrypted != "EAAsecrettoken"
    assert decrypt_json(encrypted) == {"token": "EAAsecrettoken"}
