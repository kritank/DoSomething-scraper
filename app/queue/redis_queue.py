import json
from uuid import uuid4

import redis.asyncio as redis

from app.core.config import settings
from app.queue.base import ScrapeJobMessage


class RedisQueueBackend:
    """A lightweight async queue using Redis lists."""

    QUEUE_KEY = "viralytics:scrape_jobs"

    def __init__(self) -> None:
        self.redis = redis.from_url(settings.REDIS_URL, decode_responses=True)

    async def enqueue(self, message: ScrapeJobMessage) -> str:
        # Generate a fake receipt handle for Redis since it doesn't natively have them for lists
        receipt_handle = str(uuid4())
        payload = {
            "receipt_handle": receipt_handle,
            "message": message.model_dump(mode="json"),
        }
        await self.redis.lpush(self.QUEUE_KEY, json.dumps(payload))
        return receipt_handle

    async def dequeue(self, batch_size: int = 1) -> list[tuple[str, ScrapeJobMessage]]:
        results = []
        for _ in range(batch_size):
            # Non-blocking pop; in a real app you might use BRPOP with a timeout
            item = await self.redis.rpop(self.QUEUE_KEY)
            if not item:
                break
            
            data = json.loads(item)
            receipt = data["receipt_handle"]
            msg = ScrapeJobMessage(**data["message"])
            results.append((receipt, msg))
            
        return results

    async def delete(self, receipt_handle: str) -> None:
        # In this simple list-based implementation, rpop already removes the item.
        # We could use Redis Streams or Sorted Sets for a true ACK mechanism, 
        # but this is sufficient for local development.
        pass

    async def queue_depth(self) -> int:
        return await self.redis.llen(self.QUEUE_KEY)
