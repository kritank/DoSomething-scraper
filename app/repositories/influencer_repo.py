from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Sequence
from uuid import UUID

from sqlalchemy import Row, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from app.core.exceptions import DuplicateInfluencerError, InfluencerNotFoundError
from app.models.category import Category
from app.models.comment import Comment
from app.models.influencer import Influencer
from app.models.post import Post
from app.models.snapshot import PostMetricsSnapshot, ProfileSnapshot
from app.repositories.creator_repo import CreatorRepo
from app.schemas.influencer import (
    InfluencerActiveUpdate,
    InfluencerCreate,
    InfluencerDetailsUpdate,
    InfluencerScrapeSettingsUpdate,
)

# How many of an influencer's most recent posts feed the engagement-rate
# average on the top-influencers leaderboard. Keeps the metric responsive to
# recent performance instead of being diluted by years of post history.
ENGAGEMENT_LOOKBACK_POSTS = 12


@dataclass
class LeaderboardEntry:
    """One /influencers/top row -- either a single platform account, or a
    creator's multiple platform accounts merged into one combined entry.
    `id` is the representative (highest-follower) account's own id, kept
    distinct from `link_id` (routes to /creators/{link_id}, the Creator id
    when merged) so the frontend always has a stable per-row React key."""

    id: UUID
    link_id: UUID
    handle: str
    platform: str
    platforms: list[str]
    category_name: str
    followers: int
    following: int
    posts: int
    is_verified: bool
    engagement_rate: Optional[float]
    last_updated: datetime


class InfluencerRepo:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_all(self) -> Sequence[Influencer]:
        result = await self.session.execute(select(Influencer).order_by(Influencer.handle))
        return result.scalars().all()

    async def get_all_with_category(self) -> Sequence[Influencer]:
        """Eager-loads Influencer.category and .creator so the dashboard
        can read category_name/creator_name without an N+1 lazy-load per
        influencer."""
        stmt = (
            select(Influencer)
            .options(selectinload(Influencer.category), selectinload(Influencer.creator))
            .order_by(Influencer.handle)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    @staticmethod
    def normalize_handle(platform: str, raw_handle: str) -> str:
        """YouTube accepts a bare name, an "@name" handle, or a full
        channel URL at registration time -- normalized here to the single
        "@name" form the API's forHandle param expects (see
        YouTubeClient.get_channel), so downstream code never has to guess
        which form a given influencer row was created with. Instagram
        handles are passed through untouched -- InstagramClient uses them
        directly as a username path segment, no "@" involved."""
        if platform != "youtube":
            return raw_handle

        handle = raw_handle.strip()
        for prefix in (
            "https://www.youtube.com/",
            "http://www.youtube.com/",
            "https://youtube.com/",
            "http://youtube.com/",
            "www.youtube.com/",
            "youtube.com/",
        ):
            if handle.startswith(prefix):
                handle = handle[len(prefix):]
                break
        handle = handle.strip("/")
        if not handle.startswith("@"):
            handle = f"@{handle}"
        return handle

    async def create(self, data: InfluencerCreate) -> Influencer:
        handle = self.normalize_handle(data.platform, data.handle)
        # Every influencer gets a Creator group, not just ones explicitly
        # linked at creation -- an unnamed one defaults to the handle
        # (stripped of YouTube's "@" prefix), so every account gets its own
        # combined creator profile from day one ("linked across 1
        # platform") instead of that page requiring an explicit link first.
        # get_or_create_by_name's case-insensitive matching means two
        # accounts registered with the same default name (e.g. the same
        # handle string reused across platforms) still merge into one
        # creator, consistent with how an explicit creator_name links
        # platforms together.
        #
        # Resolved before constructing the Influencer row -- if the
        # get-or-create races another request on a duplicate name and
        # rolls back, nothing else in this transaction is lost yet.
        creator_name = (data.creator_name or "").strip() or handle.lstrip("@")
        creator = await CreatorRepo(self.session).get_or_create_by_name(creator_name)

        influencer = Influencer(
            handle=handle,
            category_id=data.category_id,
            platform=data.platform,
            scrape_posts_since=data.scrape_posts_since,
            creator_id=creator.id,
            account_type=data.account_type,
        )
        self.session.add(influencer)
        try:
            await self.session.commit()
            return influencer
        except IntegrityError:
            await self.session.rollback()
            raise DuplicateInfluencerError(handle)

    async def update_scrape_settings(
        self, influencer_id: UUID, data: InfluencerScrapeSettingsUpdate
    ) -> Influencer:
        """Partial update -- only fields actually present in the request
        are applied (via model_fields_set), same convention as
        InfluencerDetailsUpdate. Both fields default to None, so without
        this a request setting only max_comments_per_post would silently
        wipe scrape_posts_since (and vice versa) back to null."""
        influencer = await self.get_by_id(influencer_id)
        fields_set = data.model_fields_set
        if "scrape_posts_since" in fields_set:
            influencer.scrape_posts_since = data.scrape_posts_since
        if "max_comments_per_post" in fields_set:
            influencer.max_comments_per_post = data.max_comments_per_post
        await self.session.commit()
        return influencer

    async def update_active(self, influencer_id: UUID, data: InfluencerActiveUpdate) -> Influencer:
        """Pause/resume tracking without touching any scraped data -- the
        default, reversible "remove" action. run_daily_scrapes() and the
        dashboard's add-influencer flow already only consider is_active
        influencers.

        Always clears paused_by_category: a direct per-influencer toggle is
        now the explicit source of truth for this row, so a later category
        reactivate (CategoryRepo.update, which only resumes influencers it
        itself paused) must not touch it -- e.g. re-deactivating a single
        influencer someone just reactivated by hand shouldn't be silently
        undone the next time its category cycles off and back on."""
        influencer = await self.get_by_id(influencer_id)
        influencer.is_active = data.is_active
        influencer.paused_by_category = False
        influencer.deactivation_reason = None
        await self.session.commit()
        return influencer

    async def update_details(self, influencer_id: UUID, data: InfluencerDetailsUpdate) -> Influencer:
        """Corrects a wrong handle or moves an influencer to a different
        category after creation -- neither was possible before (both were
        write-once at create() time), which is exactly what forced a manual
        SQL fix for a mistyped handle earlier."""
        influencer = await self.get_by_id(influencer_id)
        if data.handle is not None:
            old_handle = influencer.handle
            influencer.handle = self.normalize_handle(influencer.platform, data.handle)
            # A handle correction is exactly the fix a "handle not found,
            # please recheck" deactivation was asking for -- clear the flag
            # so the next scrape gets a real chance instead of the influencer
            # silently staying deactivated with a now-stale reason. Doesn't
            # touch is_active itself: the corrected handle still needs the
            # normal reactivate action (or the edit form can do both at once).
            influencer.deactivation_reason = None
            if old_handle.lower() != influencer.handle.lower():
                # comment_sync.py's is_from_creator is computed at sync
                # time from whatever the influencer's handle was THEN
                # (comment_sync.normalize_comment: username == creator
                # handle) -- a rename otherwise leaves every comment
                # outside the rolling comment-sync window permanently
                # mislabeled, with no re-scrape ever touching it again to
                # fix it. One bulk UPDATE recomputes it for every existing
                # comment against the new handle instead of waiting on
                # scrape coverage that may never come.
                await self.session.execute(
                    update(Comment)
                    .where(Comment.post_id.in_(select(Post.id).where(Post.influencer_id == influencer_id)))
                    .values(is_from_creator=func.lower(Comment.username) == influencer.handle.lower())
                )
        if data.category_id is not None:
            influencer.category_id = data.category_id
        if data.creator_name is not None:
            if data.creator_name.strip():
                creator = await CreatorRepo(self.session).get_or_create_by_name(data.creator_name)
                influencer.creator_id = creator.id
            else:
                influencer.creator_id = None
        if data.account_type is not None:
            influencer.account_type = data.account_type
        try:
            await self.session.commit()
        except IntegrityError:
            await self.session.rollback()
            raise DuplicateInfluencerError(data.handle or influencer.handle)
        return influencer

    async def delete(self, influencer_id: UUID) -> None:
        """Hard delete -- cascades to posts/comments/snapshots/feature_store
        via DB-level ON DELETE CASCADE. Irreversible."""
        influencer = await self.get_by_id(influencer_id)
        await self.session.delete(influencer)
        await self.session.commit()

    async def get_by_id(self, influencer_id: UUID) -> Influencer:
        influencer = await self.session.get(Influencer, influencer_id)
        if not influencer:
            raise InfluencerNotFoundError(str(influencer_id))
        return influencer
    
    async def get_by_handle(self, handle: str) -> Influencer:
        result = await self.session.execute(select(Influencer).where(Influencer.handle == handle))
        influencer = result.scalar_one_or_none()
        if not influencer:
            raise InfluencerNotFoundError(handle)
        return influencer

    def _leaderboard_base_stmt(self):
        """Shared projection behind get_top_ranked and get_public_accounts:
        each influencer's latest profile snapshot (followers/verified/etc.)
        plus an engagement rate averaged over their most recent posts.
        Callers apply their own .where()/.order_by()/.limit()."""
        latest_snapshot = (
            select(
                ProfileSnapshot,
                func.row_number()
                .over(
                    partition_by=ProfileSnapshot.influencer_id,
                    order_by=ProfileSnapshot.scraped_at.desc(),
                )
                .label("rn"),
            )
            .subquery("latest_snapshot")
        )

        latest_metric = (
            select(
                PostMetricsSnapshot.post_id,
                PostMetricsSnapshot.likes,
                PostMetricsSnapshot.comments,
                func.row_number()
                .over(
                    partition_by=PostMetricsSnapshot.post_id,
                    order_by=PostMetricsSnapshot.scraped_at.desc(),
                )
                .label("rn"),
            )
            .subquery("latest_metric")
        )

        recent_posts = (
            select(
                Post.id,
                Post.influencer_id,
                func.row_number()
                .over(partition_by=Post.influencer_id, order_by=Post.posted_at.desc())
                .label("rn"),
            )
            .subquery("recent_posts")
        )

        engagement = (
            select(
                recent_posts.c.influencer_id,
                func.avg(latest_metric.c.likes + latest_metric.c.comments).label(
                    "avg_engagement"
                ),
            )
            .join(latest_metric, latest_metric.c.post_id == recent_posts.c.id)
            .where(
                recent_posts.c.rn <= ENGAGEMENT_LOOKBACK_POSTS,
                latest_metric.c.rn == 1,
            )
            .group_by(recent_posts.c.influencer_id)
            .subquery("engagement")
        )

        stmt = (
            select(
                Influencer.id,
                Influencer.handle,
                Influencer.platform,
                Influencer.creator_id,
                Influencer.profile_pic_url,
                Category.name.label("category_name"),
                latest_snapshot.c.followers,
                latest_snapshot.c.following,
                latest_snapshot.c.posts,
                latest_snapshot.c.is_verified,
                latest_snapshot.c.updated_at.label("last_updated"),
                # YouTube-only extras (country, channel creation date); null
                # for Instagram rows -- see ProfileSnapshot.platform_metadata.
                latest_snapshot.c.platform_metadata,
                engagement.c.avg_engagement,
            )
            .join(latest_snapshot, latest_snapshot.c.influencer_id == Influencer.id)
            .join(Category, Category.id == Influencer.category_id)
            .outerjoin(engagement, engagement.c.influencer_id == Influencer.id)
            .where(latest_snapshot.c.rn == 1)
        )
        return stmt, latest_snapshot

    # Ranking key per `sort` value -- entries missing the sorted field (e.g.
    # no engagement history yet) sort last rather than erroring or floating
    # to the top as a false zero.
    _SORT_KEYS = {
        "followers": lambda e: (True, e.followers),
        "posts": lambda e: (True, e.posts),
        "engagement": lambda e: (e.engagement_rate is not None, e.engagement_rate or 0),
    }

    async def get_top_ranked(
        self,
        limit: int = 20,
        category_name: Optional[str] = None,
        platform: Optional[str] = None,
        sort: str = "followers",
    ) -> list[LeaderboardEntry]:
        """Ranked leaderboard for the public "Top Influencers" page.

        A creator with linked accounts on multiple platforms (Influencer
        rows sharing a creator_id) is merged into a single combined entry
        -- otherwise the same person/brand would occupy two leaderboard
        slots. Merging happens whether or not `platform` is set: filtering
        to one platform just means each merge group only ever has one
        member (a creator's second platform account is excluded by the
        Influencer.platform predicate below), so the grouping code path
        stays uniform instead of branching.

        No limit is applied at the SQL level -- accounts must be pulled in
        full and merged first, since a creator's combined rank can differ
        from either individual account's rank. `limit` and `sort` are both
        applied in Python after merging instead.
        """
        stmt, latest_snapshot = self._leaderboard_base_stmt()
        stmt = stmt.where(Influencer.is_active.is_(True))
        if category_name:
            stmt = stmt.where(Category.name == category_name)
        if platform:
            stmt = stmt.where(Influencer.platform == platform)
        stmt = stmt.order_by(latest_snapshot.c.followers.desc())

        result = await self.session.execute(stmt)
        rows = result.all()

        groups: dict[UUID, list[Row]] = defaultdict(list)
        for row in rows:
            groups[row.creator_id or row.id].append(row)

        entries = [self._merge_leaderboard_group(key, group) for key, group in groups.items()]
        entries.sort(key=self._SORT_KEYS.get(sort, self._SORT_KEYS["followers"]), reverse=True)
        return entries[:limit]

    @staticmethod
    def _merge_leaderboard_group(link_id: UUID, rows: Sequence[Row]) -> LeaderboardEntry:
        primary = max(rows, key=lambda r: r.followers)
        engagement_rates = [
            round(r.avg_engagement / r.followers * 100, 2)
            for r in rows
            if r.avg_engagement is not None and r.followers
        ]
        return LeaderboardEntry(
            id=primary.id,
            link_id=link_id,
            handle=primary.handle,
            platform=primary.platform,
            platforms=sorted({r.platform for r in rows}),
            category_name=primary.category_name,
            followers=sum(r.followers for r in rows),
            following=sum(r.following for r in rows),
            posts=sum(r.posts for r in rows),
            is_verified=any(r.is_verified for r in rows),
            engagement_rate=(
                round(sum(engagement_rates) / len(engagement_rates), 2) if engagement_rates else None
            ),
            last_updated=max(r.last_updated for r in rows),
        )

    async def get_public_accounts(self, influencer_ids: Sequence[UUID]) -> Sequence[Row]:
        """Same per-influencer stats projection as get_top_ranked, scoped to
        a specific set of influencer ids -- backs the public combined
        creator profile page. Includes paused accounts (unlike the
        leaderboard) since a creator's profile shouldn't drop a platform
        just because scraping is temporarily paused on it."""
        if not influencer_ids:
            return []
        stmt, latest_snapshot = self._leaderboard_base_stmt()
        stmt = stmt.where(Influencer.id.in_(influencer_ids)).order_by(
            latest_snapshot.c.followers.desc()
        )
        result = await self.session.execute(stmt)
        return result.all()
