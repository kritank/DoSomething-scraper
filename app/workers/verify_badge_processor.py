"""On-demand "refresh verified badge" job -- learns the real is_verified
status from whatever source actually exposes it for the influencer's
platform, and writes it forward, without touching posts/comments/other
profile fields. Neither pipeline's regular scrape can teach itself
is_verified on its own --

- Instagram's Graph API (Business Discovery) doesn't expose is_verified at
  all (InstagramGraphJobProcessor carries the previous snapshot's value
  forward instead of re-deriving it); an influencer with no cookie-sourced
  history yet has nothing to carry forward.
- YouTube's Data API doesn't expose it either (see
  docs/YOUTUBE_SCRAPER_DESIGN.md) -- the only source is the public channel
  page (app/scraper/youtube_page_scraper.py).

Writes a brand new ProfileSnapshot (not a mutation of history) that copies
every other field forward from the influencer's current latest snapshot,
same carry-forward convention InstagramGraphJobProcessor._run_scrape
already uses for Graph-sourced fields -- so a later Graph scrape's own
carry-forward picks up the corrected value automatically.
"""
import time
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import settings
from app.core.exceptions import (
    InfluencerHandleNotFoundError,
    ScraperBlockedError,
    ScraperRateLimitError,
    YouTubeChannelPageError,
)
from app.core.logging import get_logger
from app.core.database import get_session
from app.models.scrape_job import ScrapeJob
from app.models.influencer import Influencer
from app.models.snapshot import ProfileSnapshot
from app.repositories.instagram_account_repo import InstagramAccountRepo
from app.scraper.client import InstagramClient
from app.scraper.parser import InstagramParser
from app.scraper.youtube_page_scraper import fetch_is_verified
from app.queue.base import ScrapeJobMessage
from app.workers.job_common import WORKER_ID

logger = get_logger(__name__)

# Every ProfileSnapshot column except the identity/timestamp ones and
# is_verified itself -- carried forward unchanged from the latest snapshot.
_CARRY_FORWARD_FIELDS = [
    "followers", "following", "posts",
    "biography", "biography_with_entities", "bio_links", "pronouns", "external_url",
    "is_business_account", "is_professional_account",
    "category_name", "category_enum", "overall_category_name",
    "business_contact_method", "business_email", "business_phone_number",
    "highlight_reel_count", "has_clips", "has_guides", "has_channel",
    "mutual_followers_count", "is_meta_verified", "hides_like_view_counts",
    "has_ar_effects", "business_category_name",
    "total_views", "subscribers_hidden", "platform_metadata",
]


class VerifyBadgeProcessor:
    def __init__(self, message: ScrapeJobMessage):
        self.message = message
        self._account = None
        self._account_repo: InstagramAccountRepo | None = None

    async def process(self):
        start_time = time.perf_counter()
        async with get_session() as session:
            job = await session.get(ScrapeJob, self.message.job_id)
            if not job:
                logger.error("Verify job not found", job_id=self.message.job_id)
                return

            job.status = "running"
            job.started_at = datetime.now(timezone.utc)
            await session.commit()

            if self.message.platform != "youtube":
                self._account_repo = InstagramAccountRepo(session)
                self._account = await self._account_repo.acquire_healthy_account(worker_id=WORKER_ID)
                if self._account is None:
                    # Never got to attempt anything -- same "don't spend a
                    # retry on a pool that was never tried" convention as
                    # NoUsableYouTubeKeyError/NoUsableInstagramTokenError.
                    logger.warning("No healthy Instagram accounts available for verify job -- will retry")
                    job.status = "retry_pending"
                    job.error_message = "no healthy Instagram accounts available"
                    job.finished_at = datetime.now(timezone.utc)
                    job.duration_s = time.perf_counter() - start_time
                    await session.commit()
                    return

            outcome = "success"
            account_at_fault = True
            retry_after: int | None = None
            try:
                is_verified = await self._fetch_is_verified(session)
                wrote = await self._write_snapshot(session, is_verified)
                job.error_message = (
                    None if wrote else "no prior snapshot to update -- influencer has never been scraped"
                )
            except InfluencerHandleNotFoundError as e:
                # Not the account's fault -- and retrying would fail
                # identically forever, so this fails outright rather than
                # going through retry_pending. Doesn't deactivate the
                # influencer (unlike a full scrape's handling of the same
                # error): a single verify check isn't enough confirmation
                # for that heavier, harder-to-reverse call.
                logger.warning("Verify job found no such handle", handle=self.message.handle)
                outcome = "success"
                account_at_fault = False
                job.error_message = str(e)
            except ScraperBlockedError as e:
                logger.exception("Verify job blocked", exc_info=e)
                outcome = "blocked"
                job.error_message = str(e)
            except ScraperRateLimitError as e:
                logger.exception("Verify job rate limited", exc_info=e)
                outcome = "rate_limited"
                retry_after = e.context.get("retry_after")
                job.error_message = str(e)
            except YouTubeChannelPageError as e:
                logger.exception("Verify job failed reading the YouTube channel page", exc_info=e)
                outcome = "error"
                job.error_message = str(e)
            except Exception as e:
                logger.exception("Verify job failed", exc_info=e)
                outcome = "error"
                job.error_message = str(e)
            finally:
                if outcome != "success":
                    job.retry_count += 1
                    job.status = (
                        "retry_pending" if job.retry_count < settings.SCRAPER_MAX_RETRIES else "failed"
                    )
                else:
                    job.status = "completed"
                job.finished_at = datetime.now(timezone.utc)
                job.duration_s = time.perf_counter() - start_time
                await session.commit()
                if self._account_repo is not None and self._account is not None:
                    release_outcome = "success" if (not account_at_fault) else outcome
                    await self._account_repo.release(self._account.id, release_outcome, retry_after=retry_after)

    async def _fetch_is_verified(self, session: AsyncSession) -> bool:
        if self.message.platform == "youtube":
            influencer = await session.get(Influencer, self.message.influencer_id)
            if influencer is not None and influencer.platform_user_id:
                return await fetch_is_verified(channel_id=influencer.platform_user_id)
            return await fetch_is_verified(handle=self.message.handle)

        # Instagram: self._account/_account_repo were already acquired in
        # process() before this try block, same "check availability first"
        # shape as InstagramEnrichProcessor.process.
        client = InstagramClient(
            cookies=self._account_repo.decrypt_cookies(self._account),
            user_agent=self._account.user_agent,
            proxy=self._account_repo.decrypt_proxy(self._account),
        )
        try:
            raw_user = await client.get_user_info(self.message.handle)
            parsed_user = InstagramParser.parse_user_info(raw_user)
            return parsed_user.is_verified
        finally:
            await client.close()

    async def _write_snapshot(self, session: AsyncSession, is_verified: bool) -> bool:
        latest = (
            await session.execute(
                select(ProfileSnapshot)
                .where(ProfileSnapshot.influencer_id == self.message.influencer_id)
                .order_by(ProfileSnapshot.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if latest is None:
            return False

        session.add(
            ProfileSnapshot(
                influencer_id=self.message.influencer_id,
                is_verified=is_verified,
                **{field: getattr(latest, field) for field in _CARRY_FORWARD_FIELDS},
            )
        )
        await session.commit()
        return True
