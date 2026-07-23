from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.core.config import settings
from app.repositories.instagram_account_repo import InstagramAccountRepo


def _account(**overrides) -> SimpleNamespace:
    defaults = dict(
        id=uuid4(), username="test_account", status="active", failure_count=0,
        last_failure_at=None, last_success_at=None, error_message=None,
        cooldown_until=None, locked_by="worker:1", lease_expires_at="not-none",
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _repo_with_account(account) -> InstagramAccountRepo:
    session = MagicMock()
    session.get = AsyncMock(return_value=account)
    session.commit = AsyncMock()
    return InstagramAccountRepo(session)


@pytest.mark.asyncio
async def test_repeated_rate_limited_outcomes_never_auto_disable():
    """Regression confirmed live in production: a real, sustained Instagram
    throttle (not a code bug -- the account's session is perfectly valid)
    kept an account at status="active" while failure_count climbed across
    separate job attempts, crossing ACCOUNT_MAX_CONSECUTIVE_FAILURES within
    a couple hours and landing in "disabled" -- a state nothing auto-
    recovers from, unlike checkpoint_required. rate_limited must never
    escalate to disabled, no matter how many times it repeats."""
    account = _account(failure_count=settings.ACCOUNT_MAX_CONSECUTIVE_FAILURES - 1)
    repo = _repo_with_account(account)

    await repo.release(account.id, "rate_limited", retry_after=30)

    assert account.status == "active"
    assert account.failure_count == settings.ACCOUNT_MAX_CONSECUTIVE_FAILURES
    assert account.cooldown_until is not None


@pytest.mark.asyncio
async def test_generic_error_outcome_still_disables_at_threshold():
    """A genuine "error" outcome (not rate-limiting) is real evidence
    something's wrong with the account/environment -- this escalation
    path must still work."""
    account = _account(failure_count=settings.ACCOUNT_MAX_CONSECUTIVE_FAILURES - 1)
    repo = _repo_with_account(account)

    await repo.release(account.id, "error")

    assert account.status == "disabled"


@pytest.mark.asyncio
async def test_blocked_outcome_goes_to_checkpoint_required_not_disabled():
    account = _account(failure_count=settings.ACCOUNT_MAX_CONSECUTIVE_FAILURES - 1)
    repo = _repo_with_account(account)

    await repo.release(account.id, "blocked")

    assert account.status == "checkpoint_required"


@pytest.mark.asyncio
async def test_success_outcome_resets_failure_count_and_reactivates():
    account = _account(status="checkpoint_required", failure_count=4, error_message="stale")
    repo = _repo_with_account(account)

    await repo.release(account.id, "success")

    assert account.status == "active"
    assert account.failure_count == 0
    assert account.error_message is None
    assert account.last_success_at is not None
