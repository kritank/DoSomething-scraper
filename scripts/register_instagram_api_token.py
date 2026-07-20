from __future__ import annotations
"""
Register an Instagram Graph API (Business Discovery) credential into the
pool used by InstagramGraphJobProcessor (PR2+). See
docs/INSTAGRAM_GRAPH_API_PLAN.md §3 for the human setup steps this assumes
have already happened (professional "reader" IG account, linked Facebook
Page, Meta app with instagram_basic/instagram_manage_insights/
pages_show_list/pages_read_engagement granted).

For the "facebook_login" flavor (the recommended one -- guaranteed Business
Discovery support), this script does the token-exchange dance for you:
1. Takes the short-lived User token straight out of Graph API Explorer.
2. Exchanges it for a long-lived User token (~60 days).
3. Resolves the Page access token via GET /me/accounts -- this is what
   actually gets stored and used for Business Discovery calls; Page tokens
   derived this way don't expire (confirmed via GET /debug_token during
   Phase 0.5 verification: type=PAGE, expires_at=0), so token_expires_at
   is left null for this flavor.
4. Resolves the IG User ID from the token's own granted scopes (GET
   /debug_token's granular_scopes[instagram_basic].target_ids) rather than
   GET /{page-id}?fields=instagram_business_account -- confirmed live that
   the latter 400s without pages_read_engagement even though Business
   Discovery itself works fine without it, so this avoids an unnecessary
   permission dependency.
5. Validates the resulting Page token with one live, free Business
   Discovery call (business_discovery.username(instagram)) before
   persisting -- a bad/under-scoped token fails here, not on the first
   real job.

For "instagram_login", this script expects you to already have the final
long-lived token and IG User ID from the app dashboard's own token
generator (see plan §3 step 4, flavor 2) -- no exchange dance needed there.

Usage:
    uv run python scripts/register_instagram_api_token.py --label reader-1
    (prompts for flavor, app id/secret, and the token)
"""

import argparse
import asyncio
import getpass

import httpx

from app.core.database import get_session
from app.repositories.instagram_api_token_repo import InstagramApiTokenRepo

GRAPH_BASE = "https://graph.facebook.com/v25.0"
REQUIRED_SCOPES = {"instagram_basic", "instagram_manage_insights", "pages_show_list"}


async def _debug_token(input_token: str, app_id: str, app_secret: str) -> dict:
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(
            "https://graph.facebook.com/debug_token",
            params={"input_token": input_token, "access_token": f"{app_id}|{app_secret}"},
        )
    response.raise_for_status()
    return response.json().get("data", {})


async def _exchange_long_lived(short_token: str, app_id: str, app_secret: str) -> str:
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(
            f"{GRAPH_BASE}/oauth/access_token",
            params={
                "grant_type": "fb_exchange_token",
                "client_id": app_id,
                "client_secret": app_secret,
                "fb_exchange_token": short_token,
            },
        )
    response.raise_for_status()
    return response.json()["access_token"]


async def _resolve_page_token(long_lived_user_token: str) -> tuple[str, str]:
    """Returns (page_id, page_access_token) for the first (and expected
    only, for a single reader account) Page this user token manages."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(
            f"{GRAPH_BASE}/me/accounts", params={"access_token": long_lived_user_token}
        )
    response.raise_for_status()
    pages = response.json().get("data", [])
    if not pages:
        raise RuntimeError(
            "This token manages no Facebook Pages -- confirm the reader IG account is linked "
            "to a Facebook Page (plan §3 step 2) and that pages_show_list was granted."
        )
    page = pages[0]
    return page["id"], page["access_token"]


def _resolve_ig_user_id(debug_data: dict) -> str:
    for scope in debug_data.get("granular_scopes", []):
        if scope.get("scope") == "instagram_basic":
            target_ids = scope.get("target_ids", [])
            if target_ids:
                return target_ids[0]
    raise RuntimeError(
        "Could not resolve an IG User ID from this token's granted scopes -- "
        "confirm instagram_basic was granted and the reader account is a professional account."
    )


async def _validate_business_discovery(ig_user_id: str, access_token: str) -> tuple[bool, str]:
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            response = await client.get(
                f"{GRAPH_BASE}/{ig_user_id}",
                params={
                    "fields": "business_discovery.username(instagram){username,followers_count}",
                    "access_token": access_token,
                },
            )
        except Exception as e:
            return False, f"Network error while validating: {e}"
    if response.status_code == 200 and "business_discovery" in response.json():
        return True, ""
    try:
        detail = response.json().get("error", {}).get("message", response.text)
    except Exception:
        detail = response.text
    return False, f"HTTP {response.status_code}: {detail}"


async def register_facebook_login(label: str, app_id: str, app_secret: str, short_token: str) -> int:
    print("Checking token scopes...")
    debug_data = await _debug_token(short_token, app_id, app_secret)
    granted = set(debug_data.get("scopes", []))
    missing = REQUIRED_SCOPES - granted
    if missing:
        print(f"Missing required scopes: {sorted(missing)}. Regenerate the token in Graph API Explorer with these included.")
        return 1

    print("Resolving IG User ID from granted scopes...")
    ig_user_id = _resolve_ig_user_id(debug_data)
    print(f"IG User ID: {ig_user_id}")

    print("Exchanging for a long-lived token...")
    long_lived = await _exchange_long_lived(short_token, app_id, app_secret)

    print("Resolving Page access token (non-expiring)...")
    page_id, page_token = await _resolve_page_token(long_lived)
    print(f"Page ID: {page_id}")

    print("Validating with a live Business Discovery call...")
    ok, detail = await _validate_business_discovery(ig_user_id, page_token)
    if not ok:
        print(f"Validation failed: {detail}")
        return 1

    async with get_session() as session:
        await InstagramApiTokenRepo(session).create(
            label=label,
            access_token=page_token,
            ig_user_id=ig_user_id,
            app_id=app_id,
            app_secret=app_secret,
            auth_flavor="facebook_login",
            token_expires_at=None,  # Page tokens derived this way don't expire
        )
    print(f"Registered Instagram API token '{label}' -- active and available to the scrape pool.")
    return 0


async def register_instagram_login(label: str, app_id: str, app_secret: str, token: str, ig_user_id: str) -> int:
    print("Validating with a live Business Discovery call...")
    ok, detail = await _validate_business_discovery(ig_user_id, token)
    if not ok:
        print(f"Validation failed: {detail}")
        return 1

    from datetime import datetime, timedelta, timezone

    async with get_session() as session:
        await InstagramApiTokenRepo(session).create(
            label=label,
            access_token=token,
            ig_user_id=ig_user_id,
            app_id=app_id,
            app_secret=app_secret,
            auth_flavor="instagram_login",
            token_expires_at=datetime.now(timezone.utc) + timedelta(days=60),
        )
    print(f"Registered Instagram API token '{label}' -- active and available to the scrape pool.")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Register an Instagram Graph API token into the pool.")
    parser.add_argument("--label", required=True, help="Human-readable name, e.g. the reader account's handle.")
    parser.add_argument("--flavor", choices=["facebook_login", "instagram_login"], default="facebook_login")
    parser.add_argument("--app-id", required=True)
    parser.add_argument("--app-secret", default=None, help="Prefer omitting this and using the prompt.")
    parser.add_argument("--token", default=None, help="Prefer omitting this and using the prompt.")
    parser.add_argument(
        "--ig-user-id",
        default=None,
        help="Only used/required for --flavor instagram_login (facebook_login resolves it automatically).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    app_secret = args.app_secret or getpass.getpass("Meta app secret: ").strip()
    token = args.token or getpass.getpass("Access token: ").strip()
    if not app_secret or not token:
        raise SystemExit("App secret and token are both required.")

    if args.flavor == "facebook_login":
        exit_code = asyncio.run(register_facebook_login(args.label, args.app_id, app_secret, token))
    else:
        if not args.ig_user_id:
            raise SystemExit("--ig-user-id is required for --flavor instagram_login.")
        exit_code = asyncio.run(
            register_instagram_login(args.label, args.app_id, app_secret, token, args.ig_user_id)
        )
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
