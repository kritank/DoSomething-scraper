from pydantic import BaseModel
from typing import Any, Optional


class InstagramUser(BaseModel):
    pk: int | str
    username: str
    full_name: str
    is_private: bool
    profile_pic_url: str
    follower_count: int
    following_count: int
    media_count: int

    biography: str = ""
    biography_with_entities: Optional[dict[str, Any]] = None
    bio_links: list[dict[str, Any]] = []
    pronouns: list[str] = []
    external_url: Optional[str] = None

    is_verified: bool = False
    is_business_account: bool = False
    is_professional_account: bool = False

    category_name: Optional[str] = None
    category_enum: Optional[str] = None
    overall_category_name: Optional[str] = None

    business_contact_method: Optional[str] = None
    business_email: Optional[str] = None
    business_phone_number: Optional[str] = None

    highlight_reel_count: int = 0
    has_clips: bool = False
    has_guides: bool = False
    has_channel: bool = False
    mutual_followers_count: int = 0

    is_verified_by_mv4b: bool = False
    hide_like_and_view_counts: bool = False
    has_ar_effects: bool = False
    business_category_name: Optional[str] = None


class InstagramMediaItem(BaseModel):
    id: str
    pk: int | str
    code: str
    caption: Optional[dict[str, Any]] = None
    # None means "creator hides like counts" (Business Discovery reports
    # this honestly as null) -- the cookie parser previously always had a
    # real number to report, so this widened from `int = 0` when the Graph
    # API path was added; 0 stays a valid (rare but real: zero likes)
    # value, distinct from "hidden".
    like_count: Optional[int] = 0
    comment_count: int = 0
    # view_count is populated only for photo/carousel media that happen to
    # embed a video component; for reels/video posts Instagram reports the
    # play (view) count under play_count instead -- and, since late 2024,
    # frequently sends play_count itself as null with the real number
    # moved to ig_play_count (or fb_play_count for cross-posted content).
    # Parser falls back through all three; see InstagramParser.parse_feed.
    view_count: int = 0
    play_count: int = 0
    # reshare_count is the real, publicly-exposed "this got shared/reposted
    # N times" metric on reels (Instagram started returning it in late
    # 2024). Saves and DM-shares are never exposed as numbers at all --
    # this is the closest real public metric to a "share count".
    reshare_count: int = 0
    media_type: int
    taken_at: int

    accessibility_caption: Optional[str] = None
    is_paid_partnership: bool = False
    product_type: Optional[str] = None
    music_metadata: Optional[dict[str, Any]] = None
    original_height: Optional[int] = None
    original_width: Optional[int] = None
    locations: list[dict[str, Any]] = []
    coauthor_producers: list[dict[str, Any]] = []
    tagged_usernames: list[dict[str, Any]] = []
    counts_disabled: bool = False
    # Pinned-to-profile posts stay pinned to the top of the feed regardless
    # of taken_at, so a backfill age cutoff must not stop on (or be
    # confused by) one of these -- skip them in that specific check instead.
    is_pinned: bool = False

    # Graph API (Business Discovery) only -- expiring CDN URLs and the
    # public permalink; None for cookie-sourced items. children mirrors a
    # carousel's per-slide {media_type, media_url, thumbnail_url}.
    media_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    children: Optional[list[dict[str, Any]]] = None
    permalink: Optional[str] = None


class InstagramComment(BaseModel):
    comment_id: str
    parent_comment_id: Optional[str] = None
    username: str = ""
    full_name: str = ""
    is_verified: bool = False
    text: str = ""
    like_count: int = 0
    child_comment_count: int = 0
    created_at: int = 0

    liked_by_creator: bool = False
    is_edited: bool = False
    reported_as_spam: bool = False
    author_profile_pic_url: Optional[str] = None
    author_is_private: bool = False
