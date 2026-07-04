import time
from uuid import UUID
from datetime import datetime
import asyncio

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.logging import get_logger
from app.core.database import get_session
from app.models.scrape_job import ScrapeJob
from app.models.influencer import Influencer
from app.models.snapshot import ProfileSnapshot, PostMetricsSnapshot
from app.models.post import Post
from app.models.comment import Comment
from app.models.feature_store import FeatureStore
from app.scraper.client import InstagramClient
from app.scraper.parser import InstagramParser
from app.schemas.instagram import InstagramComment
from app.queue.base import ScrapeJobMessage
from app.feature_extraction.extractor import FeatureExtractor


logger = get_logger(__name__)

MEDIA_TYPE_LABELS = {1: "image", 2: "video", 8: "carousel"}

COMMENT_PAGE_SLEEP = 0.5
MAX_COMMENT_PAGES = 50   # per post, safety cap (~750 top-level comments/post)
MAX_REPLY_PAGES = 20     # per comment thread, safety cap


class JobProcessor:
    def __init__(self, message: ScrapeJobMessage):
        self.message = message
        self.client = InstagramClient()

    async def process(self):
        start_time = time.perf_counter()
        async with get_session() as session:
            job = await session.get(ScrapeJob, self.message.job_id)
            if not job:
                logger.error("Job not found", job_id=self.message.job_id)
                return
            
            job.status = "running"
            job.started_at = datetime.utcnow()
            await session.commit()
            
            try:
                await self._run_scrape(session, job)
                job.status = "completed"
            except Exception as e:
                logger.exception("Scrape failed", exc_info=e)
                job.status = "failed"
                job.error_message = str(e)
            finally:
                job.finished_at = datetime.utcnow()
                job.duration_s = time.perf_counter() - start_time
                await session.commit()
                await self.client.close()

    async def _run_scrape(self, session: AsyncSession, job: ScrapeJob):
        handle = self.message.handle
        
        # 1. Fetch User Info
        raw_user = await self.client.get_user_info(handle)
        parsed_user = InstagramParser.parse_user_info(raw_user)
        
        # Create profile snapshot
        snapshot = ProfileSnapshot(
            influencer_id=self.message.influencer_id,
            followers=parsed_user.follower_count,
            following=parsed_user.following_count,
            posts=parsed_user.media_count,
            biography=parsed_user.biography,
            biography_with_entities=parsed_user.biography_with_entities,
            bio_links=parsed_user.bio_links,
            pronouns=parsed_user.pronouns,
            external_url=parsed_user.external_url,
            is_verified=parsed_user.is_verified,
            is_business_account=parsed_user.is_business_account,
            is_professional_account=parsed_user.is_professional_account,
            category_name=parsed_user.category_name,
            category_enum=parsed_user.category_enum,
            overall_category_name=parsed_user.overall_category_name,
            business_contact_method=parsed_user.business_contact_method,
            business_email=parsed_user.business_email,
            business_phone_number=parsed_user.business_phone_number,
            highlight_reel_count=parsed_user.highlight_reel_count,
            has_clips=parsed_user.has_clips,
            has_guides=parsed_user.has_guides,
            has_channel=parsed_user.has_channel,
            mutual_followers_count=parsed_user.mutual_followers_count,
            is_meta_verified=parsed_user.is_verified_by_mv4b,
            hides_like_view_counts=parsed_user.hide_like_and_view_counts,
            has_ar_effects=parsed_user.has_ar_effects,
            business_category_name=parsed_user.business_category_name,
        )
        session.add(snapshot)
        await session.commit()
        
        # 2 & 3. Fetch and save posts, paginating over the user's feed.
        #
        # First scrape for an influencer (no posts saved yet): backfill full
        # history by paginating until Instagram runs out of pages.
        # Every scrape after that: page only until we hit a shortcode we've
        # already saved. The feed is newest-first, so once we see a known
        # post everything beyond it is already captured -- stop there
        # instead of re-walking the whole history every day.
        stmt = select(Post.id).where(Post.influencer_id == self.message.influencer_id).limit(1)
        result = await session.execute(stmt)
        is_first_scrape = result.scalar_one_or_none() is None

        posts_processed = 0
        max_id = ""
        MAX_PAGES = 100  # safety cap against runaway backfill pagination

        for _ in range(MAX_PAGES):
            try:
                raw_feed = await self.client.get_user_feed(handle, max_id)
            except Exception as e:
                logger.warning("Feed fetch unavailable", handle=handle, error=str(e))
                break

            items, next_max_id = InstagramParser.parse_feed(raw_feed)
            if not items:
                break

            reached_known_post = False
            for item in items:
                stmt = select(Post).where(Post.shortcode == item.code)
                result = await session.execute(stmt)
                post = result.scalar_one_or_none()

                if post:
                    if is_first_scrape:
                        continue  # duplicate within this backfill pass
                    reached_known_post = True
                    break

                caption_text = item.caption.get("text", "") if item.caption else ""
                post = Post(
                    influencer_id=self.message.influencer_id,
                    shortcode=item.code,
                    media_pk=str(item.pk),
                    permalink=f"https://www.instagram.com/p/{item.code}/",
                    caption=caption_text,
                    posted_at=datetime.fromtimestamp(item.taken_at),
                    accessibility_caption=item.accessibility_caption,
                    is_paid_partnership=item.is_paid_partnership,
                    product_type=item.product_type,
                    music_metadata=item.music_metadata,
                    original_height=item.original_height,
                    original_width=item.original_width,
                    locations=item.locations,
                    coauthor_producers=item.coauthor_producers,
                    tagged_usernames=item.tagged_usernames,
                    counts_disabled=item.counts_disabled,
                )
                session.add(post)
                await session.commit()

                metrics = PostMetricsSnapshot(
                    post_id=post.id,
                    likes=item.like_count,
                    comments=item.comment_count,
                    # Reels/videos report their view count in play_count;
                    # view_count is 0 for those and only meaningful for
                    # media types that don't have a play_count at all.
                    views=item.view_count or item.play_count,
                )
                session.add(metrics)

                media_type_label = MEDIA_TYPE_LABELS.get(item.media_type, "unknown")
                features = FeatureExtractor.extract_features(post, media_type=media_type_label)
                session.add(features)

                posts_processed += 1

            await session.commit()

            if reached_known_post or not raw_feed.get("more_available") or not next_max_id:
                break
            max_id = next_max_id
            await asyncio.sleep(1)  # be polite between page requests

        job.posts_processed = posts_processed
        await session.commit()

        # 4. Sync comments (including nested reply threads) for every saved
        # post, not just the ones discovered this run. Comments can land on
        # a post at any time, so old posts need re-checking too, not only
        # newly discovered ones.
        stmt = select(Post).where(
            Post.influencer_id == self.message.influencer_id,
            Post.media_pk.isnot(None),
        )
        result = await session.execute(stmt)
        all_posts = result.scalars().all()

        for post in all_posts:
            try:
                await self._sync_comments_for_post(session, post)
                await self._update_engagement_timing_features(session, post)
            except Exception as e:
                logger.warning("Comment sync failed", shortcode=post.shortcode, error=str(e))
            await asyncio.sleep(COMMENT_PAGE_SLEEP)

    async def _sync_comments_for_post(self, session: AsyncSession, post: Post) -> None:
        min_id = ""
        for _ in range(MAX_COMMENT_PAGES):
            raw = await self.client.get_media_comments(post.media_pk, min_id)
            comments, next_min_id, has_more = InstagramParser.parse_comments(raw)
            if not comments:
                break

            for comment in comments:
                await self._upsert_comment(session, post.id, comment)
                if comment.child_comment_count > 0:
                    await self._sync_replies(session, post, comment)
            await session.commit()

            if not has_more or not next_min_id:
                break
            min_id = next_min_id
            await asyncio.sleep(COMMENT_PAGE_SLEEP)

    async def _sync_replies(self, session: AsyncSession, post: Post, parent: InstagramComment) -> None:
        cursor = ""
        for _ in range(MAX_REPLY_PAGES):
            raw = await self.client.get_comment_replies(post.media_pk, parent.comment_id, cursor)
            replies, next_cursor, has_more = InstagramParser.parse_replies(raw, parent.comment_id)
            if not replies:
                break

            for reply in replies:
                await self._upsert_comment(session, post.id, reply)
            await session.commit()

            if not has_more or not next_cursor:
                break
            cursor = next_cursor
            await asyncio.sleep(COMMENT_PAGE_SLEEP)

    async def _upsert_comment(self, session: AsyncSession, post_id: UUID, comment: InstagramComment) -> None:
        if not comment.comment_id:
            return

        stmt = select(Comment).where(Comment.comment_id == comment.comment_id)
        result = await session.execute(stmt)
        existing = result.scalar_one_or_none()

        is_from_creator = comment.username.lower() == self.message.handle.lower()

        if existing:
            existing.like_count = comment.like_count
            existing.child_comment_count = comment.child_comment_count
            existing.text = comment.text
            existing.liked_by_creator = comment.liked_by_creator
            existing.is_edited = comment.is_edited
            existing.reported_as_spam = comment.reported_as_spam
            existing.is_from_creator = is_from_creator
            existing.author_profile_pic_url = comment.author_profile_pic_url
            existing.author_is_private = comment.author_is_private
            return

        session.add(
            Comment(
                post_id=post_id,
                comment_id=comment.comment_id,
                parent_comment_id=comment.parent_comment_id,
                username=comment.username,
                full_name=comment.full_name,
                is_verified=comment.is_verified,
                is_from_creator=is_from_creator,
                author_profile_pic_url=comment.author_profile_pic_url,
                author_is_private=comment.author_is_private,
                text=comment.text,
                like_count=comment.like_count,
                child_comment_count=comment.child_comment_count,
                liked_by_creator=comment.liked_by_creator,
                is_edited=comment.is_edited,
                reported_as_spam=comment.reported_as_spam,
                commented_at=datetime.fromtimestamp(comment.created_at) if comment.created_at else datetime.utcnow(),
            )
        )

    async def _update_engagement_timing_features(self, session: AsyncSession, post: Post) -> None:
        """Derive engagement-timing signals from comments already saved for
        this post -- no extra API calls, just better use of scraped data.
        """
        stmt = select(Comment).where(Comment.post_id == post.id)
        result = await session.execute(stmt)
        all_comments = result.scalars().all()
        if not all_comments:
            return

        top_level = [c for c in all_comments if c.parent_comment_id is None]
        creator_comments = [c for c in all_comments if c.is_from_creator]

        first_comment_at = min((c.commented_at for c in top_level), default=None)
        first_creator_reply_at = min((c.commented_at for c in creator_comments), default=None)

        stmt = select(FeatureStore).where(FeatureStore.post_id == post.id)
        result = await session.execute(stmt)
        features = result.scalar_one_or_none()
        if not features:
            return

        posted_at = post.posted_at
        features.first_comment_at = first_comment_at
        features.time_to_first_comment_s = (
            int((first_comment_at - posted_at).total_seconds()) if first_comment_at else None
        )
        features.creator_reply_count = len(creator_comments)
        features.time_to_first_creator_reply_s = (
            int((first_creator_reply_at - posted_at).total_seconds()) if first_creator_reply_at else None
        )
        await session.commit()
