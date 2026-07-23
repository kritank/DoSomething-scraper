from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.core.config import settings
from app.core.exceptions import ScraperBlockedError, ScraperRateLimitError, ScraperTimeoutError
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


@pytest.mark.asyncio
async def test_get_too_many_redirects_raises_blocked_error_without_retry(monkeypatch):
    """Confirmed live in production: TooManyRedirects means the account's
    cookie session can no longer load this page at all (Instagram
    redirects it to itself indefinitely, sending Set-Cookie:
    sessionid=deleted) -- not a transient network blip. Must raise
    immediately, same as a genuine checkpoint, not burn 3 retries against
    a deterministic failure."""
    from curl_cffi.requests.exceptions import TooManyRedirects

    client = _make_client()
    mock_get = AsyncMock(side_effect=TooManyRedirects("Maximum (30) redirects followed"))
    monkeypatch.setattr(client._curl, "get", mock_get)

    with pytest.raises(ScraperBlockedError):
        await client._get("https://i.instagram.com/api/v1/some_endpoint", handle="testuser")

    assert mock_get.call_count == 1  # never retried
    await client.close()


@pytest.mark.asyncio
async def test_401_with_please_wait_body_retries_instead_of_blocking(monkeypatch):
    """Confirmed live in production: Instagram returns HTTP 401 with
    {"message": "Please wait a few minutes before you try again.",
    "require_login": true, ...} for an ordinary rate/volume throttle on a
    perfectly valid, working session -- not a checkpoint. Treating every
    401/403 as an unconditional hard block (the previous behavior) parked
    healthy accounts in checkpoint_required permanently: account_revalidator's
    own probe hits the identical throttle and never clears it, since
    nothing about the account or session was ever actually wrong."""
    monkeypatch.setattr("app.scraper.client.asyncio.sleep", _noop)

    client = _make_client()
    mock_get = AsyncMock(
        side_effect=[
            _FakeResponse(
                401,
                json_data={
                    "message": "Please wait a few minutes before you try again.",
                    "require_login": True,
                    "status": "fail",
                },
            ),
            _FakeResponse(200, json_data={"status": "ok", "items": []}),
        ]
    )
    monkeypatch.setattr(client._curl, "get", mock_get)

    result = await client._get("https://i.instagram.com/api/v1/some_endpoint", handle="testuser")

    assert result == {"status": "ok", "items": []}
    assert mock_get.call_count == 2
    await client.close()


@pytest.mark.asyncio
async def test_401_with_please_wait_body_exhausts_retries_as_rate_limit(monkeypatch):
    monkeypatch.setattr("app.scraper.client.asyncio.sleep", _noop)
    monkeypatch.setattr(settings, "SCRAPER_MAX_RETRIES", 1)

    client = _make_client()
    monkeypatch.setattr(
        client._curl,
        "get",
        AsyncMock(
            return_value=_FakeResponse(
                401,
                json_data={"message": "Please wait a few minutes before you try again.", "status": "fail"},
            )
        ),
    )

    with pytest.raises(ScraperRateLimitError):
        await client._get("https://i.instagram.com/api/v1/some_endpoint", handle="testuser")
    await client.close()


@pytest.mark.asyncio
async def test_401_with_checkpoint_body_still_blocks_without_retry(monkeypatch):
    """A 401 whose body genuinely indicates a checkpoint/hijacked session
    must still hard-block immediately, exactly like the 200-status
    checkpoint case -- only the "please wait" soft-throttle body should be
    softened."""
    client = _make_client()
    mock_get = AsyncMock(
        return_value=_FakeResponse(
            401,
            json_data={"status": "fail", "message": "checkpoint_required", "checkpoint_url": "/challenge/"},
        )
    )
    monkeypatch.setattr(client._curl, "get", mock_get)

    with pytest.raises(ScraperBlockedError):
        await client._get("https://i.instagram.com/api/v1/some_endpoint", handle="testuser")

    assert mock_get.call_count == 1  # never retried -- not recoverable
    await client.close()


@pytest.mark.asyncio
async def test_checkpoint_status_raises_blocked_error(monkeypatch):
    """A real checkpoint/login-required body (200 OK, non-"ok" status,
    checkpoint_url or a checkpoint-flavored message) is the one case that
    should still map to ScraperBlockedError -- an actual hijacked/invalidated
    session that no retry can fix."""
    client = _make_client()
    mock_get = AsyncMock(
        return_value=_FakeResponse(
            200,
            json_data={"status": "fail", "message": "checkpoint_required", "checkpoint_url": "/challenge/"},
        )
    )
    monkeypatch.setattr(client._curl, "get", mock_get)

    with pytest.raises(ScraperBlockedError):
        await client._get("https://i.instagram.com/api/v1/some_endpoint", handle="testuser")

    assert mock_get.call_count == 1  # never retried -- not recoverable
    await client.close()


@pytest.mark.asyncio
async def test_soft_fail_status_retries_instead_of_blocking(monkeypatch):
    """A non-"ok" status that ISN'T a checkpoint (e.g. a soft spam/feedback
    throttle) must NOT be treated as a blocked session -- that was the bug
    that kept parking perfectly healthy accounts in checkpoint_required.
    It should retry like a 429 and succeed once the throttle clears."""
    monkeypatch.setattr("app.scraper.client.asyncio.sleep", _noop)

    client = _make_client()
    mock_get = AsyncMock(
        side_effect=[
            _FakeResponse(200, json_data={"status": "fail", "message": "feedback_required"}),
            _FakeResponse(200, json_data={"status": "ok", "items": []}),
        ]
    )
    monkeypatch.setattr(client._curl, "get", mock_get)

    result = await client._get("https://i.instagram.com/api/v1/some_endpoint", handle="testuser")

    assert result == {"status": "ok", "items": []}
    assert mock_get.call_count == 2
    await client.close()


@pytest.mark.asyncio
async def test_soft_fail_status_exhausts_retries_as_rate_limit(monkeypatch):
    """If a non-checkpoint "fail" status never clears, it should surface as
    ScraperRateLimitError (retryable at the job level, cooldown on the
    account) -- not ScraperBlockedError (terminal, needs manual resolution)."""
    monkeypatch.setattr("app.scraper.client.asyncio.sleep", _noop)
    monkeypatch.setattr(settings, "SCRAPER_MAX_RETRIES", 1)

    client = _make_client()
    monkeypatch.setattr(
        client._curl,
        "get",
        AsyncMock(return_value=_FakeResponse(200, json_data={"status": "fail", "message": "feedback_required"})),
    )

    with pytest.raises(ScraperRateLimitError):
        await client._get("https://i.instagram.com/api/v1/some_endpoint", handle="testuser")
    await client.close()


@pytest.mark.asyncio
async def test_graphql_post_401_with_please_wait_body_retries_instead_of_blocking(monkeypatch):
    """Same soft-throttle fix as _get, applied to the comment/reply
    GraphQL POST path (_graphql_post) -- the endpoint comment sync
    actually walks through, so this is the path that was silently
    stranding accounts the moment enrichment started doing real work."""
    monkeypatch.setattr("app.scraper.client.asyncio.sleep", _noop)

    client = _make_client()
    monkeypatch.setattr(client, "_ensure_csrf_tokens", AsyncMock(return_value=("dtsg", "lsd")))
    mock_post = AsyncMock(
        side_effect=[
            _FakeResponse(
                401,
                json_data={"message": "Please wait a few minutes before you try again.", "status": "fail"},
            ),
            _FakeResponse(200, json_data={"status": "ok", "data": {}}),
        ]
    )
    monkeypatch.setattr(client._curl, "post", mock_post)

    result = await client._graphql_post("SomeQuery", "12345", {}, referer="https://instagram.com/p/x/")

    assert result == {"status": "ok", "data": {}}
    assert mock_post.call_count == 2
    await client.close()


@pytest.mark.asyncio
async def test_graphql_post_401_with_checkpoint_body_still_blocks_without_retry(monkeypatch):
    client = _make_client()
    monkeypatch.setattr(client, "_ensure_csrf_tokens", AsyncMock(return_value=("dtsg", "lsd")))
    mock_post = AsyncMock(
        return_value=_FakeResponse(
            401,
            json_data={"status": "fail", "message": "checkpoint_required", "checkpoint_url": "/challenge/"},
        )
    )
    monkeypatch.setattr(client._curl, "post", mock_post)

    with pytest.raises(ScraperBlockedError):
        await client._graphql_post("SomeQuery", "12345", {}, referer="https://instagram.com/p/x/")


@pytest.mark.asyncio
async def test_graphql_post_retries_when_csrf_token_fetch_raises(monkeypatch):
    """Regression confirmed live in production: _ensure_csrf_tokens's plain
    page-load GET had no exception handling at all -- when it hit an
    infinite self-redirect (Instagram serving a logged-out/consent
    interstitial only a real browser's JS can escape, observed
    identically across every pooled account), the raw TooManyRedirects
    propagated straight out of _graphql_post, skipping its retry loop
    entirely and failing every single comment/reply sync attempt outright
    with zero backoff. Must now get the same retry/backoff treatment as
    a POST-side network blip."""
    monkeypatch.setattr("app.scraper.client.asyncio.sleep", _noop)

    client = _make_client()
    mock_ensure = AsyncMock(side_effect=[RuntimeError("Maximum (30) redirects followed"), ("dtsg", "lsd")])
    monkeypatch.setattr(client, "_ensure_csrf_tokens", mock_ensure)
    mock_post = AsyncMock(return_value=_FakeResponse(200, json_data={"status": "ok", "data": {}}))
    monkeypatch.setattr(client._curl, "post", mock_post)

    result = await client._graphql_post("SomeQuery", "12345", {}, referer="https://instagram.com/p/x/")

    assert result == {"status": "ok", "data": {}}
    assert mock_ensure.call_count == 2  # retried, not crashed
    assert mock_post.call_count == 1  # only reached once tokens finally succeeded
    await client.close()


@pytest.mark.asyncio
async def test_graphql_post_exhausts_retries_when_csrf_token_fetch_always_raises(monkeypatch):
    monkeypatch.setattr("app.scraper.client.asyncio.sleep", _noop)
    monkeypatch.setattr(settings, "SCRAPER_MAX_RETRIES", 1)

    client = _make_client()
    monkeypatch.setattr(
        client, "_ensure_csrf_tokens", AsyncMock(side_effect=RuntimeError("Maximum (30) redirects followed"))
    )

    with pytest.raises(ScraperTimeoutError):
        await client._graphql_post("SomeQuery", "12345", {}, referer="https://instagram.com/p/x/")
    await client.close()


@pytest.mark.asyncio
async def test_graphql_post_too_many_redirects_raises_blocked_error_without_retry(monkeypatch):
    """Same distinction as _get's equivalent test -- TooManyRedirects from
    the CSRF token fetch means the session can't authenticate for the
    full-page surface at all, so it must raise immediately rather than
    retrying a deterministic failure 3 times first."""
    from curl_cffi.requests.exceptions import TooManyRedirects

    client = _make_client()
    mock_ensure = AsyncMock(side_effect=TooManyRedirects("Maximum (30) redirects followed"))
    monkeypatch.setattr(client, "_ensure_csrf_tokens", mock_ensure)

    with pytest.raises(ScraperBlockedError):
        await client._graphql_post("SomeQuery", "12345", {}, referer="https://instagram.com/p/x/")

    assert mock_ensure.call_count == 1  # never retried
    await client.close()


@pytest.mark.asyncio
async def test_400_retries_instead_of_raising_unhandled_error(monkeypatch):
    """A 400 from Instagram's web endpoints is intermittent (confirmed
    against real job history -- the same account/handle succeeds a run or
    two later), not a malformed request or a blocked session. It must NOT
    fall through to raise_for_status(), which raises a raw, untyped error
    that JobProcessor's generic except-Exception catch-all blames on the
    account -- silently burning down every account's failure_count for
    something none of them did wrong."""
    monkeypatch.setattr("app.scraper.client.asyncio.sleep", _noop)

    client = _make_client()
    mock_get = AsyncMock(
        side_effect=[
            _FakeResponse(400),
            _FakeResponse(200, json_data={"status": "ok", "items": []}),
        ]
    )
    monkeypatch.setattr(client._curl, "get", mock_get)

    result = await client._get("https://i.instagram.com/api/v1/some_endpoint", handle="testuser")

    assert result == {"status": "ok", "items": []}
    assert mock_get.call_count == 2
    await client.close()


@pytest.mark.asyncio
async def test_400_exhausts_retries_as_rate_limit_error(monkeypatch):
    """A persistent 400 surfaces as ScraperRateLimitError (retryable at the
    job level, cooldown on the account) -- not an unhandled exception that
    counts as an account-fault "error" outcome."""
    monkeypatch.setattr("app.scraper.client.asyncio.sleep", _noop)
    monkeypatch.setattr(settings, "SCRAPER_MAX_RETRIES", 1)

    client = _make_client()
    monkeypatch.setattr(client._curl, "get", AsyncMock(return_value=_FakeResponse(400)))

    with pytest.raises(ScraperRateLimitError):
        await client._get("https://i.instagram.com/api/v1/some_endpoint", handle="testuser")
    await client.close()
