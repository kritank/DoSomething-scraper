import httpx
from typing import Any

from app.core.config import settings
from app.core.exceptions import ScraperRateLimitError, ScraperBlockedError, ScraperTimeoutError


class InstagramClient:
    BASE_URL = "https://i.instagram.com/api/v1"
    
    def __init__(self):
        # We need a proper user agent and headers to mimic the app
        self.headers = {
            "User-Agent": "Instagram 219.0.0.12.117 Android",
            "Accept-Language": "en-US",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        }
        self.cookies = settings.instagram_cookies
        
        self.client = httpx.AsyncClient(
            base_url=self.BASE_URL,
            headers=self.headers,
            cookies=self.cookies,
            timeout=15.0,
            follow_redirects=True,
        )

    async def _request(self, endpoint: str, handle: str = "") -> dict[str, Any]:
        try:
            response = await self.client.get(endpoint)
            if response.status_code == 429:
                retry_after = int(response.headers.get("Retry-After", 60))
                raise ScraperRateLimitError(handle=handle, retry_after=retry_after)
            elif response.status_code in (401, 403):
                raise ScraperBlockedError(handle=handle)
            
            response.raise_for_status()
            return response.json()
        except httpx.TimeoutException:
            raise ScraperTimeoutError(handle=handle)

    async def get_user_info(self, username: str) -> dict[str, Any]:
        """Fetch user profile via the public web endpoint.

        The mobile private API (i.instagram.com) rejects browser-extracted
        session cookies with a checkpoint_required error since it expects a
        signed mobile app session. web_profile_info accepts the same web
        cookies (plus X-IG-App-ID) and returns equivalent profile fields.
        """
        response = await self.client.get(
            "https://www.instagram.com/api/v1/users/web_profile_info/",
            params={"username": username},
            headers={"X-IG-App-ID": "936619743392459"},
        )
        response.raise_for_status()
        payload = response.json()
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
        response = await self.client.get(
            f"https://www.instagram.com/api/v1/feed/user/{username}/username/",
            params=params,
            headers={"X-IG-App-ID": "936619743392459"},
        )
        response.raise_for_status()
        return response.json()

    async def get_media_comments(self, media_pk: str, min_id: str = "") -> dict[str, Any]:
        """Fetch a page of top-level comments for a post via the web endpoint.

        can_support_threading=true is required -- without it Instagram
        silently returns child_comment_count as null on every comment,
        hiding the fact that reply threads exist at all.
        """
        params: dict[str, Any] = {"can_support_threading": "true"}
        if min_id:
            params["min_id"] = min_id
        response = await self.client.get(
            f"https://www.instagram.com/api/v1/media/{media_pk}/comments/",
            params=params,
            headers={"X-IG-App-ID": "936619743392459"},
        )
        response.raise_for_status()
        return response.json()

    async def get_comment_replies(self, media_pk: str, comment_pk: str, min_child_cursor: str = "") -> dict[str, Any]:
        """Fetch a page of replies to a single top-level comment."""
        params: dict[str, Any] = {}
        if min_child_cursor:
            params["min_child_cursor"] = min_child_cursor
        response = await self.client.get(
            f"https://www.instagram.com/api/v1/media/{media_pk}/comments/{comment_pk}/child_comments/",
            params=params,
            headers={"X-IG-App-ID": "936619743392459"},
        )
        response.raise_for_status()
        return response.json()

    async def close(self):
        await self.client.aclose()
