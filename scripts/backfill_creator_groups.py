"""One-time backfill: give every influencer without a creator_id its own
Creator group, named after its handle (see InfluencerRepo.create, which
does this automatically for new influencers going forward -- this script
only needs to run once, to catch accounts registered before that changed).

Without a creator_id, an influencer has no combined creator profile page
("linked across N platforms") -- only the single-platform one. Two
already-unlinked influencers that happen to share the exact same handle
string across platforms (e.g. the same person's Instagram and YouTube both
literally called "mrbeast") get merged into one Creator here, same as
CreatorRepo.get_or_create_by_name's case-insensitive matching already does
for any other creator-name link in this app.

Purely DB-side (no external API calls) -- safe to re-run any time.

Usage:
    uv run python scripts/backfill_creator_groups.py
"""
from __future__ import annotations

import asyncio

from sqlalchemy import select

from app.core.database import get_session
from app.models.influencer import Influencer
from app.repositories.creator_repo import CreatorRepo


async def main() -> None:
    async with get_session() as session:
        stmt = select(Influencer).where(Influencer.creator_id.is_(None)).order_by(Influencer.handle)
        influencers = (await session.execute(stmt)).scalars().all()

        print(f"{len(influencers)} influencer(s) without a creator group.")
        creator_repo = CreatorRepo(session)
        for i, influencer in enumerate(influencers, start=1):
            name = influencer.handle.lstrip("@")
            creator = await creator_repo.get_or_create_by_name(name)
            influencer.creator_id = creator.id
            print(f"[{i}/{len(influencers)}] {influencer.handle} ({influencer.platform}) -> \"{creator.name}\"")
        await session.commit()
        print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
