import asyncio
import signal
import sys

from app.core.config import settings
from app.core.logging import configure_logging, get_logger
from app.core.database import init_db, close_db
from app.queue.factory import get_queue
from app.workers.account_login_processor import process_pending_logins
from app.workers.account_revalidator import revalidate_checkpoint_accounts
from app.workers.instagram_enrich_processor import InstagramEnrichProcessor
from app.workers.instagram_graph_job_processor import InstagramGraphJobProcessor
from app.workers.job_processor import JobProcessor
from app.workers.youtube_job_processor import YouTubeJobProcessor


configure_logging(log_level=settings.LOG_LEVEL, json_logs=not settings.DEBUG)
logger = get_logger(__name__)
shutdown_event = asyncio.Event()

def handle_sigterm(*args):
    logger.info("Received termination signal")
    shutdown_event.set()


async def _run_one(receipt: str, msg, queue) -> None:
    logger.info("Processing job", job_id=msg.job_id, platform=msg.platform, job_type=msg.job_type, backend=msg.backend)
    try:
        if msg.job_type == "enrich":
            processor = InstagramEnrichProcessor(msg)
        elif msg.platform == "youtube":
            processor = YouTubeJobProcessor(msg)
        elif msg.backend == "graph":
            processor = InstagramGraphJobProcessor(msg)
        else:
            processor = JobProcessor(msg)
        await processor.process()
    except Exception as e:
        logger.error("Job raised unhandled error", job_id=msg.job_id, error=str(e))
    else:
        logger.info("Completed job", job_id=msg.job_id)
    finally:
        await queue.delete(receipt)


async def worker_loop():
    """Runs up to MAX_SCRAPER_WORKERS jobs concurrently as a continuously
    refilling pool, rather than dequeuing a batch and awaiting all of it
    before dequeuing again. That batch-gather shape had a head-of-line
    problem: one slow job (e.g. an influencer with a large comment
    backlog) held the other batch_size-1 slots idle for its entire
    duration, since no new message was pulled until every job in the
    batch finished. Here, a slot is refilled the instant its job
    completes, independent of how long its batch-mates take.

    Concurrency is still capped in practice by how many Instagram accounts
    are healthy in the pool -- acquire_healthy_account() hands out one
    account per concurrent job, so MAX_SCRAPER_WORKERS beyond the account
    pool size just means extra jobs block waiting for an account rather
    than truly running in parallel.
    """
    logger.info("Starting worker loop", backend=settings.QUEUE_BACKEND, concurrency=settings.MAX_SCRAPER_WORKERS)
    queue = get_queue()
    active: set[asyncio.Task] = set()

    while not shutdown_event.is_set():
        free_slots = settings.MAX_SCRAPER_WORKERS - len(active)
        if free_slots > 0:
            try:
                messages = await queue.dequeue(batch_size=free_slots)
            except Exception as e:
                logger.error("Error in worker loop", error=str(e))
                await asyncio.sleep(5)
                continue
            for receipt, msg in messages:
                active.add(asyncio.create_task(_run_one(receipt, msg, queue)))

        if not active:
            await asyncio.sleep(2)
            continue

        # Short timeout (not indefinite) so a full pool still re-checks
        # shutdown_event periodically instead of blocking on whichever
        # job happens to finish last.
        done, active = await asyncio.wait(active, timeout=2, return_when=asyncio.FIRST_COMPLETED)

    if active:
        # Let in-flight jobs finish their DB work before main() tears
        # down the connection pool in its finally: close_db() -- an
        # abandoned task mid-commit is corruption waiting to happen.
        logger.info("Waiting for in-flight jobs to finish before shutdown", count=len(active))
        await asyncio.gather(*active)


async def main():
    signal.signal(signal.SIGINT, handle_sigterm)
    signal.signal(signal.SIGTERM, handle_sigterm)
    
    await init_db()
    try:
        await asyncio.gather(
            worker_loop(),
            process_pending_logins(shutdown_event),
            revalidate_checkpoint_accounts(shutdown_event),
        )
    finally:
        await close_db()


if __name__ == "__main__":
    asyncio.run(main())
