"""Thin wrapper over Meta's official Instagram Graph API "Business
Discovery" endpoint. See docs/INSTAGRAM_GRAPH_API_PLAN.md and
docs/INSTAGRAM_HYBRID_IMPLEMENTATION.md PR1 §1.5 for the design.

Mirrors YouTubeClient's shape (dependency-injected provider callbacks, a
_ROTATE sentinel, a per-token retry loop bounded by SCRAPER_MAX_RETRIES,
key/token rotation bounded by a rotation cap) -- same reasoning: this stays
DB-free and unit-testable, with the concrete repo-backed callbacks wired in
by whatever calls it (app/workers/instagram_token_provider.py, PR2).

Deviations from the plan doc, confirmed empirically against the live API
before writing this (docs/INSTAGRAM_GRAPH_API_PLAN.md Phase 0.5's "verify
against current docs/fixtures" step):
- Rate-limit header is `x-app-usage` (percentages for call_count,
  total_cputime, total_time), NOT `X-Business-Use-Case-Usage` -- Business
  Discovery apparently reports under the standard per-app usage header,
  not a per-Business-Use-Case one.
- API version v23.0 is deprecated; Meta auto-upgrades unversioned/old
  calls to v25.0 with a warning header. Config defaults to v25.0.
"""

from __future__ import annotations

import asyncio
import json
import random
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable
from uuid import UUID

import httpx

from app.core.config import settings
from app.core.exceptions import (
    InfluencerHandleNotFoundError,
    InstagramAccountNotProfessionalError,
    NoUsableInstagramTokenError,
    ScraperRateLimitError,
    ScraperTimeoutError,
)
from app.core.logging import get_logger
from app.scraper.rate_limit import TokenBucketRateLimiter

logger = get_logger(__name__)

_BACKOFF_BASE_S = 5.0
_BACKOFF_MAX_S = 120.0

# Safety cap on how many distinct tokens a single request will rotate
# through before giving up -- see YouTubeClient._MAX_KEY_ROTATIONS for the
# identical reasoning (a pool never realistically has more than a handful
# of tokens; this just guards against get_usable_token()/mark_exhausted()
# ever disagreeing about a token's state).
_MAX_TOKEN_ROTATIONS = 10

# Meta error codes that mean "this token is rate-limited, try another /
# wait" -- rotate rather than fail the job. Confirmed shape: `code` at the
# top level of the `error` object; `error_subcode` 2108006 (or a message
# mentioning "not a professional account") is the separate, non-retryable
# "target isn't Business-Discovery-readable" case handled by
# InstagramAccountNotProfessionalError instead.
_RATE_LIMIT_CODES = {4, 17, 32, 613}
_INVALID_TOKEN_CODE = 190
_TARGET_NOT_FOUND_CODE = 110
_NOT_PROFESSIONAL_SUBCODE = 2108006

# How full the app-level usage header (any of call_count/total_cputime/
# total_time) can get before this client proactively cools the token down
# rather than waiting for a hard rate-limit error.
_USAGE_PROACTIVE_COOLDOWN_PCT = 95.0
_USAGE_PROACTIVE_COOLDOWN_S = 3600

TokenProvider = Callable[[], Awaitable[tuple[UUID, str, str]]]  # (id, access_token, ig_user_id)
UsageRecorder = Callable[[UUID, int, float | None], Awaitable[None]]  # (id, calls, max_usage_pct)
TokenExhauster = Callable[[UUID, datetime], Awaitable[None]]  # (id, cooldown_until)
TokenInvalidator = Callable[[UUID, str], Awaitable[None]]

# Sentinel returned internally by _request_with_token to mean "this token
# is spent -- rotate and retry the same logical request on another one."
_ROTATE = object()


def _extract_error(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    error = payload.get("error")
    return error if isinstance(error, dict) else {}


def _max_usage_pct(header_value: str | None) -> float | None:
    """Parses the x-app-usage header's JSON body and returns the max
    percentage across call_count/total_cputime/total_time -- any one of
    the three hitting its cap throttles the app, so the worst of the three
    is what matters for the proactive-cooldown decision."""
    if not header_value:
        return None
    try:
        data = json.loads(header_value)
    except (ValueError, TypeError):
        return None
    values = [v for v in (data.get("call_count"), data.get("total_cputime"), data.get("total_time")) if isinstance(v, (int, float))]
    return max(values) if values else None


class InstagramGraphClient:
    """token_provider/usage_recorder/token_exhauster/token_invalidator are
    async callbacks (not a direct repo/session dependency), same reasoning
    as YouTubeClient -- this stays decoupled from any particular DB
    session's lifetime."""

    def __init__(
        self,
        token_provider: TokenProvider,
        usage_recorder: UsageRecorder,
        token_exhauster: TokenExhauster,
        token_invalidator: TokenInvalidator,
    ):
        self._token_provider = token_provider
        self._usage_recorder = usage_recorder
        self._token_exhauster = token_exhauster
        self._token_invalidator = token_invalidator
        self._http = httpx.AsyncClient(timeout=settings.SCRAPER_TIMEOUT_S)
        self._current: tuple[UUID, str, str] | None = None
        self._rate_limiter = TokenBucketRateLimiter(
            rate_per_s=settings.INSTAGRAM_GRAPH_RATE_PER_HOUR / 3600,
            burst=5,
        )

    async def _ensure_token(self) -> tuple[UUID, str, str]:
        if self._current is None:
            self._current = await self._token_provider()
        return self._current

    @property
    def last_token_id(self) -> UUID | None:
        return self._current[0] if self._current else None

    async def _request_with_token(
        self,
        ig_user_id: str,
        fields: str,
        token_id: UUID,
        access_token: str,
        handle: str,
    ) -> dict[str, Any] | object:
        """One token's worth of the request, including its own network/5xx
        backoff loop (bounded by SCRAPER_MAX_RETRIES). Returns the parsed
        `business_discovery` object on success, or the _ROTATE sentinel if
        this token is spent/bad and the caller should try the next one."""
        params = {"fields": fields, "access_token": access_token}
        url = f"https://graph.facebook.com/{settings.INSTAGRAM_GRAPH_API_VERSION}/{ig_user_id}"
        for attempt in range(settings.SCRAPER_MAX_RETRIES + 1):
            await self._rate_limiter.acquire()
            try:
                response = await self._http.get(url, params=params)
            except Exception:
                if attempt < settings.SCRAPER_MAX_RETRIES:
                    wait_s = min(_BACKOFF_BASE_S * (2**attempt), _BACKOFF_MAX_S)
                    wait_s += random.uniform(0, wait_s * 0.2)
                    await asyncio.sleep(wait_s)
                    continue
                raise ScraperTimeoutError(handle=handle)

            usage_pct = _max_usage_pct(response.headers.get("x-app-usage"))

            if response.status_code == 200:
                payload = response.json()
                await self._usage_recorder(token_id, 1, usage_pct)
                if usage_pct is not None and usage_pct >= _USAGE_PROACTIVE_COOLDOWN_PCT:
                    logger.warning(
                        "Instagram Graph API token near usage cap, proactively cooling down",
                        token_id=str(token_id),
                        usage_pct=usage_pct,
                    )
                    await self._token_exhauster(
                        token_id, datetime.now(timezone.utc) + timedelta(seconds=_USAGE_PROACTIVE_COOLDOWN_S)
                    )
                    # Without this, self._current stays set to this
                    # now-cooling-down token, and _ensure_token() only ever
                    # refetches when it's None -- every remaining request
                    # this client instance makes for the rest of THIS job's
                    # pagination would keep reusing the token proactive
                    # cooldown was specifically meant to stop hammering,
                    # defeating the whole point of checking usage_pct here.
                    self._current = None
                return payload.get("business_discovery", {})

            try:
                payload = response.json()
            except Exception:
                payload = None
            error = _extract_error(payload)
            code = error.get("code")
            subcode = error.get("error_subcode")
            message = str(error.get("message") or response.text)

            if code == _TARGET_NOT_FOUND_CODE and subcode != _NOT_PROFESSIONAL_SUBCODE:
                raise InfluencerHandleNotFoundError(handle, "instagram")
            if code == 100 and subcode == _NOT_PROFESSIONAL_SUBCODE:
                raise InstagramAccountNotProfessionalError(handle)
            # Message-based fallback for the not-professional case -- the
            # exact subcode is Phase 0.5-assumed, not independently
            # confirmed against a real personal-account response (none of
            # the handles tried during setup turned out to be personal
            # accounts). Keep both checks until a real one is captured.
            if "not a professional account" in message.lower() or "not an instagram business" in message.lower():
                raise InstagramAccountNotProfessionalError(handle)

            if code in _RATE_LIMIT_CODES:
                logger.warning("Instagram Graph API token rate limited, rotating", token_id=str(token_id), code=code)
                await self._token_exhauster(token_id, datetime.now(timezone.utc) + timedelta(hours=1))
                return _ROTATE
            if code == _INVALID_TOKEN_CODE:
                logger.warning("Instagram Graph API token invalid, rotating", token_id=str(token_id))
                await self._token_invalidator(token_id, message)
                return _ROTATE

            if response.status_code == 429 or response.status_code >= 500:
                if attempt < settings.SCRAPER_MAX_RETRIES:
                    wait_s = min(_BACKOFF_BASE_S * (2**attempt), _BACKOFF_MAX_S)
                    wait_s += random.uniform(0, wait_s * 0.2)
                    await asyncio.sleep(wait_s)
                    continue
                raise ScraperRateLimitError(handle=handle)

            # Any other error we don't have a specific handler for --
            # rotate rather than fail outright, since we can't tell from
            # here whether it's token-specific.
            logger.warning("Instagram Graph API request failed, rotating", token_id=str(token_id), code=code, message=message)
            return _ROTATE

        raise ScraperTimeoutError(handle=handle)

    async def _business_discovery(self, username: str, fields: str) -> dict[str, Any]:
        for _ in range(_MAX_TOKEN_ROTATIONS):
            try:
                token_id, access_token, ig_user_id = await self._ensure_token()
            except NoUsableInstagramTokenError:
                raise ScraperRateLimitError(handle=username, retry_after=_USAGE_PROACTIVE_COOLDOWN_S)

            result = await self._request_with_token(ig_user_id, fields, token_id, access_token, username)
            if result is _ROTATE:
                self._current = None
                continue
            return result  # type: ignore[return-value]

        raise ScraperRateLimitError(handle=username)

    _MEDIA_SUBFIELDS = (
        "id,caption,like_count,comments_count,media_type,media_product_type,"
        "media_url,thumbnail_url,permalink,timestamp,children{media_type,media_url,thumbnail_url}"
    )

    async def get_business_profile(self, username: str) -> dict[str, Any]:
        """Profile fields + first media page in one call."""
        fields = (
            f"business_discovery.username({username})"
            "{username,name,biography,website,followers_count,follows_count,media_count,"
            f"profile_picture_url,media.limit({settings.INSTAGRAM_GRAPH_MEDIA_PAGE_SIZE})"
            f"{{{self._MEDIA_SUBFIELDS}}}}}"
        )
        return await self._business_discovery(username, fields)

    async def get_business_media(self, username: str, after: str) -> dict[str, Any]:
        """A subsequent media page via media.after(cursor) -- no profile
        re-fetch, just the media connection."""
        fields = (
            f"business_discovery.username({username})"
            f"{{media.limit({settings.INSTAGRAM_GRAPH_MEDIA_PAGE_SIZE}).after({after})"
            f"{{{self._MEDIA_SUBFIELDS}}}}}"
        )
        return await self._business_discovery(username, fields)

    async def close(self) -> None:
        await self._http.aclose()
