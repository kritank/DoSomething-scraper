from typing import Protocol
from uuid import UUID

from pydantic import BaseModel


class ScrapeJobMessage(BaseModel):
    job_id: UUID
    influencer_id: UUID
    handle: str
    # "instagram" | "youtube" -- routes to the matching JobProcessor in
    # worker_runner._run_one. Defaulted so a message already in flight
    # during a deploy still decodes on the new worker image.
    platform: str = "instagram"
    # "scrape" (normal pipeline) | "enrich" (Instagram-only cookie
    # follow-on, PR3) -- see docs/INSTAGRAM_HYBRID_IMPLEMENTATION.md.
    job_type: str = "scrape"
    # "cookies" | "graph" -- Instagram only (ignored for platform=youtube).
    # Decided once at enqueue time by DispatchService, not re-derived in
    # worker_runner._run_one, so routing stays a pure function of the
    # message with no DB lookup (see PR2 §2.3's "choose the message-stamp
    # approach").
    backend: str = "cookies"


class QueueBackend(Protocol):
    async def enqueue(self, message: ScrapeJobMessage) -> str:
        """Enqueue a message and return the receipt handle/message ID."""
        ...

    async def dequeue(self, batch_size: int = 1) -> list[tuple[str, ScrapeJobMessage]]:
        """Dequeue messages, returning a list of (receipt_handle, message)."""
        ...

    async def delete(self, receipt_handle: str) -> None:
        """Delete a message from the queue after successful processing."""
        ...

    async def queue_depth(self) -> int:
        """Return the approximate number of messages in the queue."""
        ...
