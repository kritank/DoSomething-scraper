from __future__ import annotations
"""
Register an Instagram account into the pool by logging in through a real
(Playwright-driven) browser session and persisting the resulting cookies.

Replaces the old flow of manually extracting sessionid/csrftoken/ds_user_id
from browser devtools and pasting them into .env -- run this once per
account instead.

Usage:
    uv run python scripts/register_instagram_account.py --username myaccount
    (prompts for password)

If Instagram challenges the login with 2FA/a "suspicious login" checkpoint,
this script CANNOT solve it -- log in manually via a real browser to clear
the checkpoint, then re-run this script.

Alternatively, if you already have an active, logged-in Instagram session in
your own browser (e.g. because the automated login above got stuck behind a
checkpoint), register directly from its cookies instead of driving a new
login:
    uv run python scripts/register_instagram_account.py --username myaccount --from-cookies
    (prompts for sessionid/csrftoken/ds_user_id/ig_did, extracted from your
    browser's devtools -- Application/Storage > Cookies > instagram.com)
"""

import argparse
import asyncio
import getpass

from app.core.config import settings
from app.core.database import get_session
from app.repositories.instagram_account_repo import InstagramAccountRepo
from app.scraper.login_automator import perform_login
from app.scraper.user_agents import next_locale_timezone_profile, pick_user_agent


async def register(
    username: str, password: str, locale: str | None, tz: str | None, headless: bool,
    proxy: str | None,
) -> int:
    if locale is None or tz is None:
        locale, tz = next_locale_timezone_profile()
    user_agent = pick_user_agent()

    print(f"Logging in as @{username} (locale={locale}, tz={tz}, headless={headless}, proxy={'set' if proxy else 'none'})...")
    result = await perform_login(
        username=username,
        password=password,
        user_agent=user_agent,
        locale=locale,
        timezone=tz,
        headless=headless,
        proxy=proxy,
    )

    async with get_session() as session:
        repo = InstagramAccountRepo(session)

        if result.status == "success":
            cookies = {c["name"]: c["value"] for c in (result.cookies or [])}
            await repo.create(
                username=username,
                cookies=cookies,
                user_agent=user_agent,
                locale=locale,
                tz=tz,
                proxy=proxy,
            )
            print(f"Registered @{username} -- account is active and available to the scrape pool.")
            return 0

        if result.status == "checkpoint_required":
            await repo.create_checkpoint_required(
                username=username, user_agent=user_agent, locale=locale, tz=tz,
                detail=result.detail or "", proxy=proxy,
            )
            print(
                f"@{username} requires manual verification (2FA/checkpoint): {result.detail}\n"
                "Log in manually in a real browser to clear it, then re-run this script."
            )
            return 1

        print(f"Login failed for @{username}: {result.status} -- {result.detail}")
        return 1


async def register_from_cookies(
    username: str, cookies: dict[str, str], locale: str | None, tz: str | None,
    proxy: str | None,
) -> int:
    if locale is None or tz is None:
        locale, tz = next_locale_timezone_profile()
    user_agent = pick_user_agent()

    async with get_session() as session:
        repo = InstagramAccountRepo(session)
        await repo.create(username=username, cookies=cookies, user_agent=user_agent, locale=locale, tz=tz, proxy=proxy)
    print(f"Registered @{username} from existing session cookies -- account is active and available to the scrape pool.")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Register an Instagram account into the scraper's account pool.")
    parser.add_argument("--username", required=True)
    parser.add_argument(
        "--password",
        default=None,
        help="Prefer omitting this and using the password prompt -- avoids it landing in shell history.",
    )
    parser.add_argument(
        "--from-cookies",
        action="store_true",
        help="Skip the automated login and register from an existing browser session's cookies instead "
        "(prompts for sessionid/csrftoken/ds_user_id/ig_did).",
    )
    parser.add_argument("--locale", default=None)
    parser.add_argument("--timezone", default=None, dest="tz")
    parser.add_argument(
        "--proxy",
        default=None,
        help="Pin this account to an egress proxy (scheme://[user:pass@]host:port). "
        "Strongly recommended: use a sticky residential/mobile proxy so login and all "
        "scraping share one IP, avoiding Instagram's checkpoint on IP mismatch. "
        "On a re-register without --proxy, any existing proxy is kept.",
    )
    headless_group = parser.add_mutually_exclusive_group()
    headless_group.add_argument("--headless", action="store_true", dest="headless", default=None)
    headless_group.add_argument("--no-headless", action="store_false", dest="headless")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.from_cookies:
        sessionid = getpass.getpass("sessionid: ").strip()
        csrftoken = getpass.getpass("csrftoken: ").strip()
        ds_user_id = getpass.getpass("ds_user_id: ").strip()
        ig_did = getpass.getpass("ig_did (optional, press enter to skip): ").strip()

        cookies = {"sessionid": sessionid, "csrftoken": csrftoken, "ds_user_id": ds_user_id}
        if ig_did:
            cookies["ig_did"] = ig_did

        missing = [name for name in ("sessionid", "csrftoken", "ds_user_id") if not cookies[name]]
        if missing:
            raise SystemExit(f"Missing required cookie value(s): {', '.join(missing)}")

        exit_code = asyncio.run(register_from_cookies(args.username, cookies, args.locale, args.tz, args.proxy))
        raise SystemExit(exit_code)

    password = args.password or getpass.getpass(f"Instagram password for @{args.username}: ")
    headless = args.headless if args.headless is not None else settings.SCRAPER_HEADLESS
    exit_code = asyncio.run(register(args.username, password, args.locale, args.tz, headless, args.proxy))
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
