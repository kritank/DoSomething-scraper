from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.scraper.login_automator import LoginResult
from app.workers.account_login_processor import process_pending_logins


def _fake_account(username="testuser"):
    return SimpleNamespace(
        username=username,
        user_agent="ua",
        locale="en_US",
        timezone="UTC",
    )


async def _run_one_cycle(monkeypatch, pending_accounts, login_result_or_exc):
    """Runs process_pending_logins for exactly one poll iteration by making
    the sleep raise to break the while loop after one pass."""
    repo_instance = MagicMock()
    repo_instance.get_pending_logins = AsyncMock(return_value=pending_accounts)
    repo_instance.decrypt_password = MagicMock(return_value="pw")
    repo_instance.create = AsyncMock()
    repo_instance.create_checkpoint_required = AsyncMock()
    repo_instance.mark_login_failed = AsyncMock()

    if isinstance(login_result_or_exc, Exception):
        perform_login_mock = AsyncMock(side_effect=login_result_or_exc)
    else:
        perform_login_mock = AsyncMock(return_value=login_result_or_exc)

    class _StopLoop(Exception):
        pass

    async def _sleep_and_stop(*_args, **_kwargs):
        raise _StopLoop()

    shutdown_event = MagicMock()
    shutdown_event.is_set.return_value = False

    with (
        patch("app.workers.account_login_processor.InstagramAccountRepo", return_value=repo_instance),
        patch("app.workers.account_login_processor.perform_login", perform_login_mock),
        patch("app.workers.account_login_processor.get_session") as mock_get_session,
        patch("app.workers.account_login_processor.asyncio.sleep", _sleep_and_stop),
    ):
        mock_get_session.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
        mock_get_session.return_value.__aexit__ = AsyncMock(return_value=False)
        with pytest.raises(_StopLoop):
            await process_pending_logins(shutdown_event)

    return repo_instance


@pytest.mark.asyncio
async def test_success_calls_create(monkeypatch):
    account = _fake_account()
    result = LoginResult(status="success", cookies=[{"name": "sessionid", "value": "abc"}])
    repo = await _run_one_cycle(monkeypatch, [account], result)
    repo.create.assert_awaited_once()
    repo.create_checkpoint_required.assert_not_called()
    repo.mark_login_failed.assert_not_called()


@pytest.mark.asyncio
async def test_checkpoint_calls_create_checkpoint_required(monkeypatch):
    account = _fake_account()
    result = LoginResult(status="checkpoint_required", detail="2FA required")
    repo = await _run_one_cycle(monkeypatch, [account], result)
    repo.create_checkpoint_required.assert_awaited_once()
    repo.create.assert_not_called()
    repo.mark_login_failed.assert_not_called()


@pytest.mark.asyncio
async def test_bad_credentials_marks_failed(monkeypatch):
    account = _fake_account()
    result = LoginResult(status="bad_credentials", detail="wrong password")
    repo = await _run_one_cycle(monkeypatch, [account], result)
    repo.mark_login_failed.assert_awaited_once()
    repo.create.assert_not_called()
    repo.create_checkpoint_required.assert_not_called()


@pytest.mark.asyncio
async def test_unknown_failure_marks_failed(monkeypatch):
    account = _fake_account()
    result = LoginResult(status="unknown_failure", detail="still on login page")
    repo = await _run_one_cycle(monkeypatch, [account], result)
    repo.mark_login_failed.assert_awaited_once()


@pytest.mark.asyncio
async def test_exception_from_perform_login_marks_failed(monkeypatch):
    account = _fake_account()
    repo = await _run_one_cycle(monkeypatch, [account], RuntimeError("browser crashed"))
    repo.mark_login_failed.assert_awaited_once()
