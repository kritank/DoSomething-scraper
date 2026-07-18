"""One-time backfill: populate Influencer.profile_pic_url for existing
influencers that don't have one yet (the field was added after most
influencers here were first scraped -- see the commit that introduced it).

Deliberately lighter than a full re-scrape: one profile-info call per
influencer, no posts/comments/snapshot writes. Safe to re-run --
influencers that already have a picture are skipped.

Only considers influencers with at least one prior *completed* scrape job
-- i.e. an account we've genuinely scraped real data for before, not one
that was added but never successfully resolved (wrong/unverified handle),
or synthetic seed/demo data that was never real-scraped at all (see
scripts/seed_demo_influencers.py). Without this filter, a demo handle that
happens to collide with someone's real Instagram username would get that
unrelated real person's photo attached to fabricated stats.

Instagram accounts are a shared, rate-limited resource (unlike YouTube API
keys, which are swapped/rotated automatically by YouTubeClient) -- this
walks the Instagram queue serially, one account lease at a time, with a
polite delay between requests, and stops immediately (rather than
continuing to burn through the rest of the queue) the moment a request
comes back blocked/rate-limited, since that's a sign the shared account is
in trouble and needs a human to look at it, not more traffic.

Usage:
    uv run python scripts/backfill_profile_pics.py [--platform instagram|youtube|all] [--limit N]
"""
from __future__ import annotations

import argparse
import asyncio
import random

from sqlalchemy import select

from app.core.database import get_session
from app.core.exceptions import (
    InfluencerNotFoundError,
    NoUsableYouTubeKeyError,
    ScraperBlockedError,
    ScraperRateLimitError,
)
from app.models.influencer import Influencer
from app.models.scrape_job import ScrapeJob
from app.repositories.instagram_account_repo import InstagramAccountRepo
from app.scraper.client import InstagramClient
from app.scraper.parser import InstagramParser
from app.scraper.youtube_client import YouTubeClient
from app.scraper.youtube_parser import YouTubeParser
from app.workers import youtube_key_provider as ykp
from app.workers.job_common import WORKER_ID

# Deliberately generous, randomized gap between Instagram requests -- this
# is a cosmetic backfill, not a time-sensitive scrape, so there's no reason
# to run it at the same pace as real scrape jobs and no upside to looking
# like a burst to Instagram's anti-abuse detection.
INSTAGRAM_DELAY_RANGE_S = (4.0, 9.0)


async def backfill_instagram(limit: int | None) -> None:
    async with get_session() as session:
        stmt = select(Influencer).where(
            Influencer.platform == "instagram",
            Influencer.profile_pic_url.is_(None),
            Influencer.id.in_(
                select(ScrapeJob.influencer_id).where(ScrapeJob.status == "completed")
            ),
        ).order_by(Influencer.handle)
        if limit:
            stmt = stmt.limit(limit)
        influencers = (await session.execute(stmt)).scalars().all()

    print(f"Instagram: {len(influencers)} influencer(s) missing a profile picture.")
    ok = skipped = failed = 0

    for i, influencer in enumerate(influencers, start=1):
        async with get_session() as session:
            account_repo = InstagramAccountRepo(session)
            account = await account_repo.acquire_healthy_account(worker_id=WORKER_ID)
            if account is None:
                print(f"[{i}/{len(influencers)}] {influencer.handle}: no healthy Instagram account available -- stopping.")
                break

            client = InstagramClient(
                cookies=account_repo.decrypt_cookies(account),
                user_agent=account.user_agent,
                proxy=account_repo.decrypt_proxy(account),
            )
            outcome = "success"
            account_at_fault = True
            try:
                raw_user = await client.get_user_info(influencer.handle)
                parsed_user = InstagramParser.parse_user_info(raw_user)
                # Re-fetch inside this session so the update lands on a row
                # attached to *this* transaction.
                row = await session.get(Influencer, influencer.id)
                if row.platform_user_id is None and parsed_user.pk:
                    row.platform_user_id = str(parsed_user.pk)
                if parsed_user.profile_pic_url:
                    row.profile_pic_url = parsed_user.profile_pic_url
                    print(f"[{i}/{len(influencers)}] {influencer.handle}: ok")
                    ok += 1
                else:
                    print(f"[{i}/{len(influencers)}] {influencer.handle}: no picture in response, skipped")
                    skipped += 1
                await session.commit()
            except InfluencerNotFoundError:
                account_at_fault = False
                print(f"[{i}/{len(influencers)}] {influencer.handle}: handle not found, skipped")
                skipped += 1
            except ScraperBlockedError as e:
                outcome = "blocked"
                failed += 1
                print(f"[{i}/{len(influencers)}] {influencer.handle}: BLOCKED ({e}) -- stopping.")
                await account_repo.release(account.id, outcome)
                await client.close()
                break
            except ScraperRateLimitError as e:
                outcome = "rate_limited"
                failed += 1
                print(f"[{i}/{len(influencers)}] {influencer.handle}: RATE LIMITED ({e}) -- stopping.")
                await account_repo.release(account.id, outcome, retry_after=e.context.get("retry_after"))
                await client.close()
                break
            except Exception as e:
                outcome = "error"
                failed += 1
                print(f"[{i}/{len(influencers)}] {influencer.handle}: error ({e})")
            finally:
                await client.close()

            release_outcome = "success" if (outcome == "success" or not account_at_fault) else outcome
            await account_repo.release(account.id, release_outcome)

        await asyncio.sleep(random.uniform(*INSTAGRAM_DELAY_RANGE_S))

    print(f"Instagram done: {ok} updated, {skipped} skipped, {failed} failed.")


async def backfill_youtube(limit: int | None) -> None:
    async with get_session() as session:
        stmt = select(Influencer).where(
            Influencer.platform == "youtube",
            Influencer.profile_pic_url.is_(None),
            Influencer.id.in_(
                select(ScrapeJob.influencer_id).where(ScrapeJob.status == "completed")
            ),
        ).order_by(Influencer.handle)
        if limit:
            stmt = stmt.limit(limit)
        influencers = (await session.execute(stmt)).scalars().all()

    print(f"YouTube: {len(influencers)} influencer(s) missing a profile picture.")
    ok = skipped = failed = 0

    for i, influencer in enumerate(influencers, start=1):
        client = YouTubeClient(
            key_provider=ykp.provide_key,
            usage_recorder=ykp.record_usage,
            key_exhauster=ykp.mark_exhausted,
            key_invalidator=ykp.mark_invalid,
        )
        try:
            if influencer.platform_user_id:
                raw_channel = await client.get_channel(channel_id=influencer.platform_user_id)
            else:
                raw_channel = await client.get_channel(handle=influencer.handle)
            channel = YouTubeParser.parse_channel(raw_channel)
            if not channel.channel_id:
                print(f"[{i}/{len(influencers)}] {influencer.handle}: no channel found, skipped")
                skipped += 1
                continue
            async with get_session() as session:
                row = await session.get(Influencer, influencer.id)
                if row.platform_user_id is None:
                    row.platform_user_id = channel.channel_id
                if channel.thumbnail_url:
                    row.profile_pic_url = channel.thumbnail_url
                    print(f"[{i}/{len(influencers)}] {influencer.handle}: ok")
                    ok += 1
                else:
                    print(f"[{i}/{len(influencers)}] {influencer.handle}: no thumbnail in response, skipped")
                    skipped += 1
                await session.commit()
        except NoUsableYouTubeKeyError:
            print(f"[{i}/{len(influencers)}] {influencer.handle}: no usable YouTube API key -- stopping.")
            break
        except Exception as e:
            failed += 1
            print(f"[{i}/{len(influencers)}] {influencer.handle}: error ({e})")

    print(f"YouTube done: {ok} updated, {skipped} skipped, {failed} failed.")


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform", choices=["instagram", "youtube", "all"], default="all")
    parser.add_argument("--limit", type=int, default=None, help="Cap how many influencers to process per platform this run.")
    args = parser.parse_args()

    if args.platform in ("instagram", "all"):
        await backfill_instagram(args.limit)
    if args.platform in ("youtube", "all"):
        await backfill_youtube(args.limit)


if __name__ == "__main__":
    asyncio.run(main())
