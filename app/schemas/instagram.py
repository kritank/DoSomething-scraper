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
