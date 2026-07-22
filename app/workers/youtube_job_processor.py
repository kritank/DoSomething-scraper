import time
import uuid
from uuid import UUID
from datetime import datetime, timedelta, timezone
import asyncio

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.analytics.creator_stats import CreatorStatsService
from app.core.config import settings
from app.core.logging import get_logger
from app.core.database import get_session
from app.core.exceptions import (
    InfluencerHandleNotFoundError,
    InfluencerNotFoundError,
    NoUsableYouTubeKeyError,
    ScraperBlockedError,
    ScraperRateLimitError,
    YouTubeResourceGoneError,
)
from app.models.scrape_job import ScrapeJob
from app.models.influencer import Influencer
from app.models.snapshot import ProfileSnapshot, PostMetricsSnapshot
from app.models.post import Post
from app.models.raw_response import RawResponse
from app.repositories.scrape_job_repo import ScrapeJobRepo
from app.scraper.youtube_client import YouTubeClient
from app.scraper.youtube_parser import YouTubeParser, parse_iso8601_to_datetime
from app.schemas.youtube import YouTubeComment, YouTubeVideo
from app.queue.base import ScrapeJobMessage
from app.feature_extraction.extractor import FeatureExtractor
from app.workers import youtube_key_provider as ykp
from app.workers.comment_sync import (
    NormalizedComment,
    last_comment_count,
    previous_child_counts,
    update_engagement_timing_features,
    upsert_comments_bulk,
)
from app.workers.job_common import JobCancelledError


logger = get_logger(__name__)

MAX_COMMENT_PAGES = 50   # per video, safety cap (mirrors JobProcessor)
MAX_REPLY_PAGES = 20     # per comment thread, safety cap


class YouTubeJobProcessor:
    """Scrapes one YouTube channel: profile, uploads, and comments.

    Structurally mirrors JobProcessor (app.workers.job_processor) --
    heartbeat, cooperative cancellation, retry/outcome bookkeeping,
    resumable backfill cursor -- but has no account to lease: YouTube API
    keys are shared, not exclusive sessions (see YouTubeApiKeyRepo), so
    there's no equivalent of acquire_healthy_account()/release() or lease
    renewal in the heartbeat.
    """

    def __init__(self, message: ScrapeJobMessage):
        self.message = message
        self.client: YouTubeClient | None = None
        self._cancel_event = asyncio.Event()

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
            # See JobProcessor.process() -- a retried job reuses this same
            # row, so these must be reset or a 0-duration failed attempt
            # would display counts left over from an earlier, more
            # successful one.
            job.posts_processed = 0
            job.comments_processed = 0
            await session.commit()

            heartbeat_task = asyncio.create_task(self._heartbeat(job.id))
            try:
                # Mirrors JobProcessor's "no healthy accounts" branch: check
                # up front whether ANY key is usable at all, so a totally
                # empty/exhausted pool routes straight to retry_pending
                # without spending a retry_count on a job that never got to
                # attempt anything. retry_failed_scrapes() re-dispatches
                # every retry_pending job on each tick regardless, so this
                # naturally self-heals once the pool has spare quota/keys.
                try:
                    await ykp.provide_key()
                except NoUsableYouTubeKeyError:
                    logger.warning("No usable YouTube API key available -- will retry")
                    job.status = "retry_pending"
                    job.error_message = "no usable YouTube API key available"
                    job.finished_at = datetime.now(timezone.utc)
                    job.duration_s = time.perf_counter() - start_time
                    await session.commit()
                    return

                outcome = "success"
                retry_after: int | None = None
                try:
                    self.client = YouTubeClient(
                        key_provider=ykp.provide_key,
                        usage_recorder=ykp.record_usage,
                        key_exhauster=ykp.mark_exhausted,
                        key_invalidator=ykp.mark_invalid,
                    )
                    await self._run_scrape(session, job)
                    job.status = "completed"
                    job.error_message = None
                    await self._recompute_outlier_metrics(session)
                except JobCancelledError:
                    logger.info("Scrape cancelled", job_id=job.id)
                    outcome = "cancelled"
                    job.error_message = None
                except InfluencerHandleNotFoundError as e:
                    # The handle/channel itself doesn't resolve -- every API
                    # key would fail this identically, and retrying won't
                    # make a bad handle start existing, so this fails the
                    # job outright and deactivates the influencer instead of
                    # burning SCRAPER_MAX_RETRIES attempts (see
                    # InfluencerHandleNotFoundError's docstring).
                    logger.warning("Scrape handle not found", job_id=job.id, error=str(e))
                    outcome = "target_not_found"
                    job.error_message = str(e)
                    await self._deactivate_for_missing_handle(session)
                except InfluencerNotFoundError as e:
                    # Our own Influencer row got deleted while this job sat
                    # queued -- a race, not a data problem, so there's
                    # nothing to deactivate, but also nothing a retry fixes.
                    logger.warning("Scrape target not found", job_id=job.id, error=str(e))
                    outcome = "target_not_found"
                    job.error_message = str(e)
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
                    if outcome == "cancelled":
                        job.status = "cancelled"
                    elif outcome == "target_not_found":
                        # See the InfluencerHandleNotFoundError/
                        # InfluencerNotFoundError handlers above.
                        job.status = "failed"
                    elif outcome != "success":
                        job.retry_count += 1
                        job.status = (
                            "retry_pending" if job.retry_count < settings.SCRAPER_MAX_RETRIES else "failed"
                        )
                    job.finished_at = datetime.now(timezone.utc)
                    job.duration_s = time.perf_counter() - start_time
                    # Ops visibility into "which key ran this" and "what did
                    # it cost" -- None if the scrape failed before resolving
                    # a key at all (e.g. the up-front no-usable-key check
                    # already returned earlier without reaching here).
                    if self.client is not None:
                        job.youtube_api_key_id = self.client.last_key_id
                        job.quota_units_used = self.client.units_used
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
        """Same as JobProcessor's counterpart -- the platform confirmed
        this handle doesn't resolve to any channel, so deactivate the
        influencer instead of dispatching it every day forever. Mutates
        in-session only; the caller's existing finally-block commit
        persists this alongside the job status update, same transaction."""
        influencer = await session.get(Influencer, self.message.influencer_id)
        if influencer is None:
            return
        influencer.is_active = False
        influencer.deactivation_reason = "handle_not_found"

    async def _recompute_outlier_metrics(self, session: AsyncSession) -> None:
        """Best-effort: re-score and persist this channel's recent videos'
        outlier metrics (docs/OUTLIERS_PLAN.md Phase 1) now that new
        PostMetricsSnapshot rows landed. Never fails the scrape job -- an
        outlier-scoring bug shouldn't take down data collection."""
        try:
            await CreatorStatsService(session).recompute_outlier_metrics(
                self.message.influencer_id
            )
            await session.commit()
        except Exception:
            logger.warning(
                "Outlier metrics recompute failed",
                influencer_id=self.message.influencer_id,
                exc_info=True,
            )
            await session.rollback()

    async def _heartbeat(self, job_id: UUID) -> None:
        """Same liveness ticker as JobProcessor._heartbeat, minus account
        lease renewal -- there's no leased resource here to renew (see the
        class docstring)."""
        while True:
            await asyncio.sleep(settings.JOB_HEARTBEAT_INTERVAL_S)
            try:
                async with get_session() as hb_session:
                    cancel_requested = await ScrapeJobRepo(hb_session).heartbeat(job_id)
                if cancel_requested:
                    self._cancel_event.set()
            except Exception:
                logger.warning("Heartbeat update failed", job_id=job_id, exc_info=True)

    async def _run_scrape(self, session: AsyncSession, job: ScrapeJob):
        handle = self.message.handle
        influencer = await session.get(Influencer, self.message.influencer_id)
        if influencer is None:
            raise InfluencerNotFoundError(str(self.message.influencer_id))

        # 1. Resolve + fetch the channel. Prefer the already-resolved
        # channel ID (survives a handle rename) once we have one.
        if influencer.platform_user_id:
            raw_channel = await self.client.get_channel(channel_id=influencer.platform_user_id)
        else:
            raw_channel = await self.client.get_channel(handle=handle)
        session.add(RawResponse(endpoint="yt_channels_list", handle=handle, payload=raw_channel, status=200))

        channel = YouTubeParser.parse_channel(raw_channel)
        if not channel.channel_id:
            # channels.list returned zero items -- deleted channel, or (the
            # common case in practice) the registered handle doesn't match
            # any real channel's forHandle value exactly. A 200 with an
            # empty list, not an HTTP error. This is a bad *target*, not a
            # blocked *key* -- every key would resolve this identically, so
            # (matching InstagramClient.get_user_info's own empty-profile
            # case) it's raised as InfluencerHandleNotFoundError, which
            # deactivates the influencer instead of burning retries on a
            # handle that isn't going to start existing. Once corrected
            # (Influencers page -> edit) and reactivated, the next daily
            # scrape resolves it with no other action needed.
            raise InfluencerHandleNotFoundError(handle, "youtube")

        if influencer.platform_user_id is None:
            influencer.platform_user_id = channel.channel_id
        # Refreshed every scrape, same as job_processor.py's Instagram
        # side -- channel thumbnails can change and (like Instagram's) are
        # served from an expiring-link CDN.
        if channel.thumbnail_url:
            influencer.profile_pic_url = channel.thumbnail_url

        session.add(
            ProfileSnapshot(
                influencer_id=self.message.influencer_id,
                followers=channel.subscriber_count,
                following=0,
                posts=channel.video_count,
                biography=channel.description,
                external_url=channel.custom_url,
                is_verified=False,
                total_views=channel.view_count,
                subscribers_hidden=channel.subscribers_hidden,
                platform_metadata={
                    "published_at": channel.published_at,
                    "country": channel.country,
                    "keywords": channel.keywords,
                    "made_for_kids": channel.made_for_kids,
                    "topic_categories": channel.topic_categories,
                },
            )
        )
        await session.commit()

        if not channel.uploads_playlist_id:
            # Resolved channel with no public uploads playlist at all
            # (extremely rare) -- nothing further to scrape this run.
            job.posts_processed = 0
            await session.commit()
            return

        # 2 & 3. Discover + hydrate videos, paginating the uploads playlist.
        # Same two-knob bounding as JobProcessor._run_scrape:
        #  - scrape_posts_since (per-influencer): how far back discovery goes.
        #  - COMMENT_SYNC_WINDOW_DAYS (global): which posts get comments
        #    (re-)synced this run.
        # Unlike Instagram's feed, the uploads playlist has no pinned-item
        # exemption -- every item is in strict upload order, so the age
        # cutoff check never needs a "but this one's pinned" carve-out.
        posts_since_cutoff: datetime | None = None
        if influencer.scrape_posts_since is not None:
            posts_since_cutoff = datetime.combine(
                influencer.scrape_posts_since, datetime.min.time()
            ).replace(tzinfo=timezone.utc)

        comment_sync_cutoff: datetime | None = None
        if settings.COMMENT_SYNC_WINDOW_DAYS > 0:
            comment_sync_cutoff = datetime.now(timezone.utc) - timedelta(
                days=settings.COMMENT_SYNC_WINDOW_DAYS
            )

        is_backfilling = not influencer.backfill_completed

        posts_processed = 0
        page_token = (influencer.backfill_cursor or "") if is_backfilling else ""
        sync_candidates: dict[UUID, Post] = {}
        raw_uploads_captured = False
        # Bounds the invalidPageToken restart to once per run -- if
        # discovery fails again immediately after restarting from page 1,
        # something else is wrong and this should surface as a real error
        # rather than looping forever.
        restarted_after_invalid_token = False

        cancelled = False
        while True:
            if self._cancel_event.is_set():
                cancelled = True
                break
            try:
                raw_page = await self.client.get_uploads_page(channel.uploads_playlist_id, page_token)
            except YouTubeResourceGoneError as e:
                if e.context.get("reason") == "invalidPageToken" and not restarted_after_invalid_token:
                    logger.warning(
                        "YouTube backfill pageToken expired, restarting discovery from page 1", handle=handle
                    )
                    page_token = ""
                    restarted_after_invalid_token = True
                    continue
                if posts_processed == 0:
                    raise
                logger.warning("Uploads page fetch unavailable after partial progress", handle=handle, error=str(e))
                break
            except Exception as e:
                if posts_processed == 0:
                    raise
                logger.warning("Uploads page fetch unavailable after partial progress", handle=handle, error=str(e))
                break

            if not raw_uploads_captured:
                session.add(
                    RawResponse(endpoint="yt_playlist_items", handle=handle, payload=raw_page, status=200)
                )
                raw_uploads_captured = True

            video_ids, next_page_token = YouTubeParser.parse_uploads_page(raw_page)
            if not video_ids:
                break

            # Hydrate this page's videos in one batched call -- 1 quota
            # unit for up to 50 videos, regardless of batch size.
            raw_videos = await self.client.get_videos(video_ids)
            videos_by_id = {v.video_id: v for v in YouTubeParser.parse_videos(raw_videos)}

            # One bulk lookup per page instead of one SELECT per video.
            stmt = select(Post).where(Post.shortcode.in_(video_ids))
            result = await session.execute(stmt)
            existing_by_code = {p.shortcode: p for p in result.scalars().all()}

            stop_pagination = False
            for video_id in video_ids:
                video = videos_by_id.get(video_id)
                if video is None:
                    # Deleted/private mid-backfill -- simply absent from
                    # the videos.list response for this batch of ids.
                    continue

                item_posted_at = parse_iso8601_to_datetime(video.published_at) or datetime.now(timezone.utc)

                if posts_since_cutoff is not None and item_posted_at < posts_since_cutoff:
                    stop_pagination = True
                    break

                within_comment_window = (
                    comment_sync_cutoff is None or item_posted_at >= comment_sync_cutoff
                )

                post = existing_by_code.get(video_id)
                if post is not None:
                    if is_backfilling:
                        continue  # duplicate within a resumed/overlapping backfill page

                    if comment_sync_cutoff is None or not within_comment_window:
                        # Newest-first, no pinned exemption -- everything
                        # further back is also outside the window.
                        stop_pagination = True
                        break

                    prev_count = await last_comment_count(session, post.id)
                    await self._record_metrics_snapshot(session, post, video)
                    new_comment_count = video.comment_count or 0
                    # video.comments_disabled (statistics response has no
                    # commentCount key at all) is a permanent state, not a
                    # transient 0 -- without this check, prev_count stays
                    # None forever for a comments-disabled video (there's
                    # never a real count to diff against) and the
                    # `prev_count is None` branch below re-adds it to
                    # sync_candidates on literally every single scrape,
                    # spending a commentThreads.list call (and quota) that
                    # YouTubeResourceGoneError("commentsDisabled") always
                    # rejects, forever, for as long as the video exists.
                    if not video.comments_disabled and (prev_count is None or prev_count != new_comment_count):
                        sync_candidates[post.id] = post
                    continue

                post = Post(
                    id=uuid.uuid4(),
                    influencer_id=self.message.influencer_id,
                    shortcode=video.video_id,
                    media_pk=video.video_id,
                    permalink=f"https://www.youtube.com/watch?v={video.video_id}",
                    caption=video.description,
                    title=video.title,
                    posted_at=item_posted_at,
                    is_paid_partnership=video.has_paid_product_placement,
                    product_type=video.media_label,
                    original_width=video.thumbnail_width,
                    original_height=video.thumbnail_height,
                    locations=[video.location] if video.location else None,
                    # Same semantics as Instagram's counts_disabled: true
                    # when the creator has hidden the like count.
                    counts_disabled=video.like_count is None,
                    platform_metadata={
                        "tags": video.tags,
                        "category_id": video.category_id,
                        "default_language": video.default_language,
                        "made_for_kids": video.made_for_kids,
                        "topic_categories": video.topic_categories,
                        "definition": video.definition,
                        "dimension": video.dimension,
                        "has_captions": video.has_captions,
                        "duration_raw": video.duration_raw,
                        "live_broadcast_content": video.live_broadcast_content,
                    },
                )
                session.add(post)

                await self._record_metrics_snapshot(session, post, video)

                features = FeatureExtractor.extract_features(post, media_type=video.media_label)
                features.reel_duration_s = video.duration_s
                session.add(features)

                posts_processed += 1
                if within_comment_window and not video.comments_disabled:
                    sync_candidates[post.id] = post

            await session.commit()

            if stop_pagination or not next_page_token:
                if is_backfilling:
                    influencer.backfill_completed = True
                    influencer.backfill_cursor = None
                    await session.commit()
                break

            page_token = next_page_token
            if is_backfilling:
                influencer.backfill_cursor = page_token
                await session.commit()

        job.posts_processed = posts_processed
        await session.commit()

        if cancelled:
            raise JobCancelledError()

        # 4. Sync comments (including reply threads) for posts whose
        # comment count changed since we last looked.
        posts_to_sync = list(sync_candidates.values())[: settings.MAX_POSTS_PER_SCRAPE]
        creator_channel_id = influencer.platform_user_id
        semaphore = asyncio.Semaphore(settings.COMMENT_SYNC_CONCURRENCY)

        async def _sync_one(post: Post) -> int:
            async with semaphore:
                if self._cancel_event.is_set():
                    return 0
                try:
                    async with get_session() as post_session:
                        count = await self._sync_comments_for_post(post_session, post, creator_channel_id)
                        await update_engagement_timing_features(post_session, post)
                        return count
                except YouTubeResourceGoneError as e:
                    if e.context.get("reason") == "commentsDisabled":
                        logger.info("Comments disabled for video, skipping", shortcode=post.shortcode)
                    else:
                        logger.warning("Comment sync failed", shortcode=post.shortcode, error=str(e))
                    return 0
                except Exception as e:
                    logger.warning("Comment sync failed", shortcode=post.shortcode, error=str(e))
                    return 0

        comment_counts = await asyncio.gather(*(_sync_one(post) for post in posts_to_sync))
        job.comments_processed = sum(comment_counts)
        await session.commit()

        if self._cancel_event.is_set():
            raise JobCancelledError()

    async def _record_metrics_snapshot(
        self, session: AsyncSession, post: Post, video: YouTubeVideo
    ) -> None:
        session.add(
            PostMetricsSnapshot(
                post_id=post.id,
                likes=video.like_count,
                comments=video.comment_count,
                views=video.view_count,
                # YouTube has no public share/repost metric at all --
                # always NULL, never a fabricated 0.
                reposts=None,
            )
        )

    async def _sync_comments_for_post(
        self, session: AsyncSession, post: Post, creator_channel_id: str | None
    ) -> int:
        page_token: str | None = None
        total = 0
        for _ in range(MAX_COMMENT_PAGES):
            try:
                raw = await self.client.get_comment_threads(post.media_pk, page_token or "")
            except YouTubeResourceGoneError as e:
                if e.context.get("reason") == "commentsDisabled":
                    return total
                raise
            top_level, inline_replies, next_page_token = YouTubeParser.parse_comment_threads(raw)
            if not top_level:
                break

            # Same diffing trick as JobProcessor._sync_comments_for_post:
            # only threads whose totalReplyCount changed since last sync
            # cost an extra request.
            prev_child_counts = await previous_child_counts(
                session, [c.comment_id for c in top_level]
            )

            normalized = [self._normalize_comment(c, creator_channel_id) for c in top_level]
            normalized += [self._normalize_comment(c, creator_channel_id) for c in inline_replies]
            await upsert_comments_bulk(session, post.id, normalized)
            await session.commit()
            total += len(top_level) + len(inline_replies)

            inline_counts_by_parent: dict[str, int] = {}
            for reply in inline_replies:
                if reply.parent_comment_id:
                    inline_counts_by_parent[reply.parent_comment_id] = (
                        inline_counts_by_parent.get(reply.parent_comment_id, 0) + 1
                    )

            for comment in top_level:
                stored_inline = inline_counts_by_parent.get(comment.comment_id, 0)
                if (
                    comment.total_reply_count > 0
                    and comment.total_reply_count != prev_child_counts.get(comment.comment_id)
                    and comment.total_reply_count > stored_inline
                ):
                    # _sync_replies re-fetches the FULL reply set for this
                    # parent via comments.list, not just the ones beyond
                    # what commentThreads.list already returned inline --
                    # those `stored_inline` replies were already counted
                    # into `total` above, so counting the full set again
                    # here double-counts them (a 20-reply thread with one
                    # new reply since last sync reported ~20 extra
                    # "comments processed" instead of ~15-16 actual
                    # new/updated rows).
                    full_reply_total = await self._sync_replies(session, post, comment.comment_id, creator_channel_id)
                    total += max(0, full_reply_total - stored_inline)

            if not next_page_token:
                break
            page_token = next_page_token
        return total

    async def _sync_replies(
        self, session: AsyncSession, post: Post, parent_comment_id: str, creator_channel_id: str | None
    ) -> int:
        page_token: str | None = None
        total = 0
        for _ in range(MAX_REPLY_PAGES):
            raw = await self.client.get_comment_replies(parent_comment_id, page_token or "")
            replies, next_page_token = YouTubeParser.parse_comment_replies(raw, parent_comment_id)
            if not replies:
                break

            normalized = [self._normalize_comment(c, creator_channel_id) for c in replies]
            await upsert_comments_bulk(session, post.id, normalized)
            await session.commit()
            total += len(replies)

            if not next_page_token:
                break
            page_token = next_page_token
        return total

    def _normalize_comment(
        self, comment: YouTubeComment, creator_channel_id: str | None
    ) -> NormalizedComment:
        # Display names aren't unique on YouTube -- unlike Instagram's
        # username comparison, this has to key off the stable channel ID.
        is_from_creator = bool(creator_channel_id) and comment.author_channel_id == creator_channel_id
        return NormalizedComment(
            comment_id=comment.comment_id,
            parent_comment_id=comment.parent_comment_id,
            username=comment.author_display_name,
            is_from_creator=is_from_creator,
            author_external_id=comment.author_channel_id,
            author_profile_pic_url=comment.author_profile_image_url,
            text=comment.text,
            like_count=comment.like_count,
            child_comment_count=comment.total_reply_count,
            is_edited=comment.is_edited,
            commented_at=(
                datetime.fromtimestamp(comment.published_at, tz=timezone.utc)
                if comment.published_at
                else datetime.now(timezone.utc)
            ),
        )
