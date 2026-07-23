from __future__ import annotations

import json
from unittest.mock import AsyncMock

import httpx
import pytest

from app.core.exceptions import YouTubeChannelPageError
from app.scraper.youtube_page_scraper import fetch_is_verified


def _page_html(inner_data: dict) -> str:
    return f"<html><script>var ytInitialData = {json.dumps(inner_data)};</script></html>"


def _header(label: str | None) -> dict:
    title = {"dynamicTextViewModel": {"text": {"content": "Some Channel"}}}
    if label is not None:
        title["dynamicTextViewModel"]["rendererContext"] = {"accessibilityContext": {"label": label}}
    return {"header": {"pageHeaderRenderer": {"content": {"pageHeaderViewModel": {"title": title}}}}}


@pytest.mark.asyncio
async def test_fetch_is_verified_true_for_verified_channel(monkeypatch):
    html = _page_html(_header("Marques Brownlee, Verified"))
    mock_get = AsyncMock(return_value=httpx.Response(200, text=html))
    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    assert await fetch_is_verified(handle="mkbhd") is True


@pytest.mark.asyncio
async def test_fetch_is_verified_false_when_no_accessibility_context(monkeypatch):
    # Confirmed live behavior: unverified channels have no
    # accessibilityContext key at all under the title, not a label lacking
    # ", Verified".
    html = _page_html(_header(None))
    mock_get = AsyncMock(return_value=httpx.Response(200, text=html))
    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    assert await fetch_is_verified(handle="some_small_channel") is False


@pytest.mark.asyncio
async def test_fetch_is_verified_prefers_channel_id_url(monkeypatch):
    html = _page_html(_header("Some Channel, Verified"))
    mock_get = AsyncMock(return_value=httpx.Response(200, text=html))
    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    assert await fetch_is_verified(channel_id="UCabc123") is True
    called_url = mock_get.call_args.args[0]
    assert called_url == "https://www.youtube.com/channel/UCabc123"


@pytest.mark.asyncio
async def test_fetch_is_verified_raises_on_non_200(monkeypatch):
    mock_get = AsyncMock(return_value=httpx.Response(404, text="not found"))
    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    with pytest.raises(YouTubeChannelPageError):
        await fetch_is_verified(handle="doesnotexist")


@pytest.mark.asyncio
async def test_fetch_is_verified_raises_when_ytinitialdata_missing(monkeypatch):
    mock_get = AsyncMock(return_value=httpx.Response(200, text="<html>nothing here</html>"))
    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    with pytest.raises(YouTubeChannelPageError):
        await fetch_is_verified(handle="mkbhd")


@pytest.mark.asyncio
async def test_fetch_is_verified_raises_on_unexpected_shape(monkeypatch):
    html = _page_html({"header": {"somethingElse": {}}})
    mock_get = AsyncMock(return_value=httpx.Response(200, text=html))
    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    with pytest.raises(YouTubeChannelPageError):
        await fetch_is_verified(handle="mkbhd")


@pytest.mark.asyncio
async def test_fetch_is_verified_raises_on_request_error(monkeypatch):
    mock_get = AsyncMock(side_effect=httpx.ConnectError("boom"))
    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    with pytest.raises(YouTubeChannelPageError):
        await fetch_is_verified(handle="mkbhd")
