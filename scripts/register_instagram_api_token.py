from __future__ import annotations
"""
Register an Instagram Graph API (Business Discovery) credential into the
pool used by InstagramGraphJobProcessor (PR2+). See
docs/INSTAGRAM_GRAPH_API_PLAN.md §3 for the human setup steps this assumes
have already happened (professional "reader" IG account, linked Facebook
Page, Meta app with instagram_basic/instagram_manage_insights/
pages_show_list/pages_read_engagement granted).

The actual exchange/validation logic lives in
app.services.instagram_token_service, shared with the dashboard's
POST /admin/instagram-tokens/* routes -- this script is just a thin CLI
wrapper (prompts for secrets, prints progress, exits non-zero on failure).

Usage:
    uv run python scripts/register_instagram_api_token.py --label reader-1
    (prompts for flavor, app id/secret, and the token)
"""

import argparse
import asyncio
import getpass

from app.core.database import get_session
from app.core.exceptions import InstagramApiTokenValidationError
from app.services.instagram_token_service import register_facebook_login, register_instagram_login


async def _register_facebook_login(label: str, app_id: str, app_secret: str, short_token: str) -> int:
    try:
        async with get_session() as session:
            await register_facebook_login(session, label, app_id, app_secret, short_token)
    except InstagramApiTokenValidationError as e:
        print(str(e))
        return 1
    print(f"Registered Instagram API token '{label}' -- active and available to the scrape pool.")
    return 0


async def _register_instagram_login(label: str, app_id: str, app_secret: str, token: str, ig_user_id: str) -> int:
    try:
        async with get_session() as session:
            await register_instagram_login(session, label, app_id, app_secret, token, ig_user_id)
    except InstagramApiTokenValidationError as e:
        print(str(e))
        return 1
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
        exit_code = asyncio.run(_register_facebook_login(args.label, args.app_id, app_secret, token))
    else:
        if not args.ig_user_id:
            raise SystemExit("--ig-user-id is required for --flavor instagram_login.")
        exit_code = asyncio.run(
            _register_instagram_login(args.label, args.app_id, app_secret, token, args.ig_user_id)
        )
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
