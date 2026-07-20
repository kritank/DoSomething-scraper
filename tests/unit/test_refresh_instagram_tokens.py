from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import httpx
import pytest

from app.scheduler.runner import refresh_instagram_tokens


def _token(auth_flavor, token_expires_at, label="t1"):
    return SimpleNamespace(id=uuid4(), label=label, auth_flavor=auth_flavor, token_expires_at=token_expires_at)


def _run(tokens, http_response=None, http_side_effect=None):
    repo_instance = MagicMock()
    repo_instance.get_all = AsyncMock(return_value=tokens)
    repo_instance.decrypt_token = MagicMock(return_value="raw-token")
    repo_instance.update_token = AsyncMock()

    mock_http = AsyncMock()
    if http_side_effect is not None:
        mock_http.get = AsyncMock(side_effect=http_side_effect)
    else:
        mock_http.get = AsyncMock(return_value=http_response)
    mock_client_cm = MagicMock()
    mock_client_cm.__aenter__ = AsyncMock(return_value=mock_http)
    mock_client_cm.__aexit__ = AsyncMock(return_value=False)

    async def _fn():
        with (
            patch("app.scheduler.runner.get_session") as mock_get_session,
            patch("app.scheduler.runner.InstagramApiTokenRepo", return_value=repo_instance),
            patch("app.scheduler.runner.httpx.AsyncClient", return_value=mock_client_cm),
        ):
            mock_get_session.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
            mock_get_session.return_value.__aexit__ = AsyncMock(return_value=False)
            await refresh_instagram_tokens()
        return repo_instance, mock_http

    return _fn()


@pytest.mark.asyncio
async def test_facebook_login_tokens_are_never_refreshed():
    # facebook_login Page tokens don't expire (token_expires_at is None) --
    # nothing to refresh, and the HTTP client must never even be touched.
    token = _token("facebook_login", None)
    repo_instance, mock_http = await _run([token])
    mock_http.get.assert_not_called()
    repo_instance.update_token.assert_not_called()


@pytest.mark.asyncio
async def test_instagram_login_token_outside_refresh_window_is_skipped():
    token = _token("instagram_login", datetime.now(timezone.utc) + timedelta(days=30))
    repo_instance, mock_http = await _run([token])
    mock_http.get.assert_not_called()
    repo_instance.update_token.assert_not_called()


@pytest.mark.asyncio
async def test_instagram_login_token_due_for_refresh_gets_refreshed():
    token = _token("instagram_login", datetime.now(timezone.utc) + timedelta(days=5))
    response = httpx.Response(
        200,
        json={"access_token": "new-token", "expires_in": 5184000},
        request=httpx.Request("GET", "https://graph.instagram.com/refresh_access_token"),
    )
    repo_instance, mock_http = await _run([token], http_response=response)

    mock_http.get.assert_awaited_once()
    repo_instance.update_token.assert_awaited_once()
    call_args = repo_instance.update_token.call_args
    assert call_args.args[0] == token.id
    assert call_args.args[1] == "new-token"


@pytest.mark.asyncio
async def test_failed_refresh_does_not_raise_and_does_not_update():
    token = _token("instagram_login", datetime.now(timezone.utc) + timedelta(days=5))
    repo_instance, mock_http = await _run([token], http_side_effect=httpx.ConnectError("boom"))
    repo_instance.update_token.assert_not_called()
