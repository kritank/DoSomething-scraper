import asyncio
import signal
import sys

from app.core.config import settings
from app.core.logging import get_logger
from app.core.database import init_db, close_db
from app.queue.factory import get_queue
from app.workers.job_processor import JobProcessor


logger = get_logger(__name__)
shutdown_event = asyncio.Event()

def handle_sigterm(*args):
    logger.info("Received termination signal")
    shutdown_event.set()


async def worker_loop():
    logger.info("Starting worker loop", backend=settings.QUEUE_BACKEND)
    queue = get_queue()
    
    while not shutdown_event.is_set():
        try:
            messages = await queue.dequeue(batch_size=1)
            for receipt, msg in messages:
                logger.info("Processing job", job_id=msg.job_id)
                processor = JobProcessor(msg)
                await processor.process()
                await queue.delete(receipt)
                logger.info("Completed job", job_id=msg.job_id)
        except Exception as e:
            logger.error("Error in worker loop", error=str(e))
            await asyncio.sleep(5)
        else:
            if not messages:
                await asyncio.sleep(2)


async def main():
    signal.signal(signal.SIGINT, handle_sigterm)
    signal.signal(signal.SIGTERM, handle_sigterm)
    
    await init_db()
    try:
        await worker_loop()
    finally:
        await close_db()


if __name__ == "__main__":
    asyncio.run(main())
