from typing import Any, Literal, Optional

from pydantic import BaseModel


class YouTubeChannel(BaseModel):
    channel_id: str
    title: str = ""
    description: str = ""
    custom_url: Optional[str] = None
    published_at: Optional[str] = None  # ISO8601, snippet.publishedAt
    country: Optional[str] = None

    uploads_playlist_id: str = ""

    subscriber_count: int = 0
    subscribers_hidden: bool = False
    view_count: int = 0
    video_count: int = 0

    keywords: Optional[str] = None
    made_for_kids: bool = False
    topic_categories: list[str] = []


class YouTubeVideo(BaseModel):
    video_id: str
    title: str = ""
    description: str = ""
    published_at: str  # ISO8601, snippet.publishedAt -- required, drives posted_at
    tags: list[str] = []
    default_language: Optional[str] = None
    category_id: Optional[str] = None
    made_for_kids: bool = False
    topic_categories: list[str] = []

    # Duration in seconds, parsed from contentDetails.duration (ISO8601).
    duration_s: Optional[float] = None
    duration_raw: Optional[str] = None
    definition: Optional[str] = None  # "hd" | "sd"
    dimension: Optional[str] = None  # "2d" | "3d"
    has_captions: bool = False

    is_live_or_upcoming: bool = False
    live_broadcast_content: str = "none"  # "none" | "live" | "upcoming"

    # None (not 0) when the creator hides likes/comments -- see
    # docs/YOUTUBE_SCRAPER_DESIGN.md §3.3. YouTube has no public share count
    # at all, so there is no reposts field here.
    view_count: Optional[int] = None
    like_count: Optional[int] = None
    comment_count: Optional[int] = None
    comments_disabled: bool = False

    has_paid_product_placement: bool = False
    thumbnail_width: Optional[int] = None
    thumbnail_height: Optional[int] = None
    location: Optional[dict[str, Any]] = None

    @property
    def media_label(self) -> Literal["live", "video", "short"]:
        if self.is_live_or_upcoming:
            return "live"
        if self.duration_s is not None and self.duration_s <= 183:
            return "short"
        return "video"


class YouTubeComment(BaseModel):
    comment_id: str
    parent_comment_id: Optional[str] = None
    author_display_name: str = ""
    author_channel_id: Optional[str] = None
    author_profile_image_url: Optional[str] = None
    text: str = ""
    like_count: int = 0
    total_reply_count: int = 0  # 0 for replies themselves (no nested threads on YouTube)
    published_at: int = 0  # unix epoch seconds, converted from ISO8601 by the parser
    is_edited: bool = False
