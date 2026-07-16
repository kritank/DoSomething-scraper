import asyncio
import json
import random
import re
import time
from typing import Any

from curl_cffi.requests import AsyncSession as CurlAsyncSession

from app.core.config import settings
from app.core.exceptions import ScraperRateLimitError, ScraperBlockedError, ScraperTimeoutError
from app.core.logging import get_logger
from app.scraper.proxies import curl_proxies

logger = get_logger(__name__)

_BACKOFF_BASE_S = 5.0
_BACKOFF_MAX_S = 120.0


class TokenBucketRateLimiter:
    """Paces every outbound request against one Instagram account/session.

    Replaces per-coroutine `sleep(random(min, max))` calls: those pace each
    caller independently, so N concurrent comment-sync tasks sharing one
    client (see JobProcessor.COMMENT_SYNC_CONCURRENCY) produce an aggregate
    request rate N times higher than intended. A single bucket shared by the
    client makes the *aggregate* rate against the account the thing that's
    actually bounded, regardless of how many coroutines are drawing from it.
    """

    def __init__(self, rate_per_s: float, burst: int):
        self.rate_per_s = rate_per_s
        self.capacity = float(burst)
        self._tokens = float(burst)
        self._updated_at = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            while True:
                now = time.monotonic()
                elapsed = now - self._updated_at
                self._updated_at = now
                self._tokens = min(self.capacity, self._tokens + elapsed * self.rate_per_s)
                if self._tokens >= 1:
                    self._tokens -= 1
                    return
                wait_s = (1 - self._tokens) / self.rate_per_s
                wait_s += random.uniform(0, wait_s * 0.2)  # jitter -- looks less like a bot
                await asyncio.sleep(wait_s)

_IG_APP_ID = "936619743392459"
_ASBD_ID = "359341"
_FB_DTSG_RE = re.compile(r'"DTSGInitData",\[\],\{"token":"([^"]+)"')
_LSD_RE = re.compile(r'"LSD",\[\],\{"token":"([^"]+)"')

# Persisted GraphQL queries backing Instagram's web comment UI. There is no
# REST equivalent on www.instagram.com -- the mobile-app-shaped
# /api/v1/media/{pk}/comments/ path some earlier code assumed doesn't exist
# on the web domain at all (confirmed by capturing the real frontend's own
# network traffic); it silently 200s with the SPA shell instead of JSON.
_COMMENTS_QUERY = "PolarisPostCommentsPaginationQuery"
_COMMENTS_DOC_ID = "26864966453197043"
_REPLIES_QUERY = "PolarisPostChildCommentsQuery"
_REPLIES_DOC_ID = "27130774429946606"

# Instagram's "status" != "ok" envelope covers many unrelated conditions --
# soft spam/feedback throttles, transient "please wait" responses, and a
# real hijacked/invalidated session all come back as "status": "fail".
# Treating all of them as a checkpoint (see _is_checkpoint_response) parked
# perfectly healthy accounts in checkpoint_required for a transient fail
# that would have cleared on its own with a cooldown, on every single
# request that happened to hit one -- the account never actually needed
# manual resolution at all. Only these markers mean an actual
# hijacked/invalidated session that a retry can't fix.
_CHECKPOINT_MESSAGES = {"checkpoint_required", "login_required", "challenge_required"}


def _is_checkpoint_response(payload: dict[str, Any]) -> bool:
    if payload.get("checkpoint_url"):
        return True
    message = str(payload.get("message") or "").lower()
    return message in _CHECKPOINT_MESSAGES or "checkpoint" in message


class InstagramClient:
    def __init__(self, cookies: dict[str, str], user_agent: str, proxy: str | None = None):
        self.headers = {
            "User-Agent": user_agent,
            "Accept-Language": "en-US",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        }
        self.cookies = cookies

        # Every Instagram request goes through this Chrome-impersonating client.
        # Instagram fingerprints the TLS handshake itself (JA3/JA4) on both the
        # GraphQL endpoint (comments/replies) and the web_profile_info/feed
        # endpoints, silently 429ing or routing anything that doesn't match a
        # real browser. A plain httpx/OpenSSL TLS stack fails this gate --
        # crucially, only from datacenter IPs: residential IPs (e.g. a laptop)
        # are not gated, so httpx appears to work locally but is blocked from
        # EC2. curl_cffi reproduces Chrome's exact fingerprint via
        # curl-impersonate, far cheaper than driving a real browser per request.
        #
        # proxies pins every request to this account's dedicated egress IP.
        # The session cookies were minted from that same IP at registration
        # (see login_automator); replaying them from a different IP -- e.g. a
        # datacenter/EC2 address -- is exactly the pattern Instagram's
        # anti-hijack detection flags, forcing the account into
        # checkpoint_required. A residential/mobile proxy per account is the
        # structural fix for the recurring "email may not be secure" lockouts.
        self._curl = CurlAsyncSession(
            impersonate="chrome124",
            proxies=curl_proxies(proxy),
        )
        self._fb_dtsg: str | None = None
        self._lsd: str | None = None
        self._token_lock = asyncio.Lock()
        self._rate_limiter = TokenBucketRateLimiter(
            rate_per_s=settings.ACCOUNT_RATE_LIMIT_RPS,
            burst=settings.ACCOUNT_RATE_LIMIT_BURST,
        )

    @classmethod
    def from_account(cls, account, cookies: dict[str, str], proxy: str | None = None) -> "InstagramClient":
        """Convenience constructor for an InstagramAccount pool row."""
        return cls(cookies=cookies, user_agent=account.user_agent, proxy=proxy)

    async def _ensure_csrf_tokens(self, force: bool = False) -> tuple[str, str]:
        """fb_dtsg/lsd are session-scoped, not per-page -- fetched once (from
        a plain page load, no browser needed) and reused for every GraphQL
        call this client makes, rather than once per post.

        Locked so concurrent comment-sync tasks sharing one InstagramClient
        (see job_processor._sync_one) don't all fire a redundant fetch the
        first time tokens are needed.
        """
        async with self._token_lock:
            if force or self._fb_dtsg is None or self._lsd is None:
                response = await self._curl.get(
                    "https://www.instagram.com/",
                    headers=self.headers,
                    cookies=self.cookies,
                    timeout=15.0,
                )
                html = response.text
                dtsg_match = _FB_DTSG_RE.search(html)
                lsd_match = _LSD_RE.search(html)
                if not dtsg_match or not lsd_match:
                    raise ScraperBlockedError(handle="")
                self._fb_dtsg = dtsg_match.group(1)
                self._lsd = lsd_match.group(1)
            return self._fb_dtsg, self._lsd

    async def _graphql_post(
        self,
        friendly_name: str,
        doc_id: str,
        variables: dict[str, Any],
        referer: str,
        handle: str = "",
    ) -> dict[str, Any]:
        """POST a persisted GraphQL query via the Chrome-impersonating client.

        Retries once with freshly-fetched CSRF tokens if the response isn't
        JSON (stale/invalid fb_dtsg/lsd looks identical to a routing miss --
        both come back as a 200 HTML shell), then applies the same 429
        backoff semantics as _get.
        """
        last_retry_after: int | None = None
        for attempt in range(settings.SCRAPER_MAX_RETRIES + 1):
            await self._rate_limiter.acquire()
            fb_dtsg, lsd = await self._ensure_csrf_tokens()
            body = {
                "fb_dtsg": fb_dtsg,
                "lsd": lsd,
                "jazoest": "2" + str(sum(ord(c) for c in fb_dtsg)),
                "fb_api_caller_class": "RelayModern",
                "fb_api_req_friendly_name": friendly_name,
                "doc_id": doc_id,
                "variables": json.dumps(variables),
            }
            headers = {
                "x-ig-app-id": _IG_APP_ID,
                "x-csrftoken": self.cookies.get("csrftoken", ""),
                "x-fb-lsd": lsd,
                "x-fb-friendly-name": friendly_name,
                "x-asbd-id": _ASBD_ID,
                "referer": referer,
                "content-type": "application/x-www-form-urlencoded",
                "user-agent": self.headers["User-Agent"],
            }
            try:
                response = await self._curl.post(
                    "https://www.instagram.com/api/graphql",
                    data=body,
                    headers=headers,
                    cookies=self.cookies,
                    timeout=15.0,
                )
            except Exception:
                # curl_cffi has no implicit timeout -- without catching this,
                # a network blip (DNS hiccup, connection stall) hangs the
                # whole job for as long as the underlying socket sits open,
                # not just the 15s below. Give it the same retry/backoff as
                # a 429 rather than bailing out of the post immediately.
                if attempt < settings.SCRAPER_MAX_RETRIES:
                    wait_s = min(_BACKOFF_BASE_S * (2 ** attempt), _BACKOFF_MAX_S)
                    wait_s += random.uniform(0, wait_s * 0.2)
                    await asyncio.sleep(wait_s)
                    continue
                raise ScraperTimeoutError(handle=handle)
            if response.status_code == 429:
                retry_after_header = response.headers.get("Retry-After")
                last_retry_after = int(retry_after_header) if retry_after_header else None
                if attempt < settings.SCRAPER_MAX_RETRIES:
                    wait_s = last_retry_after if last_retry_after else min(
                        _BACKOFF_BASE_S * (2 ** attempt), _BACKOFF_MAX_S
                    )
                    wait_s += random.uniform(0, wait_s * 0.2)
                    await asyncio.sleep(wait_s)
                    continue
                raise ScraperRateLimitError(handle=handle, retry_after=last_retry_after)
            elif response.status_code in (401, 403):
                raise ScraperBlockedError(handle=handle)
            elif response.status_code >= 500:
                # Transient on Instagram's end, not a blocked/rate-limited
                # session -- retry with the same backoff instead of letting
                # a passing 5xx burn the whole job's retry_count.
                if attempt < settings.SCRAPER_MAX_RETRIES:
                    wait_s = min(_BACKOFF_BASE_S * (2 ** attempt), _BACKOFF_MAX_S)
                    wait_s += random.uniform(0, wait_s * 0.2)
                    await asyncio.sleep(wait_s)
                    continue
                raise ScraperTimeoutError(handle=handle)

            try:
                payload = response.json()
            except Exception:
                if attempt < settings.SCRAPER_MAX_RETRIES:
                    await self._ensure_csrf_tokens(force=True)
                    continue
                raise
            if isinstance(payload, dict) and payload.get("status") not in (None, "ok"):
                if _is_checkpoint_response(payload):
                    logger.warning(
                        "GraphQL response reported a checkpoint",
                        handle=handle,
                        friendly_name=friendly_name,
                        message=payload.get("message"),
                    )
                    raise ScraperBlockedError(handle=handle)
                # A non-checkpoint "fail" (soft throttle, feedback_required,
                # transient hiccup) -- retry like a 429 rather than parking
                # a perfectly healthy session in checkpoint_required for
                # something that clears with a cooldown.
                logger.warning(
                    "GraphQL response reported a non-ok, non-checkpoint status",
                    handle=handle,
                    friendly_name=friendly_name,
                    status=payload.get("status"),
                    message=payload.get("message"),
                )
                if attempt < settings.SCRAPER_MAX_RETRIES:
                    wait_s = min(_BACKOFF_BASE_S * (2 ** attempt), _BACKOFF_MAX_S)
                    wait_s += random.uniform(0, wait_s * 0.2)
                    await asyncio.sleep(wait_s)
                    continue
                raise ScraperRateLimitError(handle=handle)
            return payload
        raise ScraperTimeoutError(handle=handle)

    async def _get(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        handle: str = "",
    ) -> dict[str, Any]:
        """GET with 429/timeout backoff, issued through the Chrome-impersonating
        curl_cffi client so it clears Instagram's TLS-fingerprint gate on these
        web endpoints (see __init__ -- plain httpx passes locally but is 429'd
        from datacenter IPs). 401/403 surface immediately (never retried
        in-loop -- a blocked session retrying itself is pointless, and the
        caller needs it to surface right away so the account pool can mark the
        account for review)."""
        merged_headers = {**self.headers, **(headers or {})}
        last_retry_after: int | None = None
        for attempt in range(settings.SCRAPER_MAX_RETRIES + 1):
            await self._rate_limiter.acquire()
            try:
                response = await self._curl.get(
                    url,
                    params=params,
                    headers=merged_headers,
                    cookies=self.cookies,
                    timeout=15.0,
                )
            except Exception:
                # curl_cffi surfaces timeouts/network blips as generic errors
                # and has no implicit timeout guard -- treat like a retryable
                # stall, mirroring _graphql_post.
                if attempt < settings.SCRAPER_MAX_RETRIES:
                    wait_s = min(_BACKOFF_BASE_S * (2 ** attempt), _BACKOFF_MAX_S)
                    wait_s += random.uniform(0, wait_s * 0.2)
                    await asyncio.sleep(wait_s)
                    continue
                raise ScraperTimeoutError(handle=handle)

            if response.status_code == 429:
                retry_after_header = response.headers.get("Retry-After")
                last_retry_after = int(retry_after_header) if retry_after_header else None
                if attempt < settings.SCRAPER_MAX_RETRIES:
                    wait_s = last_retry_after if last_retry_after else min(
                        _BACKOFF_BASE_S * (2 ** attempt), _BACKOFF_MAX_S
                    )
                    wait_s += random.uniform(0, wait_s * 0.2)  # jitter
                    await asyncio.sleep(wait_s)
                    continue
                raise ScraperRateLimitError(handle=handle, retry_after=last_retry_after)
            elif response.status_code in (401, 403):
                raise ScraperBlockedError(handle=handle)
            elif response.status_code >= 500:
                # Transient on Instagram's end -- retry rather than let
                # raise_for_status() below kill the job outright.
                if attempt < settings.SCRAPER_MAX_RETRIES:
                    wait_s = min(_BACKOFF_BASE_S * (2 ** attempt), _BACKOFF_MAX_S)
                    wait_s += random.uniform(0, wait_s * 0.2)
                    await asyncio.sleep(wait_s)
                    continue
                raise ScraperTimeoutError(handle=handle)

            response.raise_for_status()
            payload = response.json()
            if isinstance(payload, dict) and payload.get("status") not in (None, "ok"):
                if _is_checkpoint_response(payload):
                    # Instagram 200s a checkpoint_required/login_required
                    # body instead of erroring -- indistinguishable from a
                    # real success by status code alone. Left unchecked,
                    # this reads as "0 items" (empty feed) or "0 followers"
                    # (empty user), both of which silently write corrupt
                    # data rather than surfacing the account as blocked.
                    logger.warning(
                        "Instagram response reported a checkpoint",
                        handle=handle,
                        url=url,
                        message=payload.get("message"),
                    )
                    raise ScraperBlockedError(handle=handle)
                # A non-checkpoint "fail" (soft spam/feedback throttle,
                # transient hiccup) -- retry like a 429 instead of parking
                # a perfectly healthy session in checkpoint_required for
                # something that would have cleared on its own with a
                # cooldown. This was the actual bug: every non-"ok" status
                # was being treated as an unrecoverable checkpoint, so a
                # session that "works absolutely fine" kept getting flagged
                # as needing manual resolution on the first soft throttle
                # any single request happened to hit.
                logger.warning(
                    "Instagram response reported a non-ok, non-checkpoint status",
                    handle=handle,
                    url=url,
                    status=payload.get("status"),
                    message=payload.get("message"),
                )
                if attempt < settings.SCRAPER_MAX_RETRIES:
                    wait_s = min(_BACKOFF_BASE_S * (2 ** attempt), _BACKOFF_MAX_S)
                    wait_s += random.uniform(0, wait_s * 0.2)
                    await asyncio.sleep(wait_s)
                    continue
                raise ScraperRateLimitError(handle=handle)
            return payload
        raise ScraperTimeoutError(handle=handle)

    async def get_user_info(self, username: str) -> dict[str, Any]:
        """Fetch user profile via the public web endpoint.

        The mobile private API (i.instagram.com) rejects browser-extracted
        session cookies with a checkpoint_required error since it expects a
        signed mobile app session. web_profile_info accepts the same web
        cookies (plus X-IG-App-ID) and returns equivalent profile fields.
        """
        user: dict[str, Any] = {}
        for attempt in range(settings.SCRAPER_MAX_RETRIES + 1):
            payload = await self._get(
                "https://www.instagram.com/api/v1/users/web_profile_info/",
                params={"username": username},
                headers={"X-IG-App-ID": "936619743392459"},
                handle=username,
            )
            user = payload.get("data", {}).get("user") or {}
            if user:
                break
            # A "status": "ok" body with no user object usually means a
            # deactivated/removed account, but can also be a transient
            # blip on this specific endpoint -- retry a couple of times
            # (same as any other soft-fail path) before concluding the
            # account actually needs attention, rather than treating the
            # first empty response as blocked.
            if attempt < settings.SCRAPER_MAX_RETRIES:
                wait_s = min(_BACKOFF_BASE_S * (2 ** attempt), _BACKOFF_MAX_S)
                wait_s += random.uniform(0, wait_s * 0.2)
                await asyncio.sleep(wait_s)
        if not user:
            raise ScraperBlockedError(handle=username)
        return {
            "user": {
                "pk": user.get("id", ""),
                "username": user.get("username", ""),
                "full_name": user.get("full_name", ""),
                "is_private": user.get("is_private", False),
                "profile_pic_url": user.get("profile_pic_url", ""),
                "follower_count": user.get("edge_followed_by", {}).get("count", 0),
                "following_count": user.get("edge_follow", {}).get("count", 0),
                "media_count": user.get("edge_owner_to_timeline_media", {}).get("count", 0),
                "biography": user.get("biography", ""),
                "biography_with_entities": user.get("biography_with_entities"),
                "bio_links": user.get("bio_links", []),
                "pronouns": user.get("pronouns", []),
                "external_url": user.get("external_url"),
                "is_verified": user.get("is_verified", False),
                "is_business_account": user.get("is_business_account", False),
                "is_professional_account": user.get("is_professional_account", False),
                "category_name": user.get("category_name"),
                "category_enum": user.get("category_enum"),
                "overall_category_name": user.get("overall_category_name"),
                "business_contact_method": user.get("business_contact_method"),
                "business_email": user.get("business_email"),
                "business_phone_number": user.get("business_phone_number"),
                "highlight_reel_count": user.get("highlight_reel_count", 0),
                "has_clips": user.get("has_clips", False),
                "has_guides": user.get("has_guides", False),
                "has_channel": user.get("has_channel", False),
                "mutual_followers_count": user.get("edge_mutual_followed_by", {}).get("count", 0),
                "is_verified_by_mv4b": user.get("is_verified_by_mv4b", False),
                "hide_like_and_view_counts": user.get("hide_like_and_view_counts", False),
                "has_ar_effects": user.get("has_ar_effects", False),
                "business_category_name": user.get("business_category_name"),
            }
        }

    async def get_user_feed(self, username: str, max_id: str = "") -> dict[str, Any]:
        """Fetch paginated posts for a user via the public web endpoint.

        Same reasoning as get_user_info: the mobile private API
        (i.instagram.com/api/v1/feed/user/{pk}/) requires a signed app
        session and checkpoint-blocks browser cookies. The web-hosted,
        username-keyed equivalent accepts the same session cookies and
        returns items in the same shape.

        count=33 (this endpoint's practical max) rather than the UI's own
        12 -- request pacing is the actual throughput bottleneck (see
        TokenBucketRateLimiter), so fewer, larger pages beats more, smaller
        ones for the same amount of feed history.
        """
        params: dict[str, Any] = {"count": 33}
        if max_id:
            params["max_id"] = max_id
        return await self._get(
            f"https://www.instagram.com/api/v1/feed/user/{username}/username/",
            params=params,
            headers={"X-IG-App-ID": "936619743392459"},
            handle=username,
        )

    async def get_media_comments(self, media_pk: str, permalink: str, after: str | None = None) -> dict[str, Any]:
        """Fetch a page of top-level comments via the real web GraphQL query
        Instagram's own frontend uses (PolarisPostCommentsPaginationQuery).

        first=50 (vs. the UI's own first=10) trades a slightly larger
        response per call for far fewer round trips over a post's full
        comment history -- fewer requests per unit of data is the actual
        performance lever here, not raw concurrency, since request pacing
        is deliberately kept polite to avoid tripping Instagram's
        anti-automation detection.

        sort_order="chronological" (not the UI default "popular") so
        pagination walks every comment exactly once in a stable order,
        instead of "popular" ranking reshuffling under paginated traversal.
        """
        variables = {
            "after": after,
            "before": None,
            "first": 50,
            "last": None,
            "media_id": media_pk,
            "sort_order": "chronological",
            "__relay_internal__pv__PolarisIsLoggedInrelayprovider": True,
        }
        payload = await self._graphql_post(_COMMENTS_QUERY, _COMMENTS_DOC_ID, variables, referer=permalink)
        connection = payload.get("data", {}).get("xdt_api__v1__media__media_id__comments__connection") or {}
        return connection

    async def get_comment_replies(
        self, media_pk: str, comment_pk: str, permalink: str, after: str | None = None
    ) -> dict[str, Any]:
        """Fetch replies to a single top-level comment (PolarisPostChildCommentsQuery).

        first=None mirrors what the real UI sends -- Instagram returns the
        full reply thread in one call for the vast majority of comments, so
        the pagination loop around this is a safety net for the rare
        very-long thread, not the common case.
        """
        variables = {
            "after": after,
            "before": None,
            "media_id": media_pk,
            "parent_comment_id": comment_pk,
            "is_chronological": None,
            "first": None,
            "last": None,
            "__relay_internal__pv__PolarisIsLoggedInrelayprovider": True,
        }
        payload = await self._graphql_post(_REPLIES_QUERY, _REPLIES_DOC_ID, variables, referer=permalink)
        connection = (
            payload.get("data", {}).get(
                "xdt_api__v1__media__media_id__comments__parent_comment_id__child_comments__connection"
            )
            or {}
        )
        return connection

    async def close(self):
        await self._curl.close()
