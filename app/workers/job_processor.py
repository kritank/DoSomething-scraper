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
from app.scraper.client import InstagramClient
from app.scraper.parser import InstagramParser
from app.queue.base import ScrapeJobMessage
from app.feature_extraction.extractor import FeatureExtractor


logger = get_logger(__name__)


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
                    caption=caption_text,
                    posted_at=datetime.fromtimestamp(item.taken_at),
                )
                session.add(post)
                await session.commit()

                metrics = PostMetricsSnapshot(
                    post_id=post.id,
                    likes=item.like_count,
                    comments=item.comment_count,
                    views=item.view_count,
                )
                session.add(metrics)

                features = FeatureExtractor.extract_features(post)
                session.add(features)

                posts_processed += 1

            await session.commit()

            if reached_known_post or not raw_feed.get("more_available") or not next_max_id:
                break
            max_id = next_max_id
            await asyncio.sleep(1)  # be polite between page requests

        job.posts_processed = posts_processed
        await session.commit()
