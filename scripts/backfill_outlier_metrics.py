"""One-time backfill: populate post_outlier_metrics for every tracked
influencer's recent posts (docs/OUTLIERS_PLAN.md Phase 1). After this,
CreatorStatsService.recompute_outlier_metrics keeps rows fresh on every
scrape (see JobProcessor/YouTubeJobProcessor._recompute_outlier_metrics) --
this script only needs to run once, or after deploying Phase 1/2 scoring
changes to re-derive history.

Purely DB-side (no external API calls, no scraper accounts involved) --
safe to re-run any time, and fast relative to the scraper backfills in this
directory.

Usage:
    uv run python scripts/backfill_outlier_metrics.py [--platform instagram|youtube|all] [--limit N]
"""
from __future__ import annotations

import argparse
import asyncio

from sqlalchemy import select

from app.analytics.creator_stats import CreatorStatsService
from app.core.database import get_session
from app.models.influencer import Influencer


async def backfill(platform: str | None, limit: int | None) -> None:
    async with get_session() as session:
        stmt = select(Influencer.id, Influencer.handle, Influencer.platform).order_by(Influencer.handle)
        if platform:
            stmt = stmt.where(Influencer.platform == platform)
        if limit:
            stmt = stmt.limit(limit)
        influencers = (await session.execute(stmt)).all()

    print(f"{len(influencers)} influencer(s) to (re)score.")
    ok = 0
    for i, row in enumerate(influencers, start=1):
        async with get_session() as session:
            try:
                n = await CreatorStatsService(session).recompute_outlier_metrics(row.id)
                await session.commit()
                print(f"[{i}/{len(influencers)}] {row.handle} ({row.platform}): {n} post(s) scored")
                ok += 1
            except Exception as e:
                await session.rollback()
                print(f"[{i}/{len(influencers)}] {row.handle} ({row.platform}): error ({e})")

    print(f"Done: {ok}/{len(influencers)} influencers scored.")


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform", choices=["instagram", "youtube", "all"], default="all")
    parser.add_argument("--limit", type=int, default=None, help="Cap how many influencers to process.")
    args = parser.parse_args()

    platform = None if args.platform == "all" else args.platform
    await backfill(platform, args.limit)


if __name__ == "__main__":
    asyncio.run(main())
