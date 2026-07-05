from __future__ import annotations

import httpx
import pytest
import respx

from app.core.config import settings
from app.core.exceptions import ScraperBlockedError, ScraperRateLimitError
from app.scraper.client import InstagramClient


def _make_client() -> InstagramClient:
    return InstagramClient(cookies={"sessionid": "sid"}, user_agent="test-agent")


@pytest.mark.asyncio
@respx.mock
async def test_retries_after_429_then_succeeds(monkeypatch):
    monkeypatch.setattr("app.scraper.client.asyncio.sleep", lambda *_: _noop())

    route = respx.get("https://i.instagram.com/api/v1/some_endpoint").mock(
        side_effect=[
            httpx.Response(429, headers={"Retry-After": "1"}),
            httpx.Response(200, json={"ok": True}),
        ]
    )

    client = _make_client()
    result = await client._get("https://i.instagram.com/api/v1/some_endpoint")

    assert result == {"ok": True}
    assert route.call_count == 2
    await client.close()


@pytest.mark.asyncio
@respx.mock
async def test_exhausts_retries_and_raises_rate_limit_error(monkeypatch):
    monkeypatch.setattr("app.scraper.client.asyncio.sleep", lambda *_: _noop())
    monkeypatch.setattr(settings, "SCRAPER_MAX_RETRIES", 1)

    respx.get("https://i.instagram.com/api/v1/some_endpoint").mock(
        return_value=httpx.Response(429, headers={"Retry-After": "1"})
    )

    client = _make_client()
    with pytest.raises(ScraperRateLimitError):
        await client._get("https://i.instagram.com/api/v1/some_endpoint", handle="testuser")
    await client.close()


@pytest.mark.asyncio
@respx.mock
async def test_401_raises_blocked_error_without_retry():
    route = respx.get("https://i.instagram.com/api/v1/some_endpoint").mock(
        return_value=httpx.Response(401)
    )

    client = _make_client()
    with pytest.raises(ScraperBlockedError):
        await client._get("https://i.instagram.com/api/v1/some_endpoint", handle="testuser")

    assert route.call_count == 1  # never retried in-loop
    await client.close()


async def _noop(*_args, **_kwargs):
    return None
