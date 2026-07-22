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
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.comment import Comment
from app.models.feature_store import FeatureStore
from app.models.post import Post
from app.models.snapshot import PostMetricsSnapshot
from app.scraper.client import InstagramClient
from app.scraper.parser import InstagramParser
from app.schemas.instagram import InstagramComment

# Same caps JobProcessor originally hardcoded -- per post / per comment
# thread, safety nets against a pathologically large comment section
# turning one scrape into an unbounded number of requests.
MAX_COMMENT_PAGES = 50
MAX_REPLY_PAGES = 20


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
    # A commenter's verified badge or display name can change between
    # syncs -- these were only ever written on first INSERT and silently
    # went stale on every re-sync after that, unlike every other
    # commenter-identity field here.
    "is_verified",
    "full_name",
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


async def _delete_missing_comments(
    session: AsyncSession, post_id: UUID, parent_comment_id: str | None, seen_comment_ids: set[str]
) -> None:
    """Tombstones comments that no longer exist on Instagram -- deleted by
    their author or removed by moderation. Comment.upsert_comments_bulk is
    insert/update-only, so without this a removed comment stayed visible
    in this platform's analytics (counts, sentiment, engagement-timing)
    forever, even after Instagram itself no longer shows it.

    Only safe to call after a walk that saw the COMPLETE current set for
    this parent (top-level comments when parent_comment_id is None, or one
    parent's full reply thread) -- a partial/truncated walk hasn't seen
    enough to know what's actually missing, so callers must not invoke
    this after a truncated one.

    When tombstoning top-level comments (parent_comment_id=None), also
    removes any reply whose parent was just removed -- parent_comment_id
    is a plain string column, not a real FK with ON DELETE CASCADE (it
    has to reference either a genuine comment_id or a YouTube-style
    "parentId.childId" string), so a deleted top-level comment's replies
    would otherwise linger, orphaned, referencing a parent that no longer
    exists as a row."""
    stmt = delete(Comment).where(Comment.post_id == post_id)
    if parent_comment_id is None:
        stmt = stmt.where(Comment.parent_comment_id.is_(None))
    else:
        stmt = stmt.where(Comment.parent_comment_id == parent_comment_id)
    if seen_comment_ids:
        stmt = stmt.where(Comment.comment_id.notin_(seen_comment_ids))
    result = await session.execute(stmt.returning(Comment.comment_id))
    removed_ids = [row[0] for row in result.all()]

    if parent_comment_id is None and removed_ids:
        await session.execute(delete(Comment).where(Comment.parent_comment_id.in_(removed_ids)))


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
        # Excludes the creator's own top-level comments -- a creator
        # posting a caption follow-up/CTA/brand tag on their own post
        # (common practice) isn't "engagement", and previously made
        # time_to_first_comment_s measure time-to-self-comment instead of
        # time-to-first-real-fan-comment whenever that happened before any
        # fan did.
        func.min(Comment.commented_at)
        .filter(Comment.parent_comment_id.is_(None), Comment.is_from_creator.is_(False))
        .label("first_comment_at"),
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


def normalize_comment(comment: InstagramComment, creator_handle: str) -> NormalizedComment:
    """Extracted from JobProcessor._normalize_comment -- creator_handle is
    now an explicit parameter (was self.message.handle) so this is usable
    from both JobProcessor and InstagramEnrichProcessor without either
    holding a reference to the other."""
    return NormalizedComment(
        comment_id=comment.comment_id,
        parent_comment_id=comment.parent_comment_id,
        username=comment.username,
        full_name=comment.full_name,
        is_verified=comment.is_verified,
        is_from_creator=comment.username.lower() == creator_handle.lower(),
        author_profile_pic_url=comment.author_profile_pic_url,
        author_is_private=comment.author_is_private,
        text=comment.text,
        like_count=comment.like_count,
        child_comment_count=comment.child_comment_count,
        liked_by_creator=comment.liked_by_creator,
        is_edited=comment.is_edited,
        reported_as_spam=comment.reported_as_spam,
        commented_at=(
            datetime.fromtimestamp(comment.created_at, tz=timezone.utc)
            if comment.created_at
            else datetime.now(timezone.utc)
        ),
    )


async def sync_replies(
    session: AsyncSession, client: InstagramClient, post: Post, parent: InstagramComment, creator_handle: str
) -> int:
    """Extracted from JobProcessor._sync_replies -- identical behavior,
    just parameterized on (session, client, post) instead of reading
    self.client/self.message from a JobProcessor instance, so
    InstagramEnrichProcessor (PR3) can call it too.

    Always walks a thread from page 1 (no cross-call resume, unlike
    sync_comments_for_post's top-level cursor) -- so a walk that completes
    naturally (has_more=False) has always seen this parent's COMPLETE
    current reply set, and tombstones any stored reply not in it (deleted
    by its author or by moderation since the last sync). A walk truncated
    by MAX_REPLY_PAGES has only seen a partial set and must not tombstone."""
    after: str | None = None
    total = 0
    seen_ids: set[str] = set()
    truncated = True
    for _ in range(MAX_REPLY_PAGES):
        connection = await client.get_comment_replies(post.media_pk, parent.comment_id, post.permalink, after)
        replies, next_after, has_more = InstagramParser.parse_replies(connection, parent.comment_id)
        if not replies:
            truncated = False
            break

        await upsert_comments_bulk(session, post.id, [normalize_comment(c, creator_handle) for c in replies])
        await session.commit()
        total += len(replies)
        seen_ids.update(r.comment_id for r in replies)

        if not has_more or not next_after:
            truncated = False
            break
        after = next_after

    if not truncated:
        await _delete_missing_comments(session, post.id, parent.comment_id, seen_ids)
        await session.commit()
    return total


async def sync_comments_for_post(
    session: AsyncSession, client: InstagramClient, post: Post, creator_handle: str
) -> int:
    """Extracted from JobProcessor._sync_comments_for_post -- same
    diffing logic (only re-walk a thread whose reply count actually
    changed since last sync), now shared with InstagramEnrichProcessor.

    Resumes from post.comment_sync_cursor when a previous walk was
    truncated by MAX_COMMENT_PAGES before reaching Instagram's real end
    (has_more=False) -- without this, a post with more top-level comments
    than one walk can cover restarted from page 1 every single sync,
    forever, and never made forward progress past that cap. A walk that
    completes naturally clears the cursor, so a normal-sized post keeps
    re-walking from page 1 every sync (needed to re-diff already-seen
    comments for edits/handle renames/deletions) -- only a genuinely
    truncated walk resumes instead of restarting.

    Also tombstones top-level comments no longer present on Instagram
    (deleted by their author or by moderation) -- but only when this call
    started fresh from page 1 (no stored cursor) AND completed naturally,
    since either a resumed or a truncated walk has only seen a PARTIAL
    slice of the real top-level set and diffing against that would
    incorrectly delete comments this call simply never reached."""
    started_fresh = post.comment_sync_cursor is None
    after: str | None = post.comment_sync_cursor
    total = 0
    truncated = True
    seen_ids: set[str] = set()
    for _ in range(MAX_COMMENT_PAGES):
        connection = await client.get_media_comments(post.media_pk, post.permalink, after)
        comments, next_after, has_more = InstagramParser.parse_comments(connection)
        if not comments:
            truncated = False
            break

        prev_child_counts = await previous_child_counts(session, [c.comment_id for c in comments])

        await upsert_comments_bulk(session, post.id, [normalize_comment(c, creator_handle) for c in comments])
        await session.commit()
        total += len(comments)
        seen_ids.update(c.comment_id for c in comments)

        for comment in comments:
            if (
                comment.child_comment_count > 0
                and comment.child_comment_count != prev_child_counts.get(comment.comment_id)
            ):
                total += await sync_replies(session, client, post, comment, creator_handle)

        if not has_more or not next_after:
            truncated = False
            break
        after = next_after
    # If the loop above never hit a break, MAX_COMMENT_PAGES was exhausted
    # without has_more ever going False -- `truncated` is still True and
    # `after` holds the cursor for the next unfetched page, exactly where
    # the next sync should resume.

    post.comment_sync_cursor = after if truncated else None
    if started_fresh and not truncated:
        await _delete_missing_comments(session, post.id, None, seen_ids)
    await session.commit()
    return total
