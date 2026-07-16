import asyncio
import random
import time


class TokenBucketRateLimiter:
    """Paces every outbound request against one account/session/key.

    Replaces per-coroutine `sleep(random(min, max))` calls: those pace each
    caller independently, so N concurrent tasks sharing one client (e.g.
    JobProcessor.COMMENT_SYNC_CONCURRENCY) produce an aggregate request rate
    N times higher than intended. A single bucket shared by the client
    makes the *aggregate* rate against the account/key the thing that's
    actually bounded, regardless of how many coroutines are drawing from it.

    Shared by InstagramClient (app.scraper.client) and YouTubeClient
    (app.scraper.youtube_client) -- the pacing mechanics are identical even
    though what's being paced against (a scraped session vs. an official
    API key) is completely different.
    """

    def __init__(self, rate_per_s: float, burst: int):
        self.rate_per_s = rate_per_s
        self.capacity = float(burst)
        self._tokens = float(burst)
        self._updated_at = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            while True:
                now = time.monotonic()
                elapsed = now - self._updated_at
                self._updated_at = now
                self._tokens = min(self.capacity, self._tokens + elapsed * self.rate_per_s)
                if self._tokens >= 1:
                    self._tokens -= 1
                    return
                wait_s = (1 - self._tokens) / self.rate_per_s
                wait_s += random.uniform(0, wait_s * 0.2)  # jitter -- looks less like a bot
                await asyncio.sleep(wait_s)
