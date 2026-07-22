"""Shared Instagram Graph API token registration logic -- used by both
scripts/register_instagram_api_token.py (CLI) and the /admin/instagram-tokens
API routes (dashboard UI). See docs/INSTAGRAM_GRAPH_API_PLAN.md §3 for the
human setup steps this assumes have already happened (professional "reader"
IG account, linked Facebook Page, Meta app with instagram_basic/
instagram_manage_insights/pages_show_list/pages_read_engagement granted).

Raises InstagramApiTokenValidationError (never a bare httpx/RuntimeError) on
any failure, with a message safe to surface directly to an operator -- the
API layer turns this into a 400, the CLI script prints it and exits 1.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import InstagramApiTokenValidationError
from app.models.instagram_api_token import InstagramApiToken
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
        raise InstagramApiTokenValidationError(
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
    raise InstagramApiTokenValidationError(
        "Could not resolve an IG User ID from this token's granted scopes -- "
        "confirm instagram_basic was granted and the reader account is a professional account."
    )


async def _validate_business_discovery(ig_user_id: str, access_token: str) -> None:
    """Raises InstagramApiTokenValidationError on any non-success outcome
    -- callers should let this propagate rather than persisting a token
    that will only fail on its first real scrape."""
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
            raise InstagramApiTokenValidationError(f"Network error while validating: {e}") from e
    if response.status_code == 200 and "business_discovery" in response.json():
        return
    try:
        detail = response.json().get("error", {}).get("message", response.text)
    except Exception:
        detail = response.text
    raise InstagramApiTokenValidationError(f"Validation failed -- HTTP {response.status_code}: {detail}")


async def register_facebook_login(
    session: AsyncSession, label: str, app_id: str, app_secret: str, short_token: str
) -> InstagramApiToken:
    """Does the full token-exchange dance: checks scopes on the short-lived
    User token straight out of Graph API Explorer, exchanges it for a
    long-lived one, resolves the non-expiring Page token that actually
    gets stored/used, and validates it with a live Business Discovery call
    before persisting."""
    debug_data = await _debug_token(short_token, app_id, app_secret)
    granted = set(debug_data.get("scopes", []))
    missing = REQUIRED_SCOPES - granted
    if missing:
        raise InstagramApiTokenValidationError(
            f"Missing required scopes: {sorted(missing)}. "
            "Regenerate the token in Graph API Explorer with these included."
        )

    ig_user_id = _resolve_ig_user_id(debug_data)
    long_lived = await _exchange_long_lived(short_token, app_id, app_secret)
    _page_id, page_token = await _resolve_page_token(long_lived)
    await _validate_business_discovery(ig_user_id, page_token)

    return await InstagramApiTokenRepo(session).create(
        label=label,
        access_token=page_token,
        ig_user_id=ig_user_id,
        app_id=app_id,
        app_secret=app_secret,
        auth_flavor="facebook_login",
        token_expires_at=None,  # Page tokens derived this way don't expire
    )


async def register_instagram_login(
    session: AsyncSession, label: str, app_id: str, app_secret: str, token: str, ig_user_id: str
) -> InstagramApiToken:
    """instagram_login flavor: the caller already has the final long-lived
    token and IG User ID from the app dashboard's own token generator (plan
    §3 step 4, flavor 2) -- no exchange dance needed, just validation."""
    await _validate_business_discovery(ig_user_id, token)

    return await InstagramApiTokenRepo(session).create(
        label=label,
        access_token=token,
        ig_user_id=ig_user_id,
        app_id=app_id,
        app_secret=app_secret,
        auth_flavor="instagram_login",
        token_expires_at=datetime.now(timezone.utc) + timedelta(days=60),
    )
