import asyncio
import json
import random
import re
import httpx
from typing import Any

from curl_cffi.requests import AsyncSession as CurlAsyncSession

from app.core.config import settings
from app.core.exceptions import ScraperRateLimitError, ScraperBlockedError, ScraperTimeoutError

_BACKOFF_BASE_S = 5.0
_BACKOFF_MAX_S = 120.0

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


class InstagramClient:
    BASE_URL = "https://i.instagram.com/api/v1"

    def __init__(self, cookies: dict[str, str], user_agent: str):
        self.headers = {
            "User-Agent": user_agent,
            "Accept-Language": "en-US",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        }
        self.cookies = cookies

        self.client = httpx.AsyncClient(
            base_url=self.BASE_URL,
            headers=self.headers,
            cookies=self.cookies,
            timeout=15.0,
            follow_redirects=True,
        )

        # Instagram's GraphQL endpoint (used for comments/replies) fingerprints
        # the TLS handshake itself (JA3/JA4) and silently routes anything that
        # doesn't match a real browser to the SPA shell instead of an error --
        # httpx's TLS stack fails this regardless of how correct the request
        # fields are. curl_cffi reproduces Chrome's exact fingerprint via
        # curl-impersonate, which is far cheaper than driving a real browser
        # per request and is what makes comment sync viable at scale.
        self._curl = CurlAsyncSession(impersonate="chrome124")
        self._fb_dtsg: str | None = None
        self._lsd: str | None = None
        self._token_lock = asyncio.Lock()

    @classmethod
    def from_account(cls, account, cookies: dict[str, str]) -> "InstagramClient":
        """Convenience constructor for an InstagramAccount pool row."""
        return cls(cookies=cookies, user_agent=account.user_agent)

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
                response = await self.client.get("https://www.instagram.com/")
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

            try:
                return response.json()
            except Exception:
                if attempt < settings.SCRAPER_MAX_RETRIES:
                    await self._ensure_csrf_tokens(force=True)
                    continue
                raise
        raise ScraperTimeoutError(handle=handle)

    async def _get(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        handle: str = "",
    ) -> dict[str, Any]:
        """GET with 429/timeout backoff. 401/403 surface immediately (never
        retried in-loop -- a blocked session retrying itself is pointless,
        and the caller needs it to surface right away so the account pool
        can mark the account for review)."""
        last_retry_after: int | None = None
        for attempt in range(settings.SCRAPER_MAX_RETRIES + 1):
            try:
                response = await self.client.get(url, params=params, headers=headers)
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

                response.raise_for_status()
                return response.json()
            except httpx.TimeoutException:
                if attempt < settings.SCRAPER_MAX_RETRIES:
                    wait_s = min(_BACKOFF_BASE_S * (2 ** attempt), _BACKOFF_MAX_S)
                    wait_s += random.uniform(0, wait_s * 0.2)
                    await asyncio.sleep(wait_s)
                    continue
                raise ScraperTimeoutError(handle=handle)
        raise ScraperTimeoutError(handle=handle)

    async def get_user_info(self, username: str) -> dict[str, Any]:
        """Fetch user profile via the public web endpoint.

        The mobile private API (i.instagram.com) rejects browser-extracted
        session cookies with a checkpoint_required error since it expects a
        signed mobile app session. web_profile_info accepts the same web
        cookies (plus X-IG-App-ID) and returns equivalent profile fields.
        """
        payload = await self._get(
            "https://www.instagram.com/api/v1/users/web_profile_info/",
            params={"username": username},
            headers={"X-IG-App-ID": "936619743392459"},
            handle=username,
        )
        user = payload.get("data", {}).get("user") or {}
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
        """
        params: dict[str, Any] = {"count": 12}
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
        await self.client.aclose()
        await self._curl.close()
