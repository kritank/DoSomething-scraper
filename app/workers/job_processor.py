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
        )
        session.add(snapshot)
        await session.commit()
        
        # 2. Fetch User Feed
        raw_feed = await self.client.get_user_feed(str(parsed_user.pk))
        items, _ = InstagramParser.parse_feed(raw_feed)
        
        # 3. Save Posts and Metrics
        posts_processed = 0
        for item in items:
            # Check if post exists
            stmt = select(Post).where(Post.shortcode == item.code)
            result = await session.execute(stmt)
            post = result.scalar_one_or_none()
            
            if not post:
                caption_text = item.caption.get("text", "") if item.caption else ""
                post = Post(
                    influencer_id=self.message.influencer_id,
                    shortcode=item.code,
                    caption=caption_text,
                    posted_at=datetime.fromtimestamp(item.taken_at),
                )
                session.add(post)
                await session.commit()
                
            # Create metrics snapshot
            metrics = PostMetricsSnapshot(
                post_id=post.id,
                likes=item.like_count,
                comments=item.comment_count,
                views=item.view_count,
            )
            session.add(metrics)
            
            # Extract features
            features = FeatureExtractor.extract_features(post)
            session.add(features)
            
            posts_processed += 1
            
        job.posts_processed = posts_processed
        await session.commit()
