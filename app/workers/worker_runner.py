import asyncio
import signal
import sys

from app.core.config import settings
from app.core.logging import configure_logging, get_logger
from app.core.database import init_db, close_db
from app.queue.factory import get_queue
from app.workers.job_processor import JobProcessor


configure_logging(log_level=settings.LOG_LEVEL, json_logs=not settings.DEBUG)
logger = get_logger(__name__)
shutdown_event = asyncio.Event()

def handle_sigterm(*args):
    logger.info("Received termination signal")
    shutdown_event.set()


async def _run_one(receipt: str, msg, queue) -> None:
    logger.info("Processing job", job_id=msg.job_id)
    try:
        await JobProcessor(msg).process()
    except Exception as e:
        logger.error("Job raised unhandled error", job_id=msg.job_id, error=str(e))
    else:
        logger.info("Completed job", job_id=msg.job_id)
    finally:
        await queue.delete(receipt)


async def worker_loop():
    logger.info("Starting worker loop", backend=settings.QUEUE_BACKEND, concurrency=settings.MAX_SCRAPER_WORKERS)
    queue = get_queue()

    while not shutdown_event.is_set():
        try:
            # Concurrency is still capped in practice by how many Instagram
            # accounts are healthy in the pool -- acquire_healthy_account()
            # hands out one account per concurrent job, so batch_size beyond
            # the account pool size just means extra jobs block waiting for
            # an account rather than truly running in parallel.
            messages = await queue.dequeue(batch_size=settings.MAX_SCRAPER_WORKERS)
            if messages:
                await asyncio.gather(*(_run_one(receipt, msg, queue) for receipt, msg in messages))
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
