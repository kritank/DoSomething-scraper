from __future__ import annotations

import json
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest

from app.core.config import settings
from app.core.exceptions import (
    InfluencerHandleNotFoundError,
    InstagramAccountNotProfessionalError,
    NoUsableInstagramTokenError,
    ScraperRateLimitError,
)
from app.scraper.instagram_graph_client import InstagramGraphClient


def _token_triple():
    return uuid4(), "test-access-token", "17841400000000000"


def _make_client(token_provider=None, usage_recorder=None, token_exhauster=None, token_invalidator=None):
    token_id, access_token, ig_user_id = _token_triple()

    async def _default_provider():
        return token_id, access_token, ig_user_id

    async def _noop(*_args, **_kwargs):
        return None

    client = InstagramGraphClient(
        token_provider=token_provider or _default_provider,
        usage_recorder=usage_recorder or _noop,
        token_exhauster=token_exhauster or _noop,
        token_invalidator=token_invalidator or _noop,
    )
    # INSTAGRAM_GRAPH_RATE_PER_HOUR (150/hr) is real-time pacing meant for
    # production, not test speed -- tests exercise retry/rotation logic
    # firing many requests back-to-back, so the limiter itself is bypassed
    # here the same way asyncio.sleep is mocked for backoff.
    client._rate_limiter.acquire = AsyncMock(return_value=None)
    return client, token_id


async def _noop_sleep(*_args, **_kwargs):
    return None


def _usage_header(pct: float) -> dict:
    return {"x-app-usage": json.dumps({"call_count": pct, "total_cputime": 0, "total_time": 0})}


def _error_response(code: int, message: str = "err", subcode: int | None = None, status: int = 400) -> httpx.Response:
    body: dict = {"error": {"code": code, "message": message}}
    if subcode is not None:
        body["error"]["error_subcode"] = subcode
    return httpx.Response(status, json=body)


@pytest.mark.asyncio
async def test_successful_request_records_usage_and_returns_business_discovery(monkeypatch):
    usage_calls = []

    async def usage_recorder(token_id, calls, pct):
        usage_calls.append((token_id, calls, pct))

    client, token_id = _make_client(usage_recorder=usage_recorder)
    mock_get = AsyncMock(
        return_value=httpx.Response(
            200,
            json={"business_discovery": {"username": "myntra", "followers_count": 100}},
            headers=_usage_header(14),
        )
    )
    monkeypatch.setattr(client._http, "get", mock_get)

    result = await client.get_business_profile("myntra")

    assert result == {"username": "myntra", "followers_count": 100}
    assert usage_calls == [(token_id, 1, 14)]
    await client.close()


@pytest.mark.asyncio
async def test_retries_after_5xx_then_succeeds(monkeypatch):
    monkeypatch.setattr("app.scraper.instagram_graph_client.asyncio.sleep", _noop_sleep)
    client, _ = _make_client()
    mock_get = AsyncMock(
        side_effect=[
            httpx.Response(500),
            httpx.Response(200, json={"business_discovery": {"username": "x"}}),
        ]
    )
    monkeypatch.setattr(client._http, "get", mock_get)

    result = await client.get_business_profile("x")

    assert result == {"username": "x"}
    assert mock_get.call_count == 2
    await client.close()


@pytest.mark.asyncio
async def test_rate_limit_code_exhausts_and_rotates_to_next_token(monkeypatch):
    monkeypatch.setattr("app.scraper.instagram_graph_client.asyncio.sleep", _noop_sleep)
    token1, token2 = uuid4(), uuid4()
    triples = iter([(token1, "tok1", "ig1"), (token2, "tok2", "ig2")])
    exhausted = []

    async def token_provider():
        return next(triples)

    async def token_exhauster(token_id, until):
        exhausted.append(token_id)

    client, _ = _make_client(token_provider=token_provider, token_exhauster=token_exhauster)
    mock_get = AsyncMock(
        side_effect=[
            _error_response(code=4, message="rate limited"),  # token1: rate limited
            httpx.Response(200, json={"business_discovery": {"username": "x"}}),  # token2: succeeds
        ]
    )
    monkeypatch.setattr(client._http, "get", mock_get)

    result = await client.get_business_profile("x")

    assert result == {"username": "x"}
    assert exhausted == [token1]
    await client.close()


@pytest.mark.asyncio
async def test_invalid_token_code_190_invalidates_and_rotates(monkeypatch):
    token1, token2 = uuid4(), uuid4()
    triples = iter([(token1, "tok1", "ig1"), (token2, "tok2", "ig2")])
    invalidated = []

    async def token_provider():
        return next(triples)

    async def token_invalidator(token_id, detail):
        invalidated.append(token_id)

    client, _ = _make_client(token_provider=token_provider, token_invalidator=token_invalidator)
    mock_get = AsyncMock(
        side_effect=[
            _error_response(code=190, message="token expired"),
            httpx.Response(200, json={"business_discovery": {"username": "x"}}),
        ]
    )
    monkeypatch.setattr(client._http, "get", mock_get)

    result = await client.get_business_profile("x")

    assert result == {"username": "x"}
    assert invalidated == [token1]
    await client.close()


@pytest.mark.asyncio
async def test_no_usable_token_surfaces_as_rate_limit_error():
    async def token_provider():
        raise NoUsableInstagramTokenError()

    client, _ = _make_client(token_provider=token_provider)

    with pytest.raises(ScraperRateLimitError):
        await client.get_business_profile("x")
    await client.close()


@pytest.mark.asyncio
async def test_not_professional_account_raises_typed_error_without_rotation(monkeypatch):
    client, _ = _make_client()
    mock_get = AsyncMock(
        return_value=_error_response(code=100, message="not a professional account", subcode=2108006)
    )
    monkeypatch.setattr(client._http, "get", mock_get)

    with pytest.raises(InstagramAccountNotProfessionalError):
        await client.get_business_profile("personal_account")

    assert mock_get.call_count == 1  # not retried/rotated -- permanent, not transient
    await client.close()


@pytest.mark.asyncio
async def test_not_professional_account_detected_via_message_fallback(monkeypatch):
    # Real fixture for this exact error shape wasn't captured during setup
    # (every handle tried during Phase 0 turned out to already be a
    # professional account) -- this covers the message-based fallback path
    # for whichever subcode Meta actually returns.
    client, _ = _make_client()
    mock_get = AsyncMock(
        return_value=_error_response(code=100, message="This user is not a professional account.")
    )
    monkeypatch.setattr(client._http, "get", mock_get)

    with pytest.raises(InstagramAccountNotProfessionalError):
        await client.get_business_profile("personal_account")
    await client.close()


@pytest.mark.asyncio
async def test_target_not_found_raises_influencer_handle_not_found(monkeypatch):
    # Confirmed live against the real API during Phase 0 setup: code 110,
    # error_subcode 2207013, message "Invalid user id".
    client, _ = _make_client()
    mock_get = AsyncMock(
        return_value=_error_response(code=110, message="Invalid user id", subcode=2207013)
    )
    monkeypatch.setattr(client._http, "get", mock_get)

    with pytest.raises(InfluencerHandleNotFoundError):
        await client.get_business_profile("this_does_not_exist")
    await client.close()


@pytest.mark.asyncio
async def test_high_usage_pct_proactively_cools_down_token(monkeypatch):
    client, token_id = _make_client()
    exhausted = []

    async def token_exhauster(tid, until):
        exhausted.append((tid, until))

    client, token_id = _make_client(token_exhauster=token_exhauster)
    mock_get = AsyncMock(
        return_value=httpx.Response(
            200,
            json={"business_discovery": {"username": "x"}},
            headers=_usage_header(97),
        )
    )
    monkeypatch.setattr(client._http, "get", mock_get)

    await client.get_business_profile("x")

    assert len(exhausted) == 1
    assert exhausted[0][0] == token_id
    await client.close()


@pytest.mark.asyncio
async def test_proactive_cooldown_stops_reusing_the_token_for_later_calls(monkeypatch):
    """Regression test: marking a token exhausted in the DB is pointless
    if this client instance keeps handing it right back out for the rest
    of the job's own pagination -- self._current must be cleared too, so
    the NEXT call actually asks the provider for a fresh token."""
    provided_ids = [uuid4(), uuid4()]
    calls = []

    async def token_provider():
        calls.append(1)
        return provided_ids[len(calls) - 1], "test-access-token", "17841400000000000"

    client, _ = _make_client(token_provider=token_provider)
    mock_get = AsyncMock(
        return_value=httpx.Response(
            200,
            json={"business_discovery": {"username": "x"}},
            headers=_usage_header(97),  # above the proactive cooldown threshold every time
        )
    )
    monkeypatch.setattr(client._http, "get", mock_get)

    await client.get_business_profile("x")
    assert len(calls) == 1
    # Cleared as part of the cooldown itself -- the whole point of the fix.
    assert client.last_token_id is None

    await client.get_business_profile("x")
    # A second call must re-ask the provider (2 calls total) rather than
    # silently reusing the token that was just flagged for cooldown --
    # without the fix, self._current would still hold provided_ids[0] and
    # _ensure_token() would never call the provider again.
    assert len(calls) == 2
    await client.close()


@pytest.mark.asyncio
async def test_rotation_cap_respected(monkeypatch):
    monkeypatch.setattr("app.scraper.instagram_graph_client.asyncio.sleep", _noop_sleep)

    async def token_provider():
        return uuid4(), "tok", "ig"

    client, _ = _make_client(token_provider=token_provider)
    # Every attempt fails with a rotate-worthy error -- must give up after
    # _MAX_TOKEN_ROTATIONS, not loop forever.
    mock_get = AsyncMock(return_value=_error_response(code=4, message="always rate limited"))
    monkeypatch.setattr(client._http, "get", mock_get)

    with pytest.raises(ScraperRateLimitError):
        await client.get_business_profile("x")

    assert mock_get.call_count == 10  # _MAX_TOKEN_ROTATIONS
    await client.close()


@pytest.mark.asyncio
async def test_pagination_uses_media_after_cursor(monkeypatch):
    client, _ = _make_client()
    mock_get = AsyncMock(
        return_value=httpx.Response(200, json={"business_discovery": {"media": {"data": []}}})
    )
    monkeypatch.setattr(client._http, "get", mock_get)

    await client.get_business_media("myntra", after="CURSOR123")

    called_params = mock_get.call_args.kwargs["params"]
    assert ".after(CURSOR123)" in called_params["fields"]
    await client.close()
