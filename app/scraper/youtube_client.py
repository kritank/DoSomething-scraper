from __future__ import annotations

import asyncio
import random
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable
from uuid import UUID
from zoneinfo import ZoneInfo

import httpx

from app.core.config import settings
from app.core.exceptions import (
    NoUsableYouTubeKeyError,
    ScraperBlockedError,
    ScraperRateLimitError,
    ScraperTimeoutError,
    YouTubeResourceGoneError,
)
from app.core.logging import get_logger
from app.scraper.rate_limit import TokenBucketRateLimiter

logger = get_logger(__name__)

_BACKOFF_BASE_S = 5.0
_BACKOFF_MAX_S = 120.0

# Safety cap on how many distinct keys a single request will rotate through
# before giving up -- distinct from SCRAPER_MAX_RETRIES (which bounds
# network/429/5xx retries against ONE key). A pool never realistically has
# more than a handful of keys; this just prevents an infinite loop if
# get_usable_key()/mark_exhausted() ever disagree about a key's state.
_MAX_KEY_ROTATIONS = 10

# Reasons the API reports under HTTP 403 that mean "this key is out of
# quota for today" -- rotate to another key, don't fail the job.
_QUOTA_REASONS = {"quotaExceeded", "dailyLimitExceeded", "rateLimitExceeded", "userRateLimitExceeded"}
# Reasons that mean the key itself is bad, not just out of quota.
_INVALID_KEY_REASONS = {"keyInvalid", "accessNotConfigured", "badRequest", "forbidden"}

KeyProvider = Callable[[], Awaitable[tuple[UUID, str]]]
UsageRecorder = Callable[[UUID, int], Awaitable[None]]
KeyExhauster = Callable[[UUID], Awaitable[None]]
KeyInvalidator = Callable[[UUID, str], Awaitable[None]]

# Sentinel returned internally by _request_with_key to mean "this key is
# spent -- rotate and retry the same logical request on another one."
_ROTATE = object()

_PACIFIC = ZoneInfo("America/Los_Angeles")


def next_midnight_pacific(now: datetime | None = None) -> datetime:
    """YouTube's quota resets at midnight Pacific. Shared with
    YouTubeApiKeyRepo (which imports this rather than duplicating it) so a
    key's quota_reset_at and a fully-exhausted pool's
    ScraperRateLimitError(retry_after=...) always agree on the boundary."""
    now = now or datetime.now(timezone.utc)
    now_pt = now.astimezone(_PACIFIC)
    next_midnight_pt = (now_pt + timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return next_midnight_pt.astimezone(timezone.utc)


def seconds_until_next_quota_reset() -> int:
    return max(1, int((next_midnight_pacific() - datetime.now(timezone.utc)).total_seconds()))


def _extract_error_reason(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None
    errors = (payload.get("error") or {}).get("errors") or []
    if errors and isinstance(errors[0], dict):
        return errors[0].get("reason")
    return None


def _extract_error_message(payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""
    return str((payload.get("error") or {}).get("message") or "")


class YouTubeClient:
    """Thin wrapper over the official YouTube Data API v3.

    Plain httpx (no TLS impersonation, no proxies) -- this is a public,
    documented, key-authenticated API, not a scraped session, so none of
    InstagramClient's anti-bot machinery applies. The only scarce resource
    is per-key daily quota, managed here via key rotation.

    key_provider/usage_recorder/key_exhauster/key_invalidator are async
    callbacks (not a direct repo/session dependency) so this client stays
    decoupled from any particular DB session's lifetime -- each callback
    opens its own short-lived session, the same pattern JobProcessor's
    heartbeat uses. See app/workers/youtube_key_provider.py for the
    concrete implementations wired in by YouTubeJobProcessor.
    """

    BASE = "https://www.googleapis.com/youtube/v3"

    def __init__(
        self,
        key_provider: KeyProvider,
        usage_recorder: UsageRecorder,
        key_exhauster: KeyExhauster,
        key_invalidator: KeyInvalidator,
    ):
        self._key_provider = key_provider
        self._usage_recorder = usage_recorder
        self._key_exhauster = key_exhauster
        self._key_invalidator = key_invalidator
        self._http = httpx.AsyncClient(timeout=15.0)
        self._current: tuple[UUID, str] | None = None
        # Running total of quota units this client instance has spent --
        # i.e. across this one job, since a fresh YouTubeClient is
        # constructed per job (see YouTubeJobProcessor.process). Read by
        # the processor after the scrape for ScrapeJob.quota_units_used,
        # independent of (and in addition to) the per-key daily total
        # usage_recorder writes to the DB.
        self._units_used = 0
        self._rate_limiter = TokenBucketRateLimiter(
            rate_per_s=settings.YOUTUBE_RATE_LIMIT_RPS,
            burst=settings.YOUTUBE_RATE_LIMIT_BURST,
        )

    async def _ensure_key(self) -> tuple[UUID, str]:
        if self._current is None:
            self._current = await self._key_provider()
        return self._current

    @property
    def last_key_id(self) -> UUID | None:
        """The key currently in use, for ops visibility into "which key ran
        this job" (see YouTubeJobProcessor.process). None until the first
        request resolves one. If the key rotated mid-job (quota exhaustion
        -- see _get), this reflects whichever key was used last, not every
        key touched."""
        return self._current[0] if self._current else None

    @property
    def units_used(self) -> int:
        """Total quota units this client has spent so far -- i.e. this job's
        running total. See ScrapeJob.quota_units_used."""
        return self._units_used

    async def _request_with_key(
        self,
        resource: str,
        params: dict[str, Any],
        key_id: UUID,
        api_key: str,
        quota_units: int,
        handle: str,
    ) -> dict[str, Any] | object:
        """One key's worth of the request, including its own network/429/5xx
        backoff loop (bounded by SCRAPER_MAX_RETRIES). Returns the parsed
        JSON on success, or the _ROTATE sentinel if this key is spent/bad
        and the caller should try the next one."""
        request_params = {**params, "key": api_key}
        for attempt in range(settings.SCRAPER_MAX_RETRIES + 1):
            await self._rate_limiter.acquire()
            try:
                response = await self._http.get(f"{self.BASE}/{resource}", params=request_params)
            except Exception:
                if attempt < settings.SCRAPER_MAX_RETRIES:
                    wait_s = min(_BACKOFF_BASE_S * (2**attempt), _BACKOFF_MAX_S)
                    wait_s += random.uniform(0, wait_s * 0.2)
                    await asyncio.sleep(wait_s)
                    continue
                raise ScraperTimeoutError(handle=handle)

            if response.status_code == 200:
                await self._usage_recorder(key_id, quota_units)
                self._units_used += quota_units
                return response.json()

            try:
                payload = response.json()
            except Exception:
                payload = None
            reason = _extract_error_reason(payload)
            message = _extract_error_message(payload) or response.text

            if response.status_code == 403 and reason == "commentsDisabled":
                raise YouTubeResourceGoneError("commentsDisabled", resource=resource)
            if response.status_code == 400 and reason == "invalidPageToken":
                raise YouTubeResourceGoneError("invalidPageToken", resource=resource)
            if response.status_code == 404:
                raise YouTubeResourceGoneError("notFound", resource=resource)

            if response.status_code == 403 and reason in _QUOTA_REASONS:
                logger.warning("YouTube key out of quota, rotating", key_id=str(key_id), reason=reason)
                await self._key_exhauster(key_id)
                return _ROTATE
            if (response.status_code == 400 and reason in _INVALID_KEY_REASONS) or (
                response.status_code == 403 and reason == "accessNotConfigured"
            ):
                logger.warning("YouTube key invalid, rotating", key_id=str(key_id), reason=reason)
                await self._key_invalidator(key_id, message)
                return _ROTATE

            if response.status_code == 429 or response.status_code >= 500:
                if attempt < settings.SCRAPER_MAX_RETRIES:
                    wait_s = min(_BACKOFF_BASE_S * (2**attempt), _BACKOFF_MAX_S)
                    wait_s += random.uniform(0, wait_s * 0.2)
                    await asyncio.sleep(wait_s)
                    continue
                raise ScraperRateLimitError(handle=handle)

            if response.status_code in (401,):
                raise ScraperBlockedError(handle=handle, platform="youtube")

            # Any other 4xx we don't have a specific handler for -- not
            # retryable, not a key problem. Surface it plainly.
            raise ScraperBlockedError(
                handle=f"{handle} ({resource}: {message or response.status_code})", platform="youtube"
            )

        raise ScraperTimeoutError(handle=handle)

    async def _get(
        self, resource: str, params: dict[str, Any], quota_units: int = 1, handle: str = ""
    ) -> dict[str, Any]:
        for _ in range(_MAX_KEY_ROTATIONS):
            try:
                key_id, api_key = await self._ensure_key()
            except NoUsableYouTubeKeyError:
                raise ScraperRateLimitError(handle=handle, retry_after=seconds_until_next_quota_reset())

            result = await self._request_with_key(resource, params, key_id, api_key, quota_units, handle)
            if result is _ROTATE:
                self._current = None
                continue
            return result  # type: ignore[return-value]

        raise ScraperRateLimitError(handle=handle)

    async def get_channel(self, handle: str | None = None, channel_id: str | None = None) -> dict[str, Any]:
        """channels.list -- 1 unit. Exactly one of handle/channel_id must be set."""
        params = {"part": "snippet,statistics,contentDetails,brandingSettings,status,topicDetails"}
        if channel_id:
            params["id"] = channel_id
        else:
            normalized = handle or ""
            if not normalized.startswith("@"):
                normalized = f"@{normalized}"
            params["forHandle"] = normalized
        return await self._get("channels", params, quota_units=1, handle=handle or channel_id or "")

    async def get_uploads_page(self, uploads_playlist_id: str, page_token: str = "") -> dict[str, Any]:
        """playlistItems.list -- 1 unit. maxResults=50 (this endpoint's max)."""
        params: dict[str, Any] = {
            "part": "contentDetails",
            "playlistId": uploads_playlist_id,
            "maxResults": 50,
        }
        if page_token:
            params["pageToken"] = page_token
        return await self._get("playlistItems", params, quota_units=1, handle=uploads_playlist_id)

    async def get_videos(self, video_ids: list[str]) -> dict[str, Any]:
        """videos.list -- 1 unit for the WHOLE batch (up to 50 ids), not per video."""
        params = {
            "part": "snippet,statistics,contentDetails,status,topicDetails,liveStreamingDetails,paidProductPlacementDetails",
            "id": ",".join(video_ids[:50]),
        }
        return await self._get("videos", params, quota_units=1, handle=",".join(video_ids[:3]))

    async def get_comment_threads(self, video_id: str, page_token: str = "") -> dict[str, Any]:
        """commentThreads.list -- 1 unit. order=time for stable pagination
        (mirrors InstagramClient.get_media_comments' chronological sort)."""
        params: dict[str, Any] = {
            "part": "snippet,replies",
            "videoId": video_id,
            "maxResults": 100,
            "order": "time",
            "textFormat": "plainText",
        }
        if page_token:
            params["pageToken"] = page_token
        return await self._get("commentThreads", params, quota_units=1, handle=video_id)

    async def get_comment_replies(self, parent_comment_id: str, page_token: str = "") -> dict[str, Any]:
        """comments.list -- 1 unit."""
        params: dict[str, Any] = {
            "part": "snippet",
            "parentId": parent_comment_id,
            "maxResults": 100,
            "textFormat": "plainText",
        }
        if page_token:
            params["pageToken"] = page_token
        return await self._get("comments", params, quota_units=1, handle=parent_comment_id)

    async def close(self) -> None:
        await self._http.aclose()
