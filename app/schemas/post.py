from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class PostOut(BaseModel):
    id: UUID
    influencer_id: UUID
    handle: str
    shortcode: str
    caption: Optional[str] = None
    permalink: Optional[str] = None
    posted_at: datetime
    likes: Optional[int] = None
    comments: Optional[int] = None
    views: Optional[int] = None
    reposts: Optional[int] = None


class PostListOut(BaseModel):
    posts: list[PostOut]
    total: int
