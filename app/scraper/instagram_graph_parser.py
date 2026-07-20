"""Pure functions over Instagram Graph API (Business Discovery) responses --
no I/O, so these are unit-testable in isolation against captured fixtures
(tests/fixtures/instagram_graph/). Mirrors youtube_parser.py's shape:
callers (instagram_graph_client.py / the job processor) own the HTTP call,
these just turn a parsed JSON payload into the same normalized
InstagramUser/InstagramMediaItem shapes the cookie InstagramParser emits,
so persistence code is shared across both sources. See
docs/INSTAGRAM_HYBRID_IMPLEMENTATION.md §1.6 and
docs/INSTAGRAM_GRAPH_API_PLAN.md §6 (field mapping)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.schemas.instagram import InstagramMediaItem, InstagramUser

# Instagram Reels ("clips") are the only Graph API media_product_type that
# maps to the cookie parser's short-form convention -- matches
# creator_stats.content_format's _INSTAGRAM_SHORT_FORM_PRODUCT_TYPES
# ({"clips"}). Everything else (FEED, STORY -- though stories aren't
# returned by Business Discovery at all) stays None, same as a regular
# feed post's product_type from the cookie path.
_REELS_PRODUCT_TYPE = "clips"

# Cookie-parser numeric media_type convention (see InstagramParser) --
# Business Discovery returns these as strings instead, so this is the
# string->int bridge that keeps both sources writing the same column shape.
_MEDIA_TYPE_MAP = {
    "IMAGE": 1,
    "VIDEO": 2,
    "CAROUSEL_ALBUM": 8,
}


def _shortcode_from_permalink(permalink: str | None) -> str:
    """https://www.instagram.com/p/{shortcode}/ or /reel/{shortcode}/ ->
    shortcode. Empty string (never None) when permalink is missing/
    unparseable -- callers treat that as "couldn't resolve a shortcode for
    this item" rather than crashing on a None where a str is expected."""
    if not permalink:
        return ""
    parts = [p for p in permalink.rstrip("/").split("/") if p]
    return parts[-1] if parts else ""


def _parse_timestamp(raw: str | None) -> int:
    """Business Discovery's timestamp is ISO8601 with a bare +HHMM offset
    (e.g. "2026-07-18T09:36:51+0000") -- confirmed against a real fixture
    that datetime.fromisoformat REJECTS this exact format (it wants a colon
    in the offset), so this uses strptime's %z instead, which accepts both
    forms. Returns 0 (never None) for a missing/unparseable timestamp,
    matching InstagramMediaItem.taken_at's non-optional int contract."""
    if not raw:
        return 0
    try:
        return int(datetime.strptime(raw, "%Y-%m-%dT%H:%M:%S%z").timestamp())
    except ValueError:
        return 0


def parse_profile(business_discovery: dict[str, Any]) -> InstagramUser:
    """`business_discovery` is the object at payload["business_discovery"]
    -- the profile fields sit alongside (not nested under) the "media"
    connection at this level. Fields the cookie parser populates that
    Business Discovery doesn't expose (pronouns, bio_links,
    highlight_reel_count, business contact info, is_verified) are left at
    InstagramUser's defaults -- callers must preserve the influencer's
    last-known values for these rather than overwrite with the default
    (see docs/INSTAGRAM_GRAPH_API_PLAN.md §2's source-of-truth matrix)."""
    return InstagramUser(
        pk=business_discovery.get("id", ""),
        username=business_discovery.get("username", ""),
        full_name=business_discovery.get("name", ""),
        # Business Discovery only returns accounts it can read at all, and
        # a private professional account isn't Business-Discovery-readable
        # in the first place -- every account reachable here is public.
        is_private=False,
        profile_pic_url=business_discovery.get("profile_picture_url", ""),
        follower_count=business_discovery.get("followers_count", 0),
        following_count=business_discovery.get("follows_count", 0),
        media_count=business_discovery.get("media_count", 0),
        biography=business_discovery.get("biography", ""),
        external_url=business_discovery.get("website"),
        # Business Discovery only ever returns Business/Creator accounts
        # (that's what makes them Business-Discovery-readable) -- there's
        # no per-response field distinguishing the two, so both flags are
        # set true rather than guessed; callers needing the exact
        # sub-type keep the influencer's last cookie-sourced value.
        is_business_account=True,
        is_professional_account=True,
    )


def parse_media_items(business_discovery: dict[str, Any]) -> list[InstagramMediaItem]:
    """One page's worth of media items from business_discovery["media"]["data"].
    Returns [] when there's no media connection (e.g. a profile-only
    request, or an account with zero posts) rather than raising."""
    items = business_discovery.get("media", {}).get("data", [])
    parsed: list[InstagramMediaItem] = []
    for item in items:
        media_type_raw = item.get("media_type", "")
        product_type = _REELS_PRODUCT_TYPE if item.get("media_product_type") == "REELS" else None
        children_raw = item.get("children", {}).get("data") if item.get("children") else None
        parsed.append(
            InstagramMediaItem(
                id=item.get("id", ""),
                pk=item.get("id", ""),
                code=_shortcode_from_permalink(item.get("permalink")),
                # Business Discovery's caption is a bare string, not the
                # cookie API's {"text": ..., ...} node -- wrapped here so
                # downstream persistence (job_processor.py:
                # `item.caption.get("text", "")`) works unchanged for
                # either source.
                caption={"text": item.get("caption", "")} if item.get("caption") is not None else None,
                like_count=item.get("like_count"),  # None preserved -- hidden-likes signal
                comment_count=item.get("comments_count", 0) or 0,
                media_type=_MEDIA_TYPE_MAP.get(media_type_raw, 0),
                taken_at=_parse_timestamp(item.get("timestamp")),
                product_type=product_type,
                media_url=item.get("media_url"),
                thumbnail_url=item.get("thumbnail_url"),
                children=children_raw,
                permalink=item.get("permalink"),
            )
        )
    return parsed


def extract_media_cursor(business_discovery: dict[str, Any]) -> str:
    """The `after` cursor for media.after(cursor) pagination -- "" (never
    None) when there's no next page, so callers can use a plain truthiness
    check to decide whether to keep paginating."""
    return business_discovery.get("media", {}).get("paging", {}).get("cursors", {}).get("after") or ""
