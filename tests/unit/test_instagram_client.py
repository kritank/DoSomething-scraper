from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.core.config import settings
from app.core.exceptions import ScraperBlockedError, ScraperRateLimitError
from app.scraper.client import InstagramClient


def _make_client() -> InstagramClient:
    return InstagramClient(cookies={"sessionid": "sid"}, user_agent="test-agent")


class _FakeResponse:
    """Minimal stand-in for a curl_cffi response -- only the attributes
    _get() actually touches."""

    def __init__(self, status_code: int, *, json_data=None, headers=None):
        self.status_code = status_code
        self._json = json_data
        self.headers = headers or {}

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


async def _noop(*_args, **_kwargs):
    return None


@pytest.mark.asyncio
async def test_retries_after_429_then_succeeds(monkeypatch):
    monkeypatch.setattr("app.scraper.client.asyncio.sleep", _noop)

    client = _make_client()
    mock_get = AsyncMock(
        side_effect=[
            _FakeResponse(429, headers={"Retry-After": "1"}),
            _FakeResponse(200, json_data={"ok": True}),
        ]
    )
    monkeypatch.setattr(client._curl, "get", mock_get)

    result = await client._get("https://i.instagram.com/api/v1/some_endpoint")

    assert result == {"ok": True}
    assert mock_get.call_count == 2
    await client.close()


@pytest.mark.asyncio
async def test_exhausts_retries_and_raises_rate_limit_error(monkeypatch):
    monkeypatch.setattr("app.scraper.client.asyncio.sleep", _noop)
    monkeypatch.setattr(settings, "SCRAPER_MAX_RETRIES", 1)

    client = _make_client()
    monkeypatch.setattr(
        client._curl,
        "get",
        AsyncMock(return_value=_FakeResponse(429, headers={"Retry-After": "1"})),
    )

    with pytest.raises(ScraperRateLimitError):
        await client._get("https://i.instagram.com/api/v1/some_endpoint", handle="testuser")
    await client.close()


@pytest.mark.asyncio
async def test_401_raises_blocked_error_without_retry(monkeypatch):
    client = _make_client()
    mock_get = AsyncMock(return_value=_FakeResponse(401))
    monkeypatch.setattr(client._curl, "get", mock_get)

    with pytest.raises(ScraperBlockedError):
        await client._get("https://i.instagram.com/api/v1/some_endpoint", handle="testuser")

    assert mock_get.call_count == 1  # never retried in-loop
    await client.close()
