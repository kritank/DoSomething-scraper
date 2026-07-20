"""One-time backfill: set a sensible Influencer.account_type ("business" |
"individual") for accounts registered before the field existed (see
docs -- account_type is nullable=False, server_default="individual", so
every existing row already reads "individual" until this runs).

Instagram exposes a real signal for this -- ProfileSnapshot.is_business_account
(and is_professional_account, which Instagram also sets for Creator accounts,
functionally a business-adjacent account type) from the most recent scrape.
Only rows where that signal says "business" are touched; everything else
keeps the "individual" default. YouTube has no equivalent public signal, so
YouTube influencers are left untouched -- correct via manual edit (the same
per-influencer "Type" field the dashboard now exposes) is the right call
there, not a guess.

Purely DB-side (no external API calls) -- safe to re-run any time.

Usage:
    uv run python scripts/backfill_account_type.py
"""
from __future__ import annotations

import asyncio

from sqlalchemy import select

from app.core.database import get_session
from app.models.influencer import Influencer
from app.models.snapshot import ProfileSnapshot


async def main() -> None:
    async with get_session() as session:
        latest_snapshot = (
            select(ProfileSnapshot)
            .distinct(ProfileSnapshot.influencer_id)
            .order_by(ProfileSnapshot.influencer_id, ProfileSnapshot.scraped_at.desc(), ProfileSnapshot.created_at.desc())
            .subquery()
        )
        stmt = (
            select(Influencer)
            .join(latest_snapshot, latest_snapshot.c.influencer_id == Influencer.id)
            .where(
                Influencer.platform == "instagram",
                Influencer.account_type != "business",
                (latest_snapshot.c.is_business_account.is_(True)) | (latest_snapshot.c.is_professional_account.is_(True)),
            )
        )
        influencers = (await session.execute(stmt)).scalars().all()

        print(f"{len(influencers)} Instagram influencer(s) to mark as business.")
        for i, influencer in enumerate(influencers, start=1):
            influencer.account_type = "business"
            print(f"[{i}/{len(influencers)}] {influencer.handle}: individual -> business")
        await session.commit()
        print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
