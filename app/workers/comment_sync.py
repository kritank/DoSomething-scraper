"""Comment persistence helpers shared by JobProcessor (Instagram) and
YouTubeJobProcessor.

Both platforms' raw comment schemas differ (InstagramComment vs.
YouTubeComment have different field names entirely), so each processor
normalizes its platform-specific parsed comment into a NormalizedComment
before calling into this module -- everything below this point is
platform-agnostic, working only against the Comment ORM model itself.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.comment import Comment
from app.models.feature_store import FeatureStore
from app.models.post import Post
from app.models.snapshot import PostMetricsSnapshot


@dataclass
class NormalizedComment:
    comment_id: str
    parent_comment_id: Optional[str]
    username: str
    commented_at: datetime
    full_name: str = ""
    is_verified: bool = False
    is_from_creator: bool = False
    author_external_id: Optional[str] = None
    author_profile_pic_url: Optional[str] = None
    author_is_private: bool = False
    text: str = ""
    like_count: int = 0
    child_comment_count: int = 0
    liked_by_creator: bool = False
    is_edited: bool = False
    reported_as_spam: bool = False


_UPDATE_COLUMNS = (
    "like_count",
    "child_comment_count",
    "text",
    "liked_by_creator",
    "is_edited",
    "reported_as_spam",
    "is_from_creator",
    "author_external_id",
    "author_profile_pic_url",
    "author_is_private",
)


def comment_row(post_id: UUID, comment: NormalizedComment) -> dict:
    return dict(
        id=uuid.uuid4(),
        post_id=post_id,
        comment_id=comment.comment_id,
        parent_comment_id=comment.parent_comment_id,
        username=comment.username,
        full_name=comment.full_name,
        is_verified=comment.is_verified,
        is_from_creator=comment.is_from_creator,
        author_external_id=comment.author_external_id,
        author_profile_pic_url=comment.author_profile_pic_url,
        author_is_private=comment.author_is_private,
        text=comment.text,
        like_count=comment.like_count,
        child_comment_count=comment.child_comment_count,
        liked_by_creator=comment.liked_by_creator,
        is_edited=comment.is_edited,
        reported_as_spam=comment.reported_as_spam,
        commented_at=comment.commented_at,
    )


async def upsert_comments_bulk(
    session: AsyncSession, post_id: UUID, comments: list[NormalizedComment]
) -> None:
    rows = [comment_row(post_id, c) for c in comments if c.comment_id]
    if not rows:
        return

    stmt = pg_insert(Comment).values(rows)
    update_cols = {col: stmt.excluded[col] for col in _UPDATE_COLUMNS}
    # on_conflict_do_update's SET clause bypasses the column's onupdate=
    # default (that only fires for plain Core/ORM UPDATE statements), so
    # updated_at needs to be set explicitly here.
    update_cols["updated_at"] = func.now()
    stmt = stmt.on_conflict_do_update(index_elements=[Comment.comment_id], set_=update_cols)
    await session.execute(stmt)


async def previous_child_counts(session: AsyncSession, comment_ids: list[str]) -> dict[str, int]:
    """Diff each comment's reply count against what's already stored
    *before* upserting -- otherwise every comment with any replies gets its
    whole thread re-walked on every single run, even when nothing about it
    changed since last time."""
    if not comment_ids:
        return {}
    stmt = select(Comment.comment_id, Comment.child_comment_count).where(
        Comment.comment_id.in_(comment_ids)
    )
    result = await session.execute(stmt)
    return dict(result.all())


async def last_comment_count(session: AsyncSession, post_id: UUID) -> int | None:
    stmt = (
        select(PostMetricsSnapshot.comments)
        .where(PostMetricsSnapshot.post_id == post_id)
        .order_by(PostMetricsSnapshot.created_at.desc())
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def update_engagement_timing_features(session: AsyncSession, post: Post) -> None:
    """Derive engagement-timing signals from comments already saved for
    this post -- no extra API calls, just better use of scraped data.
    Identical across platforms since it only reads the Comment table."""
    stmt = select(
        func.count().label("total"),
        func.min(Comment.commented_at).filter(Comment.parent_comment_id.is_(None)).label(
            "first_comment_at"
        ),
        func.min(Comment.commented_at).filter(Comment.is_from_creator.is_(True)).label(
            "first_creator_reply_at"
        ),
        func.count().filter(Comment.is_from_creator.is_(True)).label("creator_reply_count"),
    ).where(Comment.post_id == post.id)
    result = await session.execute(stmt)
    row = result.one()
    if not row.total:
        return

    stmt = select(FeatureStore).where(FeatureStore.post_id == post.id)
    result = await session.execute(stmt)
    features = result.scalar_one_or_none()
    if not features:
        return

    posted_at = post.posted_at
    features.first_comment_at = row.first_comment_at
    features.time_to_first_comment_s = (
        int((row.first_comment_at - posted_at).total_seconds()) if row.first_comment_at else None
    )
    features.creator_reply_count = row.creator_reply_count
    features.time_to_first_creator_reply_s = (
        int((row.first_creator_reply_at - posted_at).total_seconds())
        if row.first_creator_reply_at
        else None
    )
    await session.commit()
