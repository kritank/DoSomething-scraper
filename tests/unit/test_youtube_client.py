from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest

from app.core.config import settings
from app.core.exceptions import NoUsableYouTubeKeyError, ScraperRateLimitError, YouTubeResourceGoneError
from app.scraper.youtube_client import YouTubeClient


def _key_pair():
    return uuid4(), "test-api-key"


def _make_client(key_provider=None, usage_recorder=None, key_exhauster=None, key_invalidator=None):
    key_id, api_key = _key_pair()

    async def _default_provider():
        return key_id, api_key

    async def _noop(*_args, **_kwargs):
        return None

    client = YouTubeClient(
        key_provider=key_provider or _default_provider,
        usage_recorder=usage_recorder or _noop,
        key_exhauster=key_exhauster or _noop,
        key_invalidator=key_invalidator or _noop,
    )
    return client, key_id


async def _noop_sleep(*_args, **_kwargs):
    return None


@pytest.mark.asyncio
async def test_successful_request_records_usage(monkeypatch):
    usage_calls = []

    async def usage_recorder(key_id, units):
        usage_calls.append((key_id, units))

    client, key_id = _make_client(usage_recorder=usage_recorder)
    mock_get = AsyncMock(return_value=httpx.Response(200, json={"items": [{"id": "x"}]}))
    monkeypatch.setattr(client._http, "get", mock_get)

    result = await client.get_channel(handle="mkbhd")

    assert result == {"items": [{"id": "x"}]}
    assert usage_calls == [(key_id, 1)]
    await client.close()


@pytest.mark.asyncio
async def test_retries_after_429_then_succeeds(monkeypatch):
    monkeypatch.setattr("app.scraper.youtube_client.asyncio.sleep", _noop_sleep)
    client, _ = _make_client()
    mock_get = AsyncMock(
        side_effect=[
            httpx.Response(429),
            httpx.Response(200, json={"items": []}),
        ]
    )
    monkeypatch.setattr(client._http, "get", mock_get)

    result = await client.get_channel(handle="x")

    assert result == {"items": []}
    assert mock_get.call_count == 2
    await client.close()


@pytest.mark.asyncio
async def test_quota_exceeded_rotates_to_next_key(monkeypatch):
    key1, key2 = uuid4(), uuid4()
    keys = iter([(key1, "key1"), (key2, "key2")])
    exhausted = []

    async def key_provider():
        return next(keys)

    async def key_exhauster(key_id):
        exhausted.append(key_id)

    client, _ = _make_client(key_provider=key_provider, key_exhauster=key_exhauster)

    calls = []

    async def fake_get(url, params=None, **kwargs):
        calls.append(params.get("key"))
        if params.get("key") == "key1":
            return httpx.Response(
                403, json={"error": {"errors": [{"reason": "quotaExceeded"}], "message": "quota"}}
            )
        return httpx.Response(200, json={"items": [{"id": "ok"}]})

    monkeypatch.setattr(client._http, "get", fake_get)

    result = await client.get_channel(handle="x")

    assert result == {"items": [{"id": "ok"}]}
    assert exhausted == [key1]
    assert calls == ["key1", "key2"]
    await client.close()


@pytest.mark.asyncio
async def test_invalid_key_rotates_and_marks_invalid(monkeypatch):
    key1, key2 = uuid4(), uuid4()
    keys = iter([(key1, "key1"), (key2, "key2")])
    invalidated = []

    async def key_provider():
        return next(keys)

    async def key_invalidator(key_id, detail):
        invalidated.append((key_id, detail))

    client, _ = _make_client(key_provider=key_provider, key_invalidator=key_invalidator)

    async def fake_get(url, params=None, **kwargs):
        if params.get("key") == "key1":
            return httpx.Response(
                400, json={"error": {"errors": [{"reason": "keyInvalid"}], "message": "API key not valid"}}
            )
        return httpx.Response(200, json={"items": []})

    monkeypatch.setattr(client._http, "get", fake_get)

    result = await client.get_channel(handle="x")

    assert result == {"items": []}
    assert invalidated == [(key1, "API key not valid")]
    await client.close()


@pytest.mark.asyncio
async def test_no_usable_key_raises_rate_limit_with_retry_after():
    async def key_provider():
        raise NoUsableYouTubeKeyError()

    client, _ = _make_client(key_provider=key_provider)

    with pytest.raises(ScraperRateLimitError) as exc_info:
        await client.get_channel(handle="x")

    assert exc_info.value.context.get("retry_after") > 0
    await client.close()


@pytest.mark.asyncio
async def test_comments_disabled_raises_resource_gone(monkeypatch):
    client, _ = _make_client()
    mock_get = AsyncMock(
        return_value=httpx.Response(
            403, json={"error": {"errors": [{"reason": "commentsDisabled"}], "message": "disabled"}}
        )
    )
    monkeypatch.setattr(client._http, "get", mock_get)

    with pytest.raises(YouTubeResourceGoneError) as exc_info:
        await client.get_comment_threads("vid1")

    assert exc_info.value.context["reason"] == "commentsDisabled"
    assert mock_get.call_count == 1  # not retried -- not recoverable
    await client.close()


@pytest.mark.asyncio
async def test_invalid_page_token_raises_resource_gone(monkeypatch):
    client, _ = _make_client()
    mock_get = AsyncMock(
        return_value=httpx.Response(
            400, json={"error": {"errors": [{"reason": "invalidPageToken"}], "message": "bad token"}}
        )
    )
    monkeypatch.setattr(client._http, "get", mock_get)

    with pytest.raises(YouTubeResourceGoneError) as exc_info:
        await client.get_uploads_page("UU123", page_token="stale")

    assert exc_info.value.context["reason"] == "invalidPageToken"
    await client.close()


@pytest.mark.asyncio
async def test_network_error_retries_then_raises_timeout(monkeypatch):
    monkeypatch.setattr("app.scraper.youtube_client.asyncio.sleep", _noop_sleep)
    monkeypatch.setattr(settings, "SCRAPER_MAX_RETRIES", 1)

    client, _ = _make_client()
    mock_get = AsyncMock(side_effect=httpx.ConnectError("boom"))
    monkeypatch.setattr(client._http, "get", mock_get)

    from app.core.exceptions import ScraperTimeoutError

    with pytest.raises(ScraperTimeoutError):
        await client.get_channel(handle="x")

    assert mock_get.call_count == 2  # initial + 1 retry
    await client.close()


@pytest.mark.asyncio
async def test_get_videos_batches_ids_into_one_request(monkeypatch):
    client, _ = _make_client()
    mock_get = AsyncMock(return_value=httpx.Response(200, json={"items": []}))
    monkeypatch.setattr(client._http, "get", mock_get)

    await client.get_videos([f"v{i}" for i in range(50)])

    assert mock_get.call_count == 1
    called_params = mock_get.call_args.kwargs["params"]
    assert called_params["id"].count(",") == 49
    await client.close()
