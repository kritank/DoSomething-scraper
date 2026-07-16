import asyncio

from app.core.config import settings
from app.core.database import get_session
from app.core.exceptions import ScraperBlockedError, ScraperRateLimitError, ScraperTimeoutError
from app.core.logging import get_logger
from app.repositories.instagram_account_repo import InstagramAccountRepo
from app.scraper.client import InstagramClient

logger = get_logger(__name__)


async def revalidate_checkpoint_accounts(shutdown_event: asyncio.Event) -> None:
    """Runs alongside worker_loop/process_pending_logins in worker_runner.py.

    checkpoint_required is otherwise a terminal DB status -- acquire_healthy_account()
    only pulls "active" rows, and nothing ever flips a checkpointed account back.
    That's correct for accounts checkpointed at login (no session ever existed to
    retest), but wrong for accounts blocked mid-scrape by release(outcome="blocked"):
    their real session cookies are left in place, and the block may have been a
    transient/since-fixed false positive (see _is_checkpoint_response in
    app/scraper/client.py) or a checkpoint Instagram itself already cleared. This
    polls those accounts with one lightweight probe request each and restores any
    that actually still work, instead of requiring an operator to notice and
    manually re-run the registration script.
    """
    while not shutdown_event.is_set():
        async with get_session() as session:
            repo = InstagramAccountRepo(session)
            candidates = await repo.get_checkpointed_with_real_session()
            for account in candidates:
                cookies = repo.decrypt_cookies(account)
                proxy = repo.decrypt_proxy(account)
                client = InstagramClient.from_account(account, cookies, proxy=proxy)
                try:
                    await client.get_user_info(account.username)
                except (ScraperBlockedError, ScraperRateLimitError, ScraperTimeoutError) as e:
                    logger.info(
                        "Checkpointed account still not usable",
                        username=account.username,
                        error=type(e).__name__,
                    )
                    continue
                except Exception as e:
                    logger.warning(
                        "Checkpoint revalidation probe raised unexpectedly",
                        username=account.username,
                        error=str(e),
                    )
                    continue

                await repo.reactivate(account.id)
                logger.info(
                    "Checkpointed account revalidated, restored to active",
                    username=account.username,
                )

        await asyncio.sleep(settings.ACCOUNT_REVALIDATE_POLL_INTERVAL_S)
