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
            }
        }

    async def get_user_feed(self, user_id: str, max_id: str = "") -> dict[str, Any]:
        """Fetch paginated posts for a user."""
        endpoint = f"/feed/user/{user_id}/?count=12"
        if max_id:
            endpoint += f"&max_id={max_id}"
        return await self._request(endpoint, handle=user_id)

    async def close(self):
        await self.client.aclose()
