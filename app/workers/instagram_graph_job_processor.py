"""Scrapes one Instagram professional account via the official Graph API
(Business Discovery) -- profile + posts + like/comment-count snapshots.

Deliberately narrower than JobProcessor (the cookie path): no comment
text/replies (the API only exposes comments_count for third-party media)
and no reel view/play counts (not exposed for accounts we don't own) --
both are cookie enrichment's job (InstagramEnrichProcessor, PR3). This
processor never writes Post.media_url/thumbnail_url as stale, and never
writes a PostMetricsSnapshot views value at all -- see
docs/INSTAGRAM_HYBRID_IMPLEMENTATION.md PR2 §2.1 step 5/6 for why: an
enrichment job may have already recorded a real view count for today, and
this processor running afterward (or before) must not clobber it with an
absent value.

Structurally mirrors YouTubeJobProcessor: no leased account/session to
manage (a Graph API token is a shareable bearer credential, not an
exclusive session), so there's no lease renewal in the heartbeat, same as
YouTube's key pool.
"""

import asyncio
import time
import uuid
from uuid import UUID
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.analytics.creator_stats import CreatorStatsService
from app.core.config import settings
from app.core.logging import get_logger
from app.core.database import get_session
from app.core.exceptions import (
    InfluencerHandleNotFoundError,
    InfluencerNotFoundError,
    InstagramAccountNotProfessionalError,
    NoUsableInstagramTokenError,
    ScraperRateLimitError,
)
from app.models.scrape_job import ScrapeJob
from app.models.influencer import Influencer
from app.models.snapshot import ProfileSnapshot, PostMetricsSnapshot
from app.models.post import Post
from app.models.raw_response import RawResponse
from app.queue.base import ScrapeJobMessage
from app.queue.factory import get_queue
from app.repositories.scrape_job_repo import ScrapeJobRepo
from app.scraper.instagram_graph_client import InstagramGraphClient
from app.scraper.instagram_graph_parser import parse_profile, parse_media_items, extract_media_cursor
from app.schemas.instagram import InstagramMediaItem
from app.feature_extraction.extractor import FeatureExtractor
from app.workers import instagram_token_provider as itp
from app.workers.job_common import JobCancelledError

logger = get_logger(__name__)

# Same convention as job_processor.py's MEDIA_TYPE_LABELS.
_MEDIA_TYPE_LABELS = {1: "image", 2: "video", 8: "carousel"}

# Safety cap on how many media pages a single scrape paginates through --
# mirrors settings.MAX_POSTS_PER_SCRAPE's role in the cookie path, just
# expressed as pages (INSTAGRAM_GRAPH_MEDIA_PAGE_SIZE each) since Business
# Discovery has no separate posts_since cutoff parameter to short-circuit on.
_MAX_MEDIA_PAGES = 20


class InstagramGraphJobProcessor:
    def __init__(self, message: ScrapeJobMessage):
        self.message = message
        self.client: InstagramGraphClient | None = None

    async def process(self):
        start_time = time.perf_counter()
        async with get_session() as session:
            job = await session.get(ScrapeJob, self.message.job_id)
            if not job:
                logger.error("Job not found", job_id=self.message.job_id)
                return

            job.status = "running"
            job.started_at = datetime.now(timezone.utc)
            job.last_heartbeat_at = job.started_at
            job.posts_processed = 0
            await session.commit()

            heartbeat_task = asyncio.create_task(self._heartbeat(job.id))
            try:
                try:
                    await itp.provide_token()
                except NoUsableInstagramTokenError:
                    logger.warning("No usable Instagram API token available -- will retry")
                    job.status = "retry_pending"
                    job.error_message = "no usable Instagram API token available"
                    job.finished_at = datetime.now(timezone.utc)
                    job.duration_s = time.perf_counter() - start_time
                    await session.commit()
                    return

                outcome = "success"
                retry_after: int | None = None
                try:
                    self.client = InstagramGraphClient(
                        token_provider=itp.provide_token,
                        usage_recorder=itp.record_usage,
                        token_exhauster=itp.mark_exhausted,
                        token_invalidator=itp.mark_invalid,
                    )
                    await self._run_scrape(session, job)
                    job.status = "completed"
                    job.error_message = None
                    await self._recompute_outlier_metrics(session)
                except JobCancelledError:
                    logger.info("Scrape cancelled", job_id=job.id)
                    outcome = "cancelled"
                    job.error_message = None
                except InstagramAccountNotProfessionalError as e:
                    # Permanent for this target, not this token -- every
                    # token would fail identically. Flag the influencer so
                    # future dispatches route straight to the cookie path
                    # (see DispatchService.dispatch_scrape_job) instead of
                    # re-attempting the API every cycle, and re-dispatch a
                    # legacy scrape now so this cycle isn't lost.
                    logger.warning("Instagram account not professional, falling back to cookies", job_id=job.id, error=str(e))
                    outcome = "target_not_found"
                    job.error_message = str(e)
                    await self._fall_back_to_cookies(session)
                except InfluencerHandleNotFoundError as e:
                    logger.warning("Scrape handle not found", job_id=job.id, error=str(e))
                    outcome = "target_not_found"
                    job.error_message = str(e)
                    await self._deactivate_for_missing_handle(session)
                except InfluencerNotFoundError as e:
                    logger.warning("Scrape target not found", job_id=job.id, error=str(e))
                    outcome = "target_not_found"
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
                    if outcome == "cancelled":
                        job.status = "cancelled"
                    elif outcome == "target_not_found":
                        job.status = "failed"
                    elif outcome != "success":
                        job.retry_count += 1
                        job.status = (
                            "retry_pending" if job.retry_count < settings.SCRAPER_MAX_RETRIES else "failed"
                        )
                    job.finished_at = datetime.now(timezone.utc)
                    job.duration_s = time.perf_counter() - start_time
                    if self.client is not None:
                        job.instagram_api_token_id = self.client.last_token_id
                    await session.commit()
                    if self.client is not None:
                        await self.client.close()
            finally:
                heartbeat_task.cancel()
                try:
                    await heartbeat_task
                except asyncio.CancelledError:
                    pass

    async def _deactivate_for_missing_handle(self, session: AsyncSession) -> None:
        influencer = await session.get(Influencer, self.message.influencer_id)
        if influencer is None:
            return
        influencer.is_active = False
        influencer.deactivation_reason = "handle_not_found"

    async def _fall_back_to_cookies(self, session: AsyncSession) -> None:
        """Marks the influencer as not API-supported (so future dispatches
        route straight to the cookie path, see DispatchService) and
        re-dispatches a legacy scrape for this cycle. Guards against an
        infinite loop by construction, not a runtime check: the fallback
        message carries backend="cookies" explicitly, and
        InstagramGraphJobProcessor is only ever selected when a message
        says backend=="graph" -- a cookies-backend message can never route
        back here."""
        influencer = await session.get(Influencer, self.message.influencer_id)
        if influencer is None:
            return
        influencer.api_supported = False
        await session.commit()

        fallback_job = await ScrapeJobRepo(session).create(influencer.id)
        await get_queue().enqueue(
            ScrapeJobMessage(
                job_id=fallback_job.id,
                influencer_id=influencer.id,
                handle=influencer.handle,
                platform=influencer.platform,
                backend="cookies",
            )
        )

    async def _recompute_outlier_metrics(self, session: AsyncSession) -> None:
        try:
            await CreatorStatsService(session).recompute_outlier_metrics(self.message.influencer_id)
            await session.commit()
        except Exception:
            logger.warning(
                "Outlier metrics recompute failed", influencer_id=self.message.influencer_id, exc_info=True
            )
            await session.rollback()

    async def _heartbeat(self, job_id: UUID) -> None:
        while True:
            await asyncio.sleep(settings.JOB_HEARTBEAT_INTERVAL_S)
            try:
                async with get_session() as hb_session:
                    await ScrapeJobRepo(hb_session).heartbeat(job_id)
            except Exception:
                logger.warning("Heartbeat update failed", job_id=job_id, exc_info=True)

    async def _upsert_post(
        self, session: AsyncSession, item: InstagramMediaItem, existing: Post | None
    ) -> Post:
        """Insert a new Post, or refresh an existing one's expiring
        CDN URLs and caption/counts-adjacent fields -- never touches
        comments/views, which this processor doesn't own."""
        caption_text = item.caption.get("text", "") if item.caption else ""
        posted_at = datetime.fromtimestamp(item.taken_at, tz=timezone.utc) if item.taken_at else datetime.now(timezone.utc)

        if existing is not None:
            existing.media_url = item.media_url
            existing.thumbnail_url = item.thumbnail_url
            if item.children is not None:
                existing.platform_metadata = {**(existing.platform_metadata or {}), "children": item.children}
            return existing

        post = Post(
            id=uuid.uuid4(),
            influencer_id=self.message.influencer_id,
            shortcode=item.code,
            media_pk=str(item.pk),
            permalink=item.permalink,
            caption=caption_text,
            posted_at=posted_at,
            product_type=item.product_type,
            media_url=item.media_url,
            thumbnail_url=item.thumbnail_url,
            platform_metadata={"children": item.children} if item.children is not None else None,
        )
        session.add(post)
        return post

    async def _record_metrics_snapshot(self, session: AsyncSession, post: Post, item: InstagramMediaItem) -> None:
        """Updates today's snapshot in place if one already exists (e.g.
        cookie enrichment ran earlier today) rather than inserting a
        second same-day row -- and leaves that row's views/reposts fields
        completely untouched either way, since this processor has no view
        data of its own to contribute (see module docstring)."""
        today = datetime.now(timezone.utc).date()
        existing_snapshot = (
            await session.execute(
                select(PostMetricsSnapshot).where(
                    PostMetricsSnapshot.post_id == post.id,
                    PostMetricsSnapshot.scraped_at == today,
                )
            )
        ).scalar_one_or_none()

        if existing_snapshot is not None:
            existing_snapshot.likes = item.like_count
            existing_snapshot.comments = item.comment_count
            return

        session.add(
            PostMetricsSnapshot(
                post_id=post.id,
                likes=item.like_count,
                comments=item.comment_count,
                views=None,
                reposts=None,
            )
        )

    async def _run_scrape(self, session: AsyncSession, job: ScrapeJob):
        handle = self.message.handle
        influencer = await session.get(Influencer, self.message.influencer_id)
        if influencer is None:
            raise InfluencerNotFoundError(str(self.message.influencer_id))

        # 1 & 2. Profile + first media page in one call.
        bd = await self.client.get_business_profile(handle)
        session.add(RawResponse(endpoint="ig_graph_business_discovery", handle=handle, payload=bd, status=200))

        user = parse_profile(bd)
        if not user.username:
            # Business Discovery returned no business_discovery object at
            # all -- shouldn't normally happen (the client already raises
            # typed errors for the not-found/not-professional cases), but
            # guard against a silently empty result rather than writing a
            # bogus zero-follower snapshot.
            raise InfluencerHandleNotFoundError(handle, "instagram")

        influencer.api_supported = True
        if influencer.platform_user_id is None and user.pk:
            influencer.platform_user_id = str(user.pk)
        if user.profile_pic_url:
            influencer.profile_pic_url = user.profile_pic_url

        session.add(
            ProfileSnapshot(
                influencer_id=self.message.influencer_id,
                followers=user.follower_count,
                following=user.following_count,
                posts=user.media_count,
                biography=user.biography,
                external_url=user.external_url,
                is_business_account=user.is_business_account,
                is_professional_account=user.is_professional_account,
            )
        )
        await session.commit()

        # 3. Paginate media, upserting posts + like/comment snapshots.
        posts_processed = 0
        cursor = ""
        page_count = 0
        while page_count < _MAX_MEDIA_PAGES:
            items = parse_media_items(bd)
            if not items:
                break

            stmt = select(Post).where(Post.shortcode.in_([i.code for i in items if i.code]))
            existing_by_code = {p.shortcode: p for p in (await session.execute(stmt)).scalars().all()}

            for item in items:
                if not item.code:
                    continue  # couldn't resolve a shortcode -- nothing to key this post on
                existing = existing_by_code.get(item.code)
                is_new = existing is None
                post = await self._upsert_post(session, item, existing)
                await self._record_metrics_snapshot(session, post, item)
                if is_new:
                    await session.flush()  # post.id must exist before FeatureStore references it
                    features = FeatureExtractor.extract_features(post, media_type=_MEDIA_TYPE_LABELS.get(item.media_type, "unknown"))
                    session.add(features)
                    posts_processed += 1

            await session.commit()
            page_count += 1

            cursor = extract_media_cursor(bd)
            if not cursor:
                break
            bd = await self.client.get_business_media(handle, cursor)

        job.posts_processed = posts_processed
        await session.commit()
