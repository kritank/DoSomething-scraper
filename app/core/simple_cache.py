"""In-process TTL cache for expensive, non-personalized public read
endpoints (the Top Influencers leaderboard, creator profiles).

Deliberately NOT Redis-backed: QUEUE_BACKEND=redis is local-dev-only
(production runs on SQS -- see app/core/config.py's QUEUE_BACKEND
comment), so a shared cache can't assume Redis is provisioned in every
deployment. A per-process cache still cuts DB load dramatically for these
routes -- their backing data only changes via periodic scrape jobs, not
per-request writes, so bounded staleness from a short TTL is a deliberate
tradeoff, not a correctness risk. Pairs with the Cache-Control header set
on the same routes, which lets Cloudflare absorb most repeat requests
before they ever reach this process.
"""

import asyncio
import time
from typing import Any, Awaitable, Callable

_store: dict[str, tuple[float, Any]] = {}
_locks: dict[str, asyncio.Lock] = {}


def _lock_for(key: str) -> asyncio.Lock:
    lock = _locks.get(key)
    if lock is None:
        lock = asyncio.Lock()
        _locks[key] = lock
    return lock


async def get_or_set(key: str, ttl_seconds: float, compute: Callable[[], Awaitable[Any]]) -> Any:
    """Returns the cached value for `key` if still fresh, else awaits
    `compute()` and caches the result. A per-key lock ensures concurrent
    requests for the same cold key wait for one computation instead of
    all hitting the DB at once (cache stampede protection)."""
    now = time.monotonic()
    hit = _store.get(key)
    if hit is not None and hit[0] > now:
        return hit[1]

    async with _lock_for(key):
        # Re-check: another waiter may have already populated it while we
        # were blocked on the lock.
        hit = _store.get(key)
        if hit is not None and hit[0] > now:
            return hit[1]
        value = await compute()
        _store[key] = (now + ttl_seconds, value)
        return value
