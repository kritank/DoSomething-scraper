import os
import socket
import time
from uuid import UUID
from datetime import datetime
import asyncio
import random

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import settings
from app.core.logging import get_logger
from app.core.database import get_session
from app.core.exceptions import ScraperBlockedError, ScraperRateLimitError
from app.models.scrape_job import ScrapeJob
from app.models.influencer import Influencer
from app.models.snapshot import ProfileSnapshot, PostMetricsSnapshot
from app.models.post import Post
from app.models.comment import Comment
from app.models.feature_store import FeatureStore
from app.repositories.instagram_account_repo import InstagramAccountRepo
from app.scraper.client import InstagramClient
from app.scraper.parser import InstagramParser
from app.schemas.instagram import InstagramComment
from app.queue.base import ScrapeJobMessage
from app.feature_extraction.extractor import FeatureExtractor


logger = get_logger(__name__)

MEDIA_TYPE_LABELS = {1: "image", 2: "video", 8: "carousel"}

MAX_COMMENT_PAGES = 50   # per post, safety cap (~750 top-level comments/post)
MAX_REPLY_PAGES = 20     # per comment thread, safety cap

WORKER_ID = f"{socket.gethostname()}:{os.getpid()}"


async def _polite_delay() -> None:
    """Jittered pacing between requests -- looks less like a bot than a
    fixed sleep, and spreads load if multiple workers run concurrently."""
    await asyncio.sleep(random.uniform(settings.SCRAPE_DELAY_MIN_S, settings.SCRAPE_DELAY_MAX_S))


class JobProcessor:
    def __init__(self, message: ScrapeJobMessage):
        self.message = message
        self.client: InstagramClient | None = None
        self._account = None

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

            account_repo = InstagramAccountRepo(session)
            self._account = await account_repo.acquire_healthy_account(worker_id=WORKER_ID)
            if self._account is None:
                logger.critical("No healthy Instagram accounts available -- pool exhausted")
                job.status = "failed"
                job.error_message = "no healthy Instagram accounts available"
                job.finished_at = datetime.utcnow()
                job.duration_s = time.perf_counter() - start_time
                await session.commit()
                return

            self.client = InstagramClient(
                cookies=account_repo.decrypt_cookies(self._account),
                user_agent=self._account.user_agent,
            )

            outcome = "success"
            retry_after: int | None = None
            try:
                await self._run_scrape(session, job)
                job.status = "completed"
            except ScraperBlockedError as e:
                logger.exception("Scrape blocked", exc_info=e)
                outcome = "blocked"
                job.error_message = str(e)
            except ScraperRateLimitError as e:
                logger.exception("Scrape rate limited", exc_info=e)
                outcome = "rate_limited"
                retry_after = e.context.get("retry_after")
                job.error_message = str(e)
            except Exception as e:
                logger.exception("Scrape failed", exc_info=e)
                outcome = "error"
                job.error_message = str(e)
            finally:
                if outcome != "success":
                    job.retry_count += 1
                    job.status = (
                        "retry_pending" if job.retry_count < settings.SCRAPER_MAX_RETRIES else "failed"
                    )
                job.finished_at = datetime.utcnow()
                job.duration_s = time.perf_counter() - start_time
                await session.commit()
                await account_repo.release(self._account.id, outcome, retry_after=retry_after)
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

        while True:
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
            await _polite_delay()

        job.posts_processed = posts_processed
        await session.commit()

        # 4. Sync comments (including nested reply threads) for the most
        # recent posts. Comments can land on a post at any time, so this
        # re-checks older posts too, not just newly discovered ones -- but
        # full historical backfill of comments (thousands of posts, each
        # with its own paginated comment/reply tree) doesn't fit any
        # reasonable time budget at a safe request pace, and old posts'
        # comment counts change the least anyway. MAX_POSTS_PER_SCRAPE
        # bounds the worst case regardless of how large the account's total
        # post history is.
        stmt = (
            select(Post)
            .where(
                Post.influencer_id == self.message.influencer_id,
                Post.media_pk.isnot(None),
            )
            .order_by(Post.posted_at.desc())
            .limit(settings.MAX_POSTS_PER_SCRAPE)
        )
        result = await session.execute(stmt)
        posts_to_sync = result.scalars().all()

        # Posts are synced concurrently (bounded by COMMENT_SYNC_CONCURRENCY),
        # each in its own DB session -- AsyncSession isn't safe for concurrent
        # use, and this is the main lever for fitting comment sync into a
        # reasonable wall-clock budget instead of running one post at a time.
        semaphore = asyncio.Semaphore(settings.COMMENT_SYNC_CONCURRENCY)

        async def _sync_one(post: Post) -> None:
            async with semaphore:
                try:
                    async with get_session() as post_session:
                        await self._sync_comments_for_post(post_session, post)
                        await self._update_engagement_timing_features(post_session, post)
                except Exception as e:
                    logger.warning("Comment sync failed", shortcode=post.shortcode, error=str(e))
                await _polite_delay()

        await asyncio.gather(*(_sync_one(post) for post in posts_to_sync))

    async def _sync_comments_for_post(self, session: AsyncSession, post: Post) -> None:
        after: str | None = None
        for _ in range(MAX_COMMENT_PAGES):
            connection = await self.client.get_media_comments(post.media_pk, post.permalink, after)
            comments, next_after, has_more = InstagramParser.parse_comments(connection)
            if not comments:
                break

            for comment in comments:
                await self._upsert_comment(session, post.id, comment)
                if comment.child_comment_count > 0:
                    await self._sync_replies(session, post, comment)
            await session.commit()

            if not has_more or not next_after:
                break
            after = next_after
            await _polite_delay()

    async def _sync_replies(self, session: AsyncSession, post: Post, parent: InstagramComment) -> None:
        after: str | None = None
        for _ in range(MAX_REPLY_PAGES):
            connection = await self.client.get_comment_replies(post.media_pk, parent.comment_id, post.permalink, after)
            replies, next_after, has_more = InstagramParser.parse_replies(connection, parent.comment_id)
            if not replies:
                break

            for reply in replies:
                await self._upsert_comment(session, post.id, reply)
            await session.commit()

            if not has_more or not next_after:
                break
            after = next_after
            await _polite_delay()

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
