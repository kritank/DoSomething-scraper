from __future__ import annotations
"""
User-agent and locale/timezone assignment for the Instagram account pool.

A UA and a locale/timezone pair are assigned ONCE per account, at registration
time, and then persisted (InstagramAccount.user_agent/locale/timezone) --
never rotated per-request. Rotating fingerprints mid-session under an already
established session is itself a bot-detection tell; consistency over the
account's lifetime is the point.
"""

import itertools
import random

from app.core.logging import get_logger

logger = get_logger(__name__)

# Used only if fake-useragent's remote data fetch fails (a known occasional
# failure mode of that library -- shouldn't block account registration).
_FALLBACK_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0",
]

# Matched locale/timezone pairs -- deliberately kept small and internally
# consistent (don't send en-US with a European timezone).
LOCALE_TIMEZONE_PROFILES: list[tuple[str, str]] = [
    ("en-US", "America/New_York"),
    ("en-US", "America/Chicago"),
    ("en-US", "America/Los_Angeles"),
    ("en-GB", "Europe/London"),
    ("en-CA", "America/Toronto"),
    ("en-AU", "Australia/Sydney"),
]

_profile_cycle = itertools.cycle(LOCALE_TIMEZONE_PROFILES)


def pick_user_agent() -> str:
    """Return a realistic desktop User-Agent, falling back to a static list
    if fake-useragent's remote data source is unreachable."""
    try:
        from fake_useragent import UserAgent

        ua = UserAgent(platforms="desktop", browsers=["Chrome", "Firefox", "Edge"])
        return ua.random
    except Exception as e:
        logger.warning("fake-useragent unavailable, using fallback UA list", error=str(e))
        return random.choice(_FALLBACK_USER_AGENTS)


def next_locale_timezone_profile() -> tuple[str, str]:
    """Round-robin through the curated locale/timezone pairs so accounts in
    the pool don't all cluster on the same profile."""
    return next(_profile_cycle)


def random_viewport() -> dict[str, int]:
    return {"width": random.randint(1280, 1920), "height": random.randint(720, 1080)}
