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

from app.analytics.creator_stats import CreatorStatsService
from app.core.config import settings
from app.core.logging import get_logger
from app.core.database import get_session
from app.core.exceptions import (
    ScraperBlockedError,
    ScraperRateLimitError,
)
from app.models.scrape_job import ScrapeJob
from app.models.influencer import Influencer
from app.models.raw_response import RawResponse
from app.models.snapshot import PostMetricsSnapshot
from app.models.post import Post
from app.repositories.instagram_account_repo import InstagramAccountRepo
from app.repositories.scrape_job_repo import ScrapeJobRepo
from app.scraper.client import InstagramClient
from app.scraper.parser import InstagramParser
from app.schemas.instagram import InstagramMediaItem
from app.queue.base import ScrapeJobMessage
from app.workers.comment_sync import last_comment_count, sync_comments_for_post, update_engagement_timing_features
from app.workers.job_common import WORKER_ID, JobCancelledError

logger = get_logger(__name__)


def _is_comment_sync_candidate(
    comments_synced_count: int, prev_reported_count: int | None, current_reported_count: int,
    effective_comment_cap: int,
) -> bool:
    """Should this matched post get a comment-sync attempt this run?

    A post with zero actually-synced comment rows is always a candidate
    (subject to the cap) regardless of what the reported-count diff below
    says -- prev_reported_count comes from PostMetricsSnapshot.comments,
    which the *Graph* scrape keeps refreshing on every one of its own runs
    (several per hour), not evidence this post's comments were ever
    actually walked. Without this, a graph-created post's diff almost
    always reads "unchanged" (the Graph snapshot is seconds-to-minutes
    old by the time enrich reads it) and comments never sync even once --
    confirmed in production after switching to the hybrid backend.
    JobProcessor's cookie-only equivalent doesn't have this gap: a
    brand-new post there is unconditionally scheduled for its first sync,
    with no diff check at all.

    Once a post has at least one synced comment, the diff-based skip
    (nothing changed since the last check -- don't bother re-walking)
    applies exactly as before."""
    if effective_comment_cap > 0 and comments_synced_count >= effective_comment_cap:
        return False
    if comments_synced_count == 0:
        return True
    return prev_reported_count is None or prev_reported_count != current_reported_count


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
                    # Confirmed missing entirely in the original PR3
                    # landing: enrichment is often the FIRST time a real
                    # view count exists for a post (the API scrape writes
                    # views=None) -- outlier scoring falls back to likes
                    # until something recomputes, so skipping this left
                    # scores stale until the *next* Graph API cycle even
                    # though the real view data was already sitting in
                    # the DB right after this job finished.
                    await self._recompute_outlier_metrics(session)
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

    async def _recompute_outlier_metrics(self, session: AsyncSession) -> None:
        """Best-effort, same as JobProcessor/InstagramGraphJobProcessor's
        counterpart -- an outlier-scoring bug shouldn't take down
        enrichment."""
        try:
            await CreatorStatsService(session).recompute_outlier_metrics(self.message.influencer_id)
            await session.commit()
        except Exception:
            logger.warning(
                "Outlier metrics recompute failed after enrichment",
                influencer_id=self.message.influencer_id, exc_info=True,
            )
            await session.rollback()

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
        # Graph-created posts get media_pk=<Graph API media id> at insert
        # time (instagram_graph_job_processor._upsert_post), but that's a
        # different ID namespace from the legacy/cookie media pk (see the
        # NOTE below on the match key) -- and comment_sync.py's
        # get_media_comments/get_comment_replies both query Instagram's
        # cookie-authenticated GraphQL endpoint keyed on the *cookie*
        # media_id. Left unpatched, every comment sync for a Graph-created
        # post silently queries the wrong media and returns nothing.
        # Backfilling it here, from the cookie feed item that's guaranteed
        # to carry the right-namespace pk, is what makes comment sync work
        # for hybrid-scraped posts at all.
        post.media_pk = str(item.pk)
        post.is_paid_partnership = item.is_paid_partnership
        post.music_metadata = item.music_metadata
        post.locations = item.locations or None
        post.coauthor_producers = item.coauthor_producers or None
        post.tagged_usernames = item.tagged_usernames or None
        post.accessibility_caption = item.accessibility_caption
        post.counts_disabled = item.counts_disabled
        # Business Discovery doesn't return original media dimensions --
        # confirmed missing entirely for Graph-created posts until
        # enrichment backfills them here (JobProcessor sets these on
        # cookie-created posts directly; Graph-created ones had no
        # equivalent source until now).
        if item.original_height is not None:
            post.original_height = item.original_height
        if item.original_width is not None:
            post.original_width = item.original_width

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
            # Instagram frequently sends play_count as an explicit null on
            # a given response even for a post it reported a real number
            # for moments earlier (see InstagramParser.parse_feed's
            # play_count fallback chain) -- if this enrich run lands on one
            # of those responses, `views` here is a transient None, not a
            # real "views went away". Only overwrite when we actually have
            # a fresh number; otherwise keep whatever was already recorded
            # today rather than blanking it out.
            if views is not None:
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

        # Per-influencer override, else the platform default -- 0 means
        # unlimited either way (see settings.COMMENT_SYNC_DEFAULT_MAX_PER_POST
        # and Influencer.max_comments_per_post's docstrings).
        effective_comment_cap = (
            influencer.max_comments_per_post
            if influencer.max_comments_per_post is not None
            else settings.COMMENT_SYNC_DEFAULT_MAX_PER_POST
        )

        # Same cutoff as InstagramGraphJobProcessor -- confirmed missing
        # here too originally. Lower-severity than the Graph side (this
        # only ever walks INSTAGRAM_ENRICH_FEED_PAGES, small by default),
        # but a configured cutoff should still stop pagination rather than
        # wasting cookie-account requests scanning pages entirely outside
        # the influencer's configured window.
        posts_since_cutoff: datetime | None = None
        if influencer.scrape_posts_since is not None:
            posts_since_cutoff = datetime.combine(
                influencer.scrape_posts_since, datetime.min.time()
            ).replace(tzinfo=timezone.utc)

        max_id = ""
        matched_shortcodes: set[str] = set()
        sync_candidates: dict[UUID, Post] = {}
        # See JobProcessor._run_scrape's identical dict -- backing the
        # backlog-priority sort below.
        candidate_reported_counts: dict[UUID, int] = {}
        unmatched_count = 0
        raw_feed_captured = False
        stop_pagination = False

        for _ in range(settings.INSTAGRAM_ENRICH_FEED_PAGES):
            if self._cancel_event.is_set():
                raise JobCancelledError()
            if stop_pagination:
                break

            raw_feed = await self.client.get_user_feed(handle, max_id)
            if not raw_feed_captured:
                # Same "one raw payload per run" convention as
                # JobProcessor -- confirmed missing here originally.
                session.add(RawResponse(endpoint="ig_enrich_get_user_feed", handle=handle, payload=raw_feed, status=200))
                raw_feed_captured = True

            items, next_max_id = InstagramParser.parse_feed(raw_feed)
            if not items:
                break

            stmt = select(Post).where(Post.shortcode.in_([item.code for item in items]))
            existing_by_code = {p.shortcode: p for p in (await session.execute(stmt)).scalars().all()}

            for item in items:
                item_posted_at = datetime.fromtimestamp(item.taken_at, tz=timezone.utc)
                if (
                    posts_since_cutoff is not None
                    and item_posted_at < posts_since_cutoff
                    and not item.is_pinned
                ):
                    stop_pagination = True
                    break

                post = existing_by_code.get(item.code)
                if post is None:
                    # Posted since the API scrape ran -- the next API cycle
                    # creates this Post row; nothing here to enrich yet.
                    unmatched_count += 1
                    continue

                # NOTE: post.media_pk (set from the Graph API's media `id`,
                # 17-18 digits) and item.pk (the legacy/cookie API's media
                # pk, 19 digits) are DIFFERENT ID NAMESPACES from two
                # separate Instagram API generations -- they never match,
                # by construction, for the same piece of media. Confirmed
                # live: 24/24 matched posts "disagreed" on a real test run.
                # The original PR3 code logged a warning on every single
                # one of these, which is pure noise (100% expected, zero
                # diagnostic value) -- removed rather than kept as a
                # misleading "something's wrong" signal. shortcode remains
                # the sole, correct merge key (INSTAGRAM_GRAPH_API_PLAN.md §2).

                self._apply_cookie_only_fields(post, item)
                await self._merge_metrics_snapshot(session, post, item)
                matched_shortcodes.add(item.code)

                # Same diffing optimization JobProcessor already uses (skip
                # a re-walk when nothing's changed since last time) -- see
                # _is_comment_sync_candidate's docstring for the production
                # regression this was missing until now (never synced a
                # single comment for any graph-created post).
                prev_count = await last_comment_count(session, post.id)
                if _is_comment_sync_candidate(
                    post.comments_synced_count or 0, prev_count, item.comment_count, effective_comment_cap
                ):
                    sync_candidates[post.id] = post
                    candidate_reported_counts[post.id] = item.comment_count

            await session.commit()

            if stop_pagination or not next_max_id:
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
                        count = await sync_comments_for_post(
                            post_session, self.client, post, handle, effective_comment_cap
                        )
                        await update_engagement_timing_features(post_session, post)
                        return count
                except Exception as e:
                    logger.warning("Enrich comment sync failed", shortcode=post.shortcode, error=str(e))
                    return 0

        # Same backlog-priority sort as JobProcessor._run_scrape.
        ranked_candidates = sorted(
            sync_candidates.values(),
            key=lambda p: max(
                0, candidate_reported_counts.get(p.id, 0) - (p.comments_synced_count or 0)
            ),
            reverse=True,
        )
        posts_to_sync = ranked_candidates[: settings.MAX_POSTS_PER_SCRAPE]
        comment_counts = await asyncio.gather(*(_sync_one(post) for post in posts_to_sync))
        job.comments_processed = sum(comment_counts)
        await session.commit()

        if self._cancel_event.is_set():
            raise JobCancelledError()
