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
        """Fetch user profile via mobile API endpoint."""
        endpoint = f"/users/{username}/usernameinfo/"
        return await self._request(endpoint, handle=username)

    async def get_user_feed(self, user_id: str, max_id: str = "") -> dict[str, Any]:
        """Fetch paginated posts for a user."""
        endpoint = f"/feed/user/{user_id}/?count=12"
        if max_id:
            endpoint += f"&max_id={max_id}"
        return await self._request(endpoint, handle=user_id)

    async def close(self):
        await self.client.aclose()
