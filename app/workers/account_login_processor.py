import asyncio

from app.core.config import settings
from app.core.database import get_session
from app.core.logging import get_logger
from app.repositories.instagram_account_repo import InstagramAccountRepo
from app.scraper.login_automator import perform_login

logger = get_logger(__name__)


async def process_pending_logins(shutdown_event: asyncio.Event) -> None:
    """Runs alongside the main scrape-job dequeue loop in worker_runner.py.

    Polls every ACCOUNT_LOGIN_POLL_INTERVAL_S; processes pending logins one
    at a time -- perform_login() drives real Chromium (~10-40s, non-trivial
    memory on this t3.micro), and this is an admin-triggered, low-frequency
    action, so concurrent logins aren't worth the resource risk.
    """
    while not shutdown_event.is_set():
        async with get_session() as session:
            repo = InstagramAccountRepo(session)
            pending = await repo.get_pending_logins()
            for account in pending:
                logger.info("Processing pending login", username=account.username)
                password = repo.decrypt_password(account)
                proxy = repo.decrypt_proxy(account)
                try:
                    result = await perform_login(
                        account.username,
                        password,
                        account.user_agent,
                        account.locale,
                        account.timezone,
                        headless=True,
                        proxy=proxy,
                    )
                except Exception as e:
                    logger.error("Login automation raised", username=account.username, error=str(e))
                    await repo.mark_login_failed(account.username, str(e))
                    continue

                if result.status == "success":
                    cookies = {c["name"]: c["value"] for c in (result.cookies or [])}
                    await repo.create(
                        account.username, cookies, account.user_agent, account.locale, account.timezone
                    )
                    logger.info("Login succeeded", username=account.username)
                elif result.status == "checkpoint_required":
                    await repo.create_checkpoint_required(
                        account.username, account.user_agent, account.locale, account.timezone,
                        detail=result.detail or "Checkpoint required -- resolve manually.",
                    )
                    logger.warning("Login hit checkpoint", username=account.username, detail=result.detail)
                else:  # bad_credentials / unknown_failure
                    await repo.mark_login_failed(account.username, result.detail or result.status)
                    logger.warning(
                        "Login failed", username=account.username, status=result.status, detail=result.detail
                    )

        await asyncio.sleep(settings.ACCOUNT_LOGIN_POLL_INTERVAL_S)
