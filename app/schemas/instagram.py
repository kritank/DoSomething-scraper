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


class InstagramMediaItem(BaseModel):
    id: str
    pk: int | str
    code: str
    caption: Optional[dict[str, Any]] = None
    like_count: int = 0
    comment_count: int = 0
    view_count: int = 0
    play_count: int = 0
    media_type: int
    taken_at: int
