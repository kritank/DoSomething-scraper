"""Reads the verification checkmark off youtube.com's public channel page.

The Data API (app/scraper/youtube_client.py) never exposes this -- see
docs/YOUTUBE_SCRAPER_DESIGN.md's "Data API doesn't expose the verification
badge" note -- so this is the only source of truth for it. Plain httpx (no
TLS impersonation, no cookies/login): this is a public, unauthenticated
page, same rationale YouTubeClient's own docstring gives for not needing
InstagramClient's anti-bot machinery.

The page embeds a `var ytInitialData = {...};` blob. A verified channel's
title carries an accessibility label ending in ", Verified"
(header.pageHeaderRenderer.content.pageHeaderViewModel.title
.dynamicTextViewModel.rendererContext.accessibilityContext.label); an
unverified channel has no accessibilityContext there at all. Confirmed
live against @mkbhd/@veritasium/@t3dotgg (verified) and a small real
channel with no subscribers to speak of (unverified, key simply absent).
"""
from __future__ import annotations

import json
import re

import httpx

from app.core.exceptions import YouTubeChannelPageError

_INITIAL_DATA_RE = re.compile(r"var ytInitialData = ({.*?});</script>")

# A real browser UA -- youtube.com's anti-bot heuristics are far lighter
# than Instagram's, but an obviously non-browser UA (httpx's default,
# "python-httpx/...") gets an empty/consent-wall response often enough to
# be worth avoiding.
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)


async def fetch_is_verified(handle: str | None = None, channel_id: str | None = None) -> bool:
    """Exactly one of handle/channel_id must be set -- same shape as
    YouTubeClient.get_channel. channel_id (stable) is preferred by callers
    over handle (renameable) when both are known."""
    if channel_id:
        url = f"https://www.youtube.com/channel/{channel_id}"
        target = channel_id
    else:
        normalized = handle or ""
        if not normalized.startswith("@"):
            normalized = f"@{normalized}"
        url = f"https://www.youtube.com/{normalized}"
        target = normalized

    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            response = await client.get(
                url,
                headers={"User-Agent": _USER_AGENT, "Accept-Language": "en-US"},
                follow_redirects=True,
            )
        except httpx.HTTPError as e:
            raise YouTubeChannelPageError(f"request failed ({e})", target=target) from e

    if response.status_code != 200:
        raise YouTubeChannelPageError(f"HTTP {response.status_code}", target=target)

    match = _INITIAL_DATA_RE.search(response.text)
    if not match:
        raise YouTubeChannelPageError("ytInitialData not found in page", target=target)

    try:
        data = json.loads(match.group(1))
    except json.JSONDecodeError as e:
        raise YouTubeChannelPageError(f"ytInitialData didn't parse as JSON ({e})", target=target) from e

    try:
        title = data["header"]["pageHeaderRenderer"]["content"]["pageHeaderViewModel"]["title"]
    except (KeyError, TypeError) as e:
        raise YouTubeChannelPageError(f"unexpected page header shape ({e})", target=target) from e

    label = (
        title.get("dynamicTextViewModel", {})
        .get("rendererContext", {})
        .get("accessibilityContext", {})
        .get("label", "")
    )
    return label.endswith(", Verified")
