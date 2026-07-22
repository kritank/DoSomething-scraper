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
    ScraperBlockedError,
    ScraperRateLimitError,
)
from app.models.scrape_job import ScrapeJob
from app.models.influencer import Influencer
from app.models.snapshot import ProfileSnapshot, PostMetricsSnapshot
from app.models.post import Post
from app.models.raw_response import RawResponse
from app.repositories.instagram_account_repo import InstagramAccountRepo
from app.repositories.scrape_job_repo import ScrapeJobRepo
from app.scraper.client import InstagramClient
from app.scraper.parser import InstagramParser
from app.schemas.instagram import InstagramMediaItem
from app.queue.base import ScrapeJobMessage
from app.feature_extraction.extractor import FeatureExtractor
from app.workers.comment_sync import (
    sync_comments_for_post,
    last_comment_count,
    update_engagement_timing_features,
)
from app.workers.job_common import WORKER_ID, JobCancelledError


logger = get_logger(__name__)

MEDIA_TYPE_LABELS = {1: "image", 2: "video", 8: "carousel"}


class JobProcessor:
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
                logger.error("Job not found", job_id=self.message.job_id)
                return

            job.status = "running"
            job.started_at = datetime.now(timezone.utc)
            job.last_heartbeat_at = job.started_at
            # A retried job reuses this same row -- without resetting these,
            # a fresh attempt that bails out instantly (e.g. no healthy
            # account available) would display alongside posts/comments
            # counts left over from a *previous* attempt that made real
            # progress before failing, making a 0-duration row look like it
            # somehow processed hundreds of posts.
            job.posts_processed = 0
            job.comments_processed = 0
            await session.commit()

            # Proves this worker is still alive independent of which phase
            # of the scrape is currently executing (feed pagination on
            # `session` vs. concurrent comment sync on its own short-lived
            # sessions -- see _run_scrape). reap_stale_running/
            # release_stale_leases key off staleness of this, not total
            # job duration, so a job legitimately taking a long time (a
            # large comment backlog on a single shared account) is never
            # falsely reaped as dead. Cancelled in the outer finally below
            # no matter which path out of this method is taken.
            heartbeat_task = asyncio.create_task(self._heartbeat(job.id))
            try:
                account_repo = InstagramAccountRepo(session)
                self._account = await account_repo.acquire_healthy_account(worker_id=WORKER_ID)
                if self._account is None:
                    # Pool contention, not a scrape failure -- this job never got
                    # to attempt anything, so it shouldn't spend retry_count the
                    # same way a real failure does. retry_failed_scrapes()
                    # re-dispatches *every* retry_pending job on each tick, so
                    # with N queued influencers and 1 account, N-1 of them hit
                    # this branch every single tick; counting those against
                    # SCRAPER_MAX_RETRIES would burn the budget in a few ticks
                    # regardless of how deep the backlog actually is. Always
                    # retry_pending, uncounted -- it naturally stops once the
                    # pool has spare capacity (or stays queued forever if it
                    # truly never does, which is the correct outcome: that's an
                    # operator problem -- register more accounts -- not a
                    # per-job one).
                    logger.warning("No healthy Instagram accounts available -- will retry")
                    job.status = "retry_pending"
                    job.error_message = "no healthy Instagram accounts available"
                    job.finished_at = datetime.now(timezone.utc)
                    job.duration_s = time.perf_counter() - start_time
                    await session.commit()
                    return

                # Recorded as soon as the account is known, independent of
                # how the job ultimately turns out -- ops visibility into
                # "which account ran this" shouldn't depend on success.
                job.instagram_account_id = self._account.id

                outcome = "success"
                # Whether the account's session is implicated in a non-success
                # outcome. False for outcomes that are about the *scrape
                # target*, not the session (currently only InfluencerNotFoundError)
                # -- release() must not spend the account's failure_count (and
                # risk disabling it, see ACCOUNT_MAX_CONSECUTIVE_FAILURES) for a
                # target every account would fail identically on.
                account_at_fault = True
                retry_after: int | None = None
                try:
                    # Constructed inside this try -- a decrypt/constructor
                    # failure here used to happen *before* the
                    # finally-released account, stranding it in "in_use"
                    # for the full lease TTL instead of being freed
                    # immediately like any other error outcome.
                    self.client = InstagramClient(
                        cookies=account_repo.decrypt_cookies(self._account),
                        user_agent=self._account.user_agent,
                        proxy=account_repo.decrypt_proxy(self._account),
                    )
                    await self._run_scrape(session, job)
                    job.status = "completed"
                    # Clear any error_message left over from an earlier failed
                    # attempt on this same job row (retry_pending reuses it,
                    # retry_count and all) -- otherwise a job that eventually
                    # succeeds still displays its last failure's message.
                    job.error_message = None
                    await self._recompute_outlier_metrics(session)
                except JobCancelledError:
                    logger.info("Scrape cancelled", job_id=job.id)
                    outcome = "cancelled"
                    job.error_message = None
                except InfluencerHandleNotFoundError as e:
                    # The Instagram handle itself doesn't resolve to any
                    # account -- retrying won't help (every account would
                    # fail identically, and the handle isn't going to start
                    # existing on the next attempt), so this skips the
                    # normal retry_pending loop and fails the job outright,
                    # and deactivates the influencer so it stops being
                    # dispatched daily forever. account_at_fault stays
                    # False -- the account's session did nothing wrong.
                    logger.warning("Scrape handle not found", job_id=job.id, error=str(e))
                    outcome = "target_not_found"
                    account_at_fault = False
                    job.error_message = str(e)
                    await self._deactivate_for_missing_handle(session)
                except InfluencerNotFoundError as e:
                    # Our own Influencer row got deleted while this job sat
                    # queued -- a race, not a data problem, so there's
                    # nothing to deactivate. Still not worth retrying (the
                    # row won't come back), but the account's session is
                    # not implicated either way.
                    logger.warning("Scrape target not found", job_id=job.id, error=str(e))
                    outcome = "target_not_found"
                    account_at_fault = False
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
                        # A user-requested stop, not a failure -- doesn't
                        # spend retry_count or route through retry_pending.
                        job.status = "cancelled"
                    elif outcome == "target_not_found":
                        # See the InfluencerHandleNotFoundError/
                        # InfluencerNotFoundError handlers above -- neither
                        # case improves on a retry, so this fails outright
                        # instead of spending SCRAPER_MAX_RETRIES attempts
                        # on a target that can't resolve.
                        job.status = "failed"
                    elif outcome != "success":
                        job.retry_count += 1
                        job.status = (
                            "retry_pending" if job.retry_count < settings.SCRAPER_MAX_RETRIES else "failed"
                        )
                    job.finished_at = datetime.now(timezone.utc)
                    job.duration_s = time.perf_counter() - start_time
                    await session.commit()
                    # The account did nothing wrong on a cancel, or on an
                    # outcome that isn't its fault (see account_at_fault) --
                    # release it exactly like a clean success (active, no
                    # failure_count bump) rather than spending its health on
                    # a failure it couldn't have avoided.
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

    async def _deactivate_for_missing_handle(self, session: AsyncSession) -> None:
        """The platform confirmed this handle doesn't resolve to any
        account -- deactivates the influencer so it stops being dispatched
        every day forever, and flags why so the dashboard can say "recheck
        the handle" instead of just "inactive". Mutates in-session only;
        the caller's existing finally-block commit persists this alongside
        the job status update, same transaction."""
        influencer = await session.get(Influencer, self.message.influencer_id)
        if influencer is None:
            return
        influencer.is_active = False
        influencer.deactivation_reason = "handle_not_found"

    async def _recompute_outlier_metrics(self, session: AsyncSession) -> None:
        """Best-effort: re-score and persist this influencer's recent posts'
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
        """Background ticker for the duration of process(): every
        JOB_HEARTBEAT_INTERVAL_S, renews both the job's liveness signal and
        (if an account has been acquired by then) its account's lease, each
        via their own short-lived session/transaction so this never
        contends with whatever the main scrape work is doing concurrently.
        A transient failure here just skips one tick and logs -- it doesn't
        take down the scrape."""
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
                logger.warning("Heartbeat update failed", job_id=job_id, exc_info=True)

    async def _run_scrape(self, session: AsyncSession, job: ScrapeJob):
        handle = self.message.handle
        influencer = await session.get(Influencer, self.message.influencer_id)
        if influencer is None:
            # Deleted while this job sat queued -- fail cleanly (routes
            # through the same retry/error bookkeeping as any other
            # scrape failure) instead of an AttributeError on the first
            # attribute access below.
            raise InfluencerNotFoundError(str(self.message.influencer_id))

        # Per-influencer override, else the platform default -- 0 means
        # unlimited either way (see settings.COMMENT_SYNC_DEFAULT_MAX_PER_POST
        # and Influencer.max_comments_per_post's docstrings).
        effective_comment_cap = (
            influencer.max_comments_per_post
            if influencer.max_comments_per_post is not None
            else settings.COMMENT_SYNC_DEFAULT_MAX_PER_POST
        )

        # 1. Fetch User Info
        raw_user = await self.client.get_user_info(handle)
        parsed_user = InstagramParser.parse_user_info(raw_user)

        # Resolve platform_user_id from Instagram's numeric pk on first
        # scrape, same as youtube_job_processor.py does with the channel
        # ID -- lets a handle rename survive without orphaning this row.
        # Never overwritten once set, since a pk is permanent for the
        # account's lifetime (unlike the handle).
        if influencer.platform_user_id is None and parsed_user.pk:
            influencer.platform_user_id = str(parsed_user.pk)
        # Refreshed every scrape, unlike platform_user_id above -- Instagram's
        # profile_pic_url is a signed, expiring CDN link.
        if parsed_user.profile_pic_url:
            influencer.profile_pic_url = parsed_user.profile_pic_url

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
        # Two independent knobs bound this pass:
        #  - scrape_posts_since (per-influencer): how far back post discovery
        #    goes at all. Pinned posts are exempt from this check -- they
        #    sit at the top of the feed regardless of age and would
        #    otherwise falsely look like "we've reached the cutoff".
        #  - COMMENT_SYNC_WINDOW_DAYS (global): which posts -- new or
        #    already known -- are worth re-fetching comments/metrics for
        #    this run. A backfill still walks the full history bounded by
        #    scrape_posts_since, but only posts inside the comment window
        #    get their comment threads (re-)synced.
        #
        # Until scrape_posts_since is reached (or the feed runs out),
        # backfill_completed stays False and pagination doesn't stop at the
        # first already-known post -- it keeps going, so an interrupted
        # backfill (crash, rate limit) resumes from backfill_cursor next run
        # instead of silently treating the influencer as fully backfilled.
        # Once backfill_completed is True, steady-state runs stop as soon as
        # they reach a known post that's also outside the comment window --
        # older posts are both already saved and not worth re-syncing.
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
        max_id = (influencer.backfill_cursor or "") if is_backfilling else ""
        sync_candidates: dict[UUID, Post] = {}
        # Instagram's own reported comment count for each candidate, as of
        # this run -- what the backlog-priority sort below is computed
        # from (reported - post.comments_synced_count), so the posts
        # furthest from complete get first claim on this run's limited
        # comment-sync budget instead of losing out to whichever post
        # happened to be inserted into the dict first.
        candidate_reported_counts: dict[UUID, int] = {}
        raw_feed_captured = False

        cancelled = False
        while True:
            if self._cancel_event.is_set():
                # Break, not raise, here -- same reasoning as the graceful
                # degradation path below: whatever posts this run already
                # found are real and worth keeping (job.posts_processed is
                # set right after this loop), only the *remaining*
                # pagination and the comment-sync phase get skipped.
                cancelled = True
                break
            try:
                raw_feed = await self.client.get_user_feed(handle, max_id)
            except Exception as e:
                if posts_processed == 0:
                    # Failed on the very first page -- indistinguishable
                    # from a totally failed scrape, so it must not be
                    # swallowed into a false "completed". Re-raise so it
                    # hits the outer handler in process(), which classifies
                    # it properly (blocked/rate_limited/error) and retries
                    # -- instead of silently reporting success having
                    # scraped nothing.
                    raise
                # Failed on a *later* page, after some posts already
                # committed this run -- graceful degradation. That partial
                # progress (and, mid-backfill, influencer.backfill_cursor)
                # is real and worth keeping rather than discarding via a
                # retry from scratch.
                logger.warning("Feed fetch unavailable after partial progress", handle=handle, error=str(e))
                break

            if not raw_feed_captured:
                # One raw payload per run, not per page -- enough to
                # diagnose a field-shape drift (Instagram silently
                # renaming/moving a metric, the way ig_play_count/
                # reshare_count replaced view_count/media_repost_count)
                # without the table growing unboundedly on every page of
                # every scrape.
                session.add(
                    RawResponse(endpoint="get_user_feed", handle=handle, payload=raw_feed, status=200)
                )
                raw_feed_captured = True

            items, next_max_id = InstagramParser.parse_feed(raw_feed)
            if not items:
                break

            # One bulk lookup per page instead of one SELECT per feed item.
            stmt = select(Post).where(Post.shortcode.in_([item.code for item in items]))
            result = await session.execute(stmt)
            existing_by_code = {p.shortcode: p for p in result.scalars().all()}

            stop_pagination = False
            for item in items:
                item_posted_at = datetime.fromtimestamp(item.taken_at, tz=timezone.utc)

                if (
                    posts_since_cutoff is not None
                    and item_posted_at < posts_since_cutoff
                    and not item.is_pinned
                ):
                    stop_pagination = True
                    break

                within_comment_window = (
                    comment_sync_cutoff is None or item_posted_at >= comment_sync_cutoff
                )

                post = existing_by_code.get(item.code)
                if post is not None:
                    if is_backfilling:
                        continue  # duplicate within a resumed/overlapping backfill page

                    if comment_sync_cutoff is None or not within_comment_window:
                        if item.is_pinned:
                            # Pinned posts sit at the top of the feed
                            # regardless of age -- reaching an old, known,
                            # pinned post does NOT mean "everything further
                            # back is also old", unlike a real
                            # newest-first item. Skip it without stopping,
                            # so pagination reaches the actual
                            # reverse-chronological posts that follow.
                            # Without this, any influencer with >=1 pinned
                            # post from outside the window has every scrape
                            # stop on page 1 before ever seeing new posts.
                            continue
                        # No window configured (old "cap at MAX_POSTS_PER_SCRAPE"
                        # behavior) or this known post is already outside the
                        # window -- everything further back in this
                        # newest-first feed is too. Nothing left to gain.
                        stop_pagination = True
                        break

                    prev_count = await last_comment_count(session, post.id)
                    await self._record_metrics_snapshot(session, post, item)
                    already_capped = (
                        effective_comment_cap > 0
                        and (post.comments_synced_count or 0) >= effective_comment_cap
                    )
                    if not already_capped and (prev_count is None or prev_count != item.comment_count):
                        sync_candidates[post.id] = post
                        candidate_reported_counts[post.id] = item.comment_count
                    continue

                # New post.
                #
                # id is set explicitly (rather than relying on the column's
                # default=uuid.uuid4) so it's available immediately below,
                # without a flush -- commits happen once per page, not once
                # per post.
                caption_text = item.caption.get("text", "") if item.caption else ""
                post = Post(
                    id=uuid.uuid4(),
                    influencer_id=self.message.influencer_id,
                    shortcode=item.code,
                    media_pk=str(item.pk),
                    permalink=f"https://www.instagram.com/p/{item.code}/",
                    caption=caption_text,
                    posted_at=item_posted_at,
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

                await self._record_metrics_snapshot(session, post, item)

                media_type_label = MEDIA_TYPE_LABELS.get(item.media_type, "unknown")
                features = FeatureExtractor.extract_features(post, media_type=media_type_label)
                session.add(features)

                posts_processed += 1
                if within_comment_window:
                    sync_candidates[post.id] = post
                    candidate_reported_counts[post.id] = item.comment_count

            await session.commit()

            if stop_pagination or not raw_feed.get("more_available") or not next_max_id:
                if is_backfilling:
                    influencer.backfill_completed = True
                    influencer.backfill_cursor = None
                    await session.commit()
                break

            max_id = next_max_id
            if is_backfilling:
                influencer.backfill_cursor = max_id
                await session.commit()

        job.posts_processed = posts_processed
        await session.commit()

        if cancelled:
            raise JobCancelledError()

        # 4. Sync comments (including nested reply threads) for posts whose
        # comment count changed since we last looked, capped at
        # MAX_POSTS_PER_SCRAPE as a safety net regardless of window size.
        # Sorted by backlog (reported - already-stored) descending first --
        # every candidate otherwise competes equally for the same
        # rate-limited budget, so a handful of large-backlog posts could
        # perpetually lose their slot to smaller ones that arrived earlier
        # in feed order and never catch up. This way the furthest-behind
        # posts get first claim on this run's limited request budget.
        ranked_candidates = sorted(
            sync_candidates.values(),
            key=lambda p: max(
                0, candidate_reported_counts.get(p.id, 0) - (p.comments_synced_count or 0)
            ),
            reverse=True,
        )
        posts_to_sync = ranked_candidates[: settings.MAX_POSTS_PER_SCRAPE]

        # Posts are synced concurrently (bounded by COMMENT_SYNC_CONCURRENCY),
        # each in its own DB session -- AsyncSession isn't safe for concurrent
        # use, and this is the main lever for fitting comment sync into a
        # reasonable wall-clock budget. Request pacing across all of these
        # tasks is handled by self.client's shared rate limiter, not by
        # sleeping here.
        semaphore = asyncio.Semaphore(settings.COMMENT_SYNC_CONCURRENCY)

        async def _sync_one(post: Post) -> int:
            async with semaphore:
                # Checked after acquiring the semaphore slot, not before --
                # tasks already in flight when cancellation fires are left
                # to finish (their progress is real and cheap to keep);
                # only tasks that haven't started yet skip themselves.
                if self._cancel_event.is_set():
                    return 0
                try:
                    async with get_session() as post_session:
                        count = await self._sync_comments_for_post(
                            post_session, post, max_comments=effective_comment_cap
                        )
                        await update_engagement_timing_features(post_session, post)
                        return count
                except Exception as e:
                    logger.warning("Comment sync failed", shortcode=post.shortcode, error=str(e))
                    return 0

        comment_counts = await asyncio.gather(*(_sync_one(post) for post in posts_to_sync))
        job.comments_processed = sum(comment_counts)
        await session.commit()

        if self._cancel_event.is_set():
            raise JobCancelledError()

    async def _record_metrics_snapshot(
        self, session: AsyncSession, post: Post, item: InstagramMediaItem
    ) -> None:
        # Image/carousel posts have no public view metric at all (Instagram
        # only tracks impressions for those privately, via owner-only
        # Insights) -- storing 0 for them would silently read as "zero
        # views" in analytics instead of "not applicable". Only video posts
        # (media_type 2) and reels (product_type "clips") ever report a
        # real view/play count.
        has_view_metric = item.media_type == 2 or item.product_type == "clips"
        views = (item.view_count or item.play_count) if has_view_metric else None

        # Check-then-update on today's row rather than a blind insert --
        # this processor can run more than once for the same influencer on
        # the same UTC day (an operator retry, a scheduler double-dispatch),
        # and a blind insert previously left a duplicate PostMetricsSnapshot
        # row for that day, double-counting likes/views in any aggregation
        # query that doesn't explicitly dedupe by (post_id, scraped_at).
        # Same convention as InstagramGraphJobProcessor._record_metrics_snapshot
        # and InstagramEnrichProcessor._merge_metrics_snapshot.
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
            existing_snapshot.views = views
            existing_snapshot.reposts = item.reshare_count
            return

        session.add(
            PostMetricsSnapshot(
                post_id=post.id,
                likes=item.like_count,
                comments=item.comment_count,
                views=views,
                reposts=item.reshare_count,
            )
        )

    async def _sync_comments_for_post(
        self, session: AsyncSession, post: Post, max_comments: int = 0
    ) -> int:
        """Delegates to the platform-agnostic-signature shared function
        (app.workers.comment_sync) also used by InstagramEnrichProcessor
        (PR3) -- see that module for the actual logic, unchanged by this
        extraction."""
        return await sync_comments_for_post(session, self.client, post, self.message.handle, max_comments)
