"""Cookie follow-on for a Graph API-scraped Instagram influencer -- fills
in what Business Discovery can't provide: reel view/play counts and
comment text/replies (see docs/INSTAGRAM_HYBRID_IMPLEMENTATION.md PR3 §3.2
and the source-of-truth matrix in INSTAGRAM_GRAPH_API_PLAN.md §2).

Uses the cookie account pool exactly like JobProcessor -- account lease,
InstagramClient.from_account, lease release, the same account_at_fault
bookkeeping -- but walks only INSTAGRAM_ENRICH_FEED_PAGES pages of the
feed (no backfill, no scrape_posts_since cutoff) and never calls
get_user_info: this job only enriches posts the API scrape already
created, it doesn't discover new ones or touch the profile snapshot.

Failure semantics: any cookie-side failure here (pool empty, rate-limit,
checkpoint) fails only this enrich job with its own normal retry path --
it must never touch the parent scrape job's status, which already
succeeded and committed real API-sourced data.
"""

import time
from uuid import UUID
from datetime import date, datetime, timezone
import asyncio

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import settings
from app.core.logging import get_logger
from app.core.database import get_session
from app.core.exceptions import (
    ScraperBlockedError,
    ScraperRateLimitError,
)
from app.models.scrape_job import ScrapeJob
from app.models.influencer import Influencer
from app.models.snapshot import PostMetricsSnapshot
from app.models.post import Post
from app.repositories.instagram_account_repo import InstagramAccountRepo
from app.repositories.scrape_job_repo import ScrapeJobRepo
from app.scraper.client import InstagramClient
from app.scraper.parser import InstagramParser
from app.schemas.instagram import InstagramMediaItem
from app.queue.base import ScrapeJobMessage
from app.workers.comment_sync import sync_comments_for_post, update_engagement_timing_features
from app.workers.job_common import WORKER_ID, JobCancelledError

logger = get_logger(__name__)


class InstagramEnrichProcessor:
    def __init__(self, message: ScrapeJobMessage):
        self.message = message
        self.client: InstagramClient | None = None
        self._account = None
        self._cancel_event = asyncio.Event()

    async def process(self):
        start_time = time.perf_counter()
        async with get_session() as session:
            job = await session.get(ScrapeJob, self.message.job_id)
            if not job:
                logger.error("Enrich job not found", job_id=self.message.job_id)
                return

            job.status = "running"
            job.started_at = datetime.now(timezone.utc)
            job.last_heartbeat_at = job.started_at
            job.comments_processed = 0
            await session.commit()

            heartbeat_task = asyncio.create_task(self._heartbeat(job.id))
            try:
                account_repo = InstagramAccountRepo(session)
                self._account = await account_repo.acquire_healthy_account(worker_id=WORKER_ID)
                if self._account is None:
                    logger.warning("No healthy Instagram accounts available for enrichment -- will retry")
                    job.status = "retry_pending"
                    job.error_message = "no healthy Instagram accounts available"
                    job.finished_at = datetime.now(timezone.utc)
                    job.duration_s = time.perf_counter() - start_time
                    await session.commit()
                    return

                job.instagram_account_id = self._account.id

                outcome = "success"
                account_at_fault = True
                retry_after: int | None = None
                try:
                    self.client = InstagramClient(
                        cookies=account_repo.decrypt_cookies(self._account),
                        user_agent=self._account.user_agent,
                        proxy=account_repo.decrypt_proxy(self._account),
                    )
                    await self._run_enrich(session, job)
                    job.status = "completed"
                    job.error_message = None
                except JobCancelledError:
                    logger.info("Enrichment cancelled", job_id=job.id)
                    outcome = "cancelled"
                    job.error_message = None
                except ScraperBlockedError as e:
                    logger.exception("Enrichment blocked", exc_info=e)
                    outcome = "blocked"
                    job.error_message = str(e)
                except ScraperRateLimitError as e:
                    logger.exception("Enrichment rate limited", exc_info=e)
                    outcome = "rate_limited"
                    retry_after = e.context.get("retry_after")
                    job.error_message = str(e)
                except Exception as e:
                    logger.exception("Enrichment failed", exc_info=e)
                    outcome = "error"
                    job.error_message = str(e)
                finally:
                    if outcome == "cancelled":
                        job.status = "cancelled"
                    elif outcome != "success":
                        job.retry_count += 1
                        job.status = (
                            "retry_pending" if job.retry_count < settings.SCRAPER_MAX_RETRIES else "failed"
                        )
                    job.finished_at = datetime.now(timezone.utc)
                    job.duration_s = time.perf_counter() - start_time
                    await session.commit()
                    release_outcome = "success" if (outcome == "cancelled" or not account_at_fault) else outcome
                    await account_repo.release(self._account.id, release_outcome, retry_after=retry_after)
                    if self.client is not None:
                        await self.client.close()
            finally:
                heartbeat_task.cancel()
                try:
                    await heartbeat_task
                except asyncio.CancelledError:
                    pass

    async def _heartbeat(self, job_id: UUID) -> None:
        while True:
            await asyncio.sleep(settings.JOB_HEARTBEAT_INTERVAL_S)
            try:
                async with get_session() as hb_session:
                    cancel_requested = await ScrapeJobRepo(hb_session).heartbeat(job_id)
                    if self._account is not None:
                        await InstagramAccountRepo(hb_session).renew_lease(self._account.id)
                if cancel_requested:
                    self._cancel_event.set()
            except Exception:
                logger.warning("Enrich heartbeat update failed", job_id=job_id, exc_info=True)

    def _apply_cookie_only_fields(self, post: Post, item: InstagramMediaItem) -> None:
        """Fields the Graph API never exposes for third-party media, which
        only ride along on the cookie feed response -- see
        INSTAGRAM_GRAPH_API_PLAN.md §2's source-of-truth matrix."""
        post.is_paid_partnership = item.is_paid_partnership
        post.music_metadata = item.music_metadata
        post.locations = item.locations or None
        post.coauthor_producers = item.coauthor_producers or None
        post.tagged_usernames = item.tagged_usernames or None
        post.accessibility_caption = item.accessibility_caption
        post.counts_disabled = item.counts_disabled

    async def _merge_metrics_snapshot(self, session: AsyncSession, post: Post, item: InstagramMediaItem) -> None:
        """Updates today's PostMetricsSnapshot in place with view/play data
        (the one thing this job actually owns) if the API scrape already
        wrote one today, rather than inserting a second same-day row --
        never touches likes/comments, which are the API's to own."""
        has_view_metric = item.media_type == 2 or item.product_type == "clips"
        views = (item.view_count or item.play_count) if has_view_metric else None
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
            existing_snapshot.views = views
            existing_snapshot.reposts = item.reshare_count
            return

        # No same-day row yet (this post wasn't touched by an API scrape
        # today) -- insert a full row from the cookie item, same shape
        # JobProcessor._record_metrics_snapshot writes.
        session.add(
            PostMetricsSnapshot(
                post_id=post.id,
                likes=item.like_count,
                comments=item.comment_count,
                views=views,
                reposts=item.reshare_count,
            )
        )

    async def _run_enrich(self, session: AsyncSession, job: ScrapeJob) -> None:
        handle = self.message.handle
        influencer = await session.get(Influencer, self.message.influencer_id)
        if influencer is None:
            return

        max_id = ""
        matched_shortcodes: set[str] = set()
        sync_candidates: dict[UUID, Post] = {}
        unmatched_count = 0

        for _ in range(settings.INSTAGRAM_ENRICH_FEED_PAGES):
            if self._cancel_event.is_set():
                raise JobCancelledError()

            raw_feed = await self.client.get_user_feed(handle, max_id)
            items, next_max_id = InstagramParser.parse_feed(raw_feed)
            if not items:
                break

            stmt = select(Post).where(Post.shortcode.in_([item.code for item in items]))
            existing_by_code = {p.shortcode: p for p in (await session.execute(stmt)).scalars().all()}

            for item in items:
                post = existing_by_code.get(item.code)
                if post is None:
                    # Posted since the API scrape ran -- the next API cycle
                    # creates this Post row; nothing here to enrich yet.
                    unmatched_count += 1
                    continue

                if post.media_pk and str(item.pk) != post.media_pk:
                    # Shortcode agrees (that's the merge key), pk disagrees
                    # -- log and proceed anyway; shortcode is the source of
                    # truth per INSTAGRAM_GRAPH_API_PLAN.md §2.
                    logger.warning(
                        "Instagram media_pk mismatch between API and cookie sources",
                        shortcode=item.code, api_pk=post.media_pk, cookie_pk=str(item.pk),
                    )

                self._apply_cookie_only_fields(post, item)
                await self._merge_metrics_snapshot(session, post, item)
                matched_shortcodes.add(item.code)
                sync_candidates[post.id] = post

            await session.commit()

            if not next_max_id:
                break
            max_id = next_max_id

        if unmatched_count:
            logger.info(
                "Enrichment found feed items with no matching Post yet",
                handle=handle, unmatched_count=unmatched_count,
            )

        if self._cancel_event.is_set():
            raise JobCancelledError()

        # Comment sync -- same shared functions/behavior as JobProcessor,
        # via app.workers.comment_sync (see PR3 §3.1 extraction).
        semaphore = asyncio.Semaphore(settings.COMMENT_SYNC_CONCURRENCY)

        async def _sync_one(post: Post) -> int:
            async with semaphore:
                if self._cancel_event.is_set():
                    return 0
                try:
                    async with get_session() as post_session:
                        count = await sync_comments_for_post(post_session, self.client, post, handle)
                        await update_engagement_timing_features(post_session, post)
                        return count
                except Exception as e:
                    logger.warning("Enrich comment sync failed", shortcode=post.shortcode, error=str(e))
                    return 0

        posts_to_sync = list(sync_candidates.values())[: settings.MAX_POSTS_PER_SCRAPE]
        comment_counts = await asyncio.gather(*(_sync_one(post) for post in posts_to_sync))
        job.comments_processed = sum(comment_counts)
        await session.commit()

        if self._cancel_event.is_set():
            raise JobCancelledError()
