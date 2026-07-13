"""
Populates categories/influencers/profile_snapshots/posts/post_metrics_snapshots
with synthetic data so the local dashboard and the public "Top Influencers"
page (GET /api/v1/influencers/top) have something to render.

Does NOT touch Instagram — unlike scripts/seed_and_scrape.py, this never
dispatches a real scrape job. Safe to run repeatedly; upserts by handle.
"""
from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.core.database import get_session
from app.models.category import Category
from app.models.influencer import Influencer
from app.models.post import Post
from app.models.snapshot import PostMetricsSnapshot, ProfileSnapshot


@dataclass(frozen=True)
class DemoProfile:
    category: str
    handle: str
    followers: int
    following: int
    posts: int
    is_verified: bool
    engagement_rate_pct: float  # target avg (likes+comments)/followers*100


DEMO_PROFILES: tuple[DemoProfile, ...] = (
    DemoProfile("Fitness", "ironpulse.fit", 2_450_000, 812, 640, True, 3.8),
    DemoProfile("Fitness", "coach.ren", 386_000, 1_204, 310, False, 5.1),
    DemoProfile("Finance", "wealthwithnina", 918_000, 340, 275, True, 4.2),
    DemoProfile("Finance", "themoneymindset", 145_000, 2_011, 190, False, 6.4),
    DemoProfile("Food", "kitchen.by.arjun", 1_120_000, 654, 980, True, 3.1),
    DemoProfile("Food", "spicetrail", 267_000, 890, 415, False, 5.7),
    DemoProfile("Travel", "wanderwithzoe", 3_040_000, 1_502, 720, True, 2.6),
    DemoProfile("Travel", "offbeatpaths", 92_000, 610, 205, False, 7.2),
    DemoProfile("Beauty", "glowbyleah", 1_780_000, 420, 560, True, 3.4),
    DemoProfile("Beauty", "barefacedbina", 214_000, 980, 330, False, 6.0),
    DemoProfile("India Entertainment", "meme.masti", 4_210_000, 220, 1_240, True, 2.9),
    DemoProfile("India Entertainment", "desi.dost", 680_000, 1_890, 505, False, 4.8),
)


async def _get_or_create_category(session, name: str) -> Category:
    result = await session.execute(select(Category).where(Category.name == name))
    existing = result.scalar_one_or_none()
    if existing:
        return existing
    category = Category(name=name)
    session.add(category)
    await session.flush()
    return category


async def _get_or_create_influencer(session, category_id, handle: str) -> Influencer:
    result = await session.execute(select(Influencer).where(Influencer.handle == handle))
    existing = result.scalar_one_or_none()
    if existing:
        return existing
    influencer = Influencer(handle=handle, category_id=category_id, backfill_completed=True)
    session.add(influencer)
    await session.flush()
    return influencer


async def _seed_snapshot(session, influencer: Influencer, profile: DemoProfile) -> None:
    now = datetime.now(timezone.utc)
    snapshot = ProfileSnapshot(
        influencer_id=influencer.id,
        scraped_at=now.date(),
        followers=profile.followers,
        following=profile.following,
        posts=profile.posts,
        is_verified=profile.is_verified,
        overall_category_name=profile.category,
        updated_at=now,
    )
    session.add(snapshot)


async def _seed_posts(session, influencer: Influencer, profile: DemoProfile) -> None:
    """Seeds a handful of recent posts + one metrics snapshot each, sized so
    avg(likes+comments)/followers lands near the profile's target engagement rate.

    Skips entirely if this influencer already has demo posts, so re-running
    the script doesn't hit the posts.shortcode unique constraint."""
    existing = await session.execute(
        select(Post.id).where(Post.influencer_id == influencer.id).limit(1)
    )
    if existing.scalar_one_or_none() is not None:
        return

    target_total = profile.followers * (profile.engagement_rate_pct / 100)
    now = datetime.now(timezone.utc)
    for i in range(ENGAGEMENT_SAMPLE_SIZE):
        jitter = random.uniform(0.85, 1.15)
        total = target_total * jitter
        comments = max(1, int(total * 0.08))
        likes = max(1, int(total - comments))

        post = Post(
            influencer_id=influencer.id,
            shortcode=f"{influencer.handle}-demo-{i}",
            posted_at=now - timedelta(days=i * 2),
        )
        session.add(post)
        await session.flush()

        session.add(
            PostMetricsSnapshot(
                post_id=post.id,
                scraped_at=now.date(),
                likes=likes,
                comments=comments,
            )
        )


ENGAGEMENT_SAMPLE_SIZE = 12


async def seed_demo(profiles=DEMO_PROFILES) -> None:
    async with get_session() as session:
        category_cache: dict[str, Category] = {}
        for profile in profiles:
            category = category_cache.get(profile.category)
            if category is None:
                category = await _get_or_create_category(session, profile.category)
                category_cache[profile.category] = category

            influencer = await _get_or_create_influencer(session, category.id, profile.handle)
            await _seed_snapshot(session, influencer, profile)
            await _seed_posts(session, influencer, profile)
            print(f"seeded: @{influencer.handle} ({profile.category}) — {profile.followers:,} followers")

        print(f"done: {len(profiles)} demo influencers seeded")


if __name__ == "__main__":
    asyncio.run(seed_demo())
