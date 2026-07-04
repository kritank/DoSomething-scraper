from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
from typing import Iterable

from sqlalchemy import select

from app.core.database import get_session
from app.models.category import Category
from app.models.influencer import Influencer
from app.models.scrape_job import ScrapeJob
from app.queue.base import ScrapeJobMessage
from app.repositories.category_repo import CategoryRepo
from app.repositories.influencer_repo import InfluencerRepo
from app.schemas.category import CategoryCreate
from app.schemas.influencer import InfluencerCreate
from app.workers.job_processor import JobProcessor


@dataclass(frozen=True)
class SeedProfile:
    category: str
    handle: str


DEFAULT_PROFILES: tuple[SeedProfile, ...] = (
    SeedProfile("Fitness", "cristiano"),
    SeedProfile("Fitness", "mikeohearn"),
    SeedProfile("Finance", "garyvee"),
    SeedProfile("Finance", "kevinolearytv"),
    SeedProfile("Food", "gordonramsay"),
    SeedProfile("Food", "jamieoliver"),
    SeedProfile("Travel", "muradosmann"),
    SeedProfile("Travel", "thebucketlistfamily"),
    SeedProfile("Beauty", "nikkietutorials"),
    SeedProfile("Beauty", "hudabeauty"),
    SeedProfile("India Entertainment", "carryminati"),
    SeedProfile("India Entertainment", "bhuvan.bam22"),
    SeedProfile("India Entertainment", "ashishchanchlani"),
)


async def _get_or_create_category(repo: CategoryRepo, name: str) -> Category:
    stmt = select(Category).where(Category.name == name)
    result = await repo.session.execute(stmt)
    existing = result.scalar_one_or_none()
    if existing:
        return existing
    return await repo.create(CategoryCreate(name=name))


async def _get_or_create_influencer(
    repo: InfluencerRepo, category_id, handle: str
) -> Influencer:
    stmt = select(Influencer).where(Influencer.handle == handle)
    result = await repo.session.execute(stmt)
    existing = result.scalar_one_or_none()
    if existing:
        return existing
    return await repo.create(InfluencerCreate(handle=handle, category_id=category_id))


async def seed_and_scrape(profiles: Iterable[SeedProfile], process_now: bool) -> None:
    async with get_session() as session:
        category_repo = CategoryRepo(session)
        influencer_repo = InfluencerRepo(session)

        category_cache: dict[str, Category] = {}
        influencer_count = 0

        for profile in profiles:
            category = category_cache.get(profile.category)
            if category is None:
                category = await _get_or_create_category(category_repo, profile.category)
                category_cache[profile.category] = category

            influencer = await _get_or_create_influencer(influencer_repo, category.id, profile.handle)
            influencer_count += 1
            print(f"seeded: @{influencer.handle} -> {category.name}")

            if process_now:
                job = ScrapeJob(influencer_id=influencer.id, status="queued")
                session.add(job)
                await session.commit()
                message = ScrapeJobMessage(job_id=job.id, influencer_id=influencer.id, handle=influencer.handle)
                print(f"scraping: @{influencer.handle}")
                await JobProcessor(message).process()

        print(f"done: {influencer_count} influencers processed")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed categories/influencers and optionally scrape them.")
    parser.add_argument(
        "--seed-only",
        action="store_true",
        help="Only seed records; skip the immediate scrape pass.",
    )
    parser.add_argument(
        "--category",
        action="append",
        dest="categories",
        help="Only process profiles in this category. Repeatable.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    profiles = DEFAULT_PROFILES
    if args.categories:
        profiles = tuple(p for p in profiles if p.category in args.categories)
    asyncio.run(seed_and_scrape(profiles, not args.seed_only))


if __name__ == "__main__":
    main()
