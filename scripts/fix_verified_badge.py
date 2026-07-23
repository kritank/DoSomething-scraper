"""One-time production data fix: restore ProfileSnapshot.is_verified for
Instagram influencers whose badge was wiped out by the Graph API pipeline.

Business Discovery (InstagramGraphJobProcessor._run_scrape) never exposes
is_verified -- before the fix in 5d6d8d3 ("Fix Instagram hybrid scraping
bugs..."), every Graph-sourced snapshot silently wrote is_verified=False
via the column default instead of carrying forward the influencer's real,
cookie-sourced value. Once that False landed, the *current* preserve-from-
prev-snapshot logic just kept copying the wrong value forward on every
later Graph scrape -- the code fix stops new corruption but can't repair
rows already written wrong, hence this one-time backfill.

Purely DB-side, no scraper calls: walks each Instagram influencer's
ProfileSnapshot history in order, treats a snapshot as Graph-sourced if a
RawResponse(endpoint="ig_graph_business_discovery") for the same handle
was written in the same transaction (identical created_at -- both rows
are added and committed together), and otherwise treats it as a truthful
cookie-sourced reading. Any Graph-sourced snapshot whose is_verified
disagrees with the most recent truthful reading is corrected back to that
value. Cookie-sourced snapshots are never touched.

Safe to re-run -- rows already matching their last truthful reading are
left alone.

Usage:
    uv run python scripts/fix_verified_badge.py [--limit N] [--dry-run]
"""
from __future__ import annotations

import argparse
import asyncio

from sqlalchemy import select

from app.core.database import get_session
from app.models.influencer import Influencer
from app.models.raw_response import RawResponse
from app.models.snapshot import ProfileSnapshot

GRAPH_ENDPOINT = "ig_graph_business_discovery"


async def fix_influencer(session, influencer: Influencer, dry_run: bool) -> int:
    snapshots = (
        await session.execute(
            select(ProfileSnapshot)
            .where(ProfileSnapshot.influencer_id == influencer.id)
            .order_by(ProfileSnapshot.created_at.asc())
        )
    ).scalars().all()
    if not snapshots:
        return 0

    graph_timestamps = set(
        (
            await session.execute(
                select(RawResponse.created_at).where(
                    RawResponse.handle == influencer.handle,
                    RawResponse.endpoint == GRAPH_ENDPOINT,
                )
            )
        ).scalars().all()
    )

    fixes = 0
    last_truthful: bool | None = None
    for snap in snapshots:
        is_graph_sourced = snap.created_at in graph_timestamps
        if not is_graph_sourced:
            last_truthful = snap.is_verified
            continue
        if last_truthful is not None and snap.is_verified != last_truthful:
            print(
                f"  {influencer.handle}: snapshot {snap.id} ({snap.scraped_at}) "
                f"is_verified {snap.is_verified} -> {last_truthful}"
            )
            if not dry_run:
                snap.is_verified = last_truthful
            fixes += 1
    return fixes


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=None, help="Cap how many influencers to scan.")
    parser.add_argument("--dry-run", action="store_true", help="Report what would change without writing.")
    args = parser.parse_args()

    async with get_session() as session:
        stmt = select(Influencer).where(Influencer.platform == "instagram").order_by(Influencer.handle)
        if args.limit:
            stmt = stmt.limit(args.limit)
        influencers = (await session.execute(stmt)).scalars().all()

    print(f"{len(influencers)} Instagram influencer(s) to check.")
    total_fixes = 0
    affected = 0
    for i, influencer in enumerate(influencers, start=1):
        async with get_session() as session:
            row = await session.get(Influencer, influencer.id)
            n = await fix_influencer(session, row, args.dry_run)
            if n:
                affected += 1
                total_fixes += n
                if not args.dry_run:
                    await session.commit()
            print(f"[{i}/{len(influencers)}] {influencer.handle}: {n} snapshot(s) {'would be ' if args.dry_run else ''}fixed")

    mode = "DRY RUN -- " if args.dry_run else ""
    print(f"{mode}Done: {total_fixes} snapshot(s) fixed across {affected} influencer(s).")


if __name__ == "__main__":
    asyncio.run(main())
