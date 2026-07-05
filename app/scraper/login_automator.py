from __future__ import annotations
"""
Programmatic Instagram login via Playwright.

Used only by scripts/register_instagram_account.py to provision the account
pool -- this is the one place in the codebase that drives a real browser
against Instagram, and the one place stealth measures matter (all other
scraping replays Instagram's own JSON endpoints via plain httpx, see
app/scraper/client.py).

Instagram's login path is watched far more closely than its read endpoints.
2FA prompts and "suspicious login" checkpoints cannot be solved here --
solving an OTP requires an out-of-band human/SMS/email step. When one is
detected we bail out immediately with status="checkpoint_required" rather
than looping or guessing; the operator has to complete it manually (log in
through a real browser once) and re-run the registration script.
"""

import asyncio
import random
from dataclasses import dataclass
from typing import Literal

from playwright.async_api import async_playwright, Page
from playwright_stealth import Stealth

from app.core.logging import get_logger
from app.scraper.user_agents import random_viewport

logger = get_logger(__name__)

LOGIN_URL = "https://www.instagram.com/accounts/login/"

_CHECKPOINT_URL_MARKERS = (
    "/challenge/",
    "/accounts/login/two_factor",
    "/two_factor",
    "/auth_platform/recaptcha/",
)
_CHECKPOINT_TEXT_MARKERS = (
    "suspicious login",
    "we detected an unusual login attempt",
    "enter the code",
    "enter the 6-digit code",
    "confirm it's you",
    "help us confirm",
)
_BAD_CREDENTIAL_TEXT_MARKERS = (
    "sorry, your password was incorrect",
    "the password you entered is incorrect",
    "couldn't find your account",
    "unable to find your account",
)

_NAV_TIMEOUT_MS = 30_000
_LAUNCH_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--no-sandbox",
    "--disable-dev-shm-usage",
    "--disable-extensions",
    "--disable-infobars",
    "--disable-gpu",
]


@dataclass(frozen=True)
class LoginResult:
    status: Literal["success", "checkpoint_required", "bad_credentials", "unknown_failure"]
    cookies: list[dict] | None = None
    detail: str | None = None


async def _human_delay(min_s: float = 0.4, max_s: float = 1.2) -> None:
    await asyncio.sleep(random.uniform(min_s, max_s))


async def _type_like_human(page: Page, selector: str, text: str) -> None:
    await page.click(selector)
    await page.type(selector, text, delay=random.uniform(60, 160))


def _classify_page(page: Page, body_text: str) -> tuple[str, str] | None:
    """Return (status, detail) if the page matches a terminal, non-success
    state; None if it looks like a plain success (caller decides)."""
    url = page.url
    lowered = body_text.lower()

    if any(marker in url for marker in _CHECKPOINT_URL_MARKERS) or any(
        marker in lowered for marker in _CHECKPOINT_TEXT_MARKERS
    ):
        return "checkpoint_required", f"challenge detected at {url}"

    if any(marker in lowered for marker in _BAD_CREDENTIAL_TEXT_MARKERS):
        return "bad_credentials", "incorrect username or password"

    return None


async def perform_login(
    username: str,
    password: str,
    user_agent: str,
    locale: str,
    timezone: str,
    headless: bool = True,
) -> LoginResult:
    async with Stealth().use_async(async_playwright()) as p:
        browser = await p.chromium.launch(headless=headless, args=_LAUNCH_ARGS)
        context = await browser.new_context(
            user_agent=user_agent,
            locale=locale,
            timezone_id=timezone,
            viewport=random_viewport(),
        )
        try:
            page = await context.new_page()
            page.set_default_timeout(_NAV_TIMEOUT_MS)

            await page.goto(LOGIN_URL, wait_until="domcontentloaded")
            await _human_delay(1.0, 2.5)  # let the page settle before interacting

            try:
                await page.click('button:has-text("Allow all cookies")', timeout=3_000)
                await _human_delay()
            except Exception:
                pass  # cookie banner not shown -- fine

            await _type_like_human(page, 'input[name="email"]', username)
            await _human_delay()
            await _type_like_human(page, 'input[name="pass"]', password)
            await _human_delay()

            # The submit control renders as a locale-dependent `div[role=button]`
            # rather than a native <button>, so press Enter instead of clicking it.
            await page.press('input[name="pass"]', "Enter")

            try:
                await page.wait_for_load_state("networkidle", timeout=_NAV_TIMEOUT_MS)
            except Exception:
                pass  # Instagram's SPA navigation doesn't always settle to idle; fall through to classification

            await _human_delay(1.0, 2.0)  # settle delay before reading page state

            body_text = await page.inner_text("body")
            terminal = _classify_page(page, body_text)
            if terminal is not None:
                status, detail = terminal
                logger.warning("Instagram login did not succeed", username=username, status=status, detail=detail)
                return LoginResult(status=status, detail=detail)  # type: ignore[arg-type]

            if "/accounts/login" in page.url:
                # Still on the login page with no recognized error -- treat
                # conservatively rather than guessing.
                return LoginResult(status="unknown_failure", detail=f"still on login page: {page.url}")

            cookies = await context.cookies()
            logger.info("Instagram login succeeded", username=username)
            return LoginResult(status="success", cookies=cookies)
        except Exception as e:
            logger.exception("Instagram login raised an unexpected error", username=username)
            return LoginResult(status="unknown_failure", detail=str(e))
        finally:
            await context.close()
            await browser.close()
