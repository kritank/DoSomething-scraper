from typing import Protocol
from uuid import UUID

from pydantic import BaseModel


class ScrapeJobMessage(BaseModel):
    job_id: UUID
    influencer_id: UUID
    handle: str


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
