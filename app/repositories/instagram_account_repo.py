from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Literal, Optional
from uuid import UUID

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func

from app.core.config import settings
from app.core.crypto import decrypt_json, encrypt_json
from app.core.logging import get_logger
from app.models.instagram_account import InstagramAccount

logger = get_logger(__name__)

AccountOutcome = Literal["success", "rate_limited", "blocked", "error"]


class InstagramAccountRepo:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def _get_by_username(self, username: str) -> Optional[InstagramAccount]:
        stmt = select(InstagramAccount).where(InstagramAccount.username == username)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(
        self,
        username: str,
        cookies: dict[str, str],
        user_agent: str,
        locale: str,
        tz: str,
    ) -> InstagramAccount:
        """Register (or re-register) an account as active with a fresh session.

        Re-running the registration script for a username already in the
        pool -- e.g. after refreshing an expired session -- must update the
        existing row rather than fail on the unique username constraint.
        """
        account = await self._get_by_username(username)
        if account is None:
            account = InstagramAccount(username=username)
            self.session.add(account)

        account.status = "active"
        account.session_cookies_encrypted = encrypt_json(cookies)
        account.session_captured_at = datetime.now(timezone.utc)
        account.user_agent = user_agent
        account.locale = locale
        account.timezone = tz
        account.error_message = None
        account.failure_count = 0
        await self.session.commit()
        return account

    async def create_checkpoint_required(
        self, username: str, user_agent: str, locale: str, tz: str, detail: str
    ) -> InstagramAccount:
        """Record an account that needs manual 2FA/checkpoint completion.

        No cookies exist yet, so session_cookies_encrypted is a placeholder --
        this row is never eligible for acquire_healthy_account() (status
        isn't "active") until an operator manually resolves the challenge
        and re-runs the registration script. Re-running against a username
        already in the pool (e.g. the previous attempt also hit a
        checkpoint) must update that row rather than fail on the unique
        username constraint.
        """
        account = await self._get_by_username(username)
        if account is None:
            account = InstagramAccount(username=username)
            self.session.add(account)

        account.status = "checkpoint_required"
        account.session_cookies_encrypted = encrypt_json({})
        account.session_captured_at = datetime.now(timezone.utc)
        account.user_agent = user_agent
        account.locale = locale
        account.timezone = tz
        account.error_message = detail
        await self.session.commit()
        return account

    def decrypt_cookies(self, account: InstagramAccount) -> dict[str, str]:
        return decrypt_json(account.session_cookies_encrypted)

    async def acquire_healthy_account(self, worker_id: str) -> Optional[InstagramAccount]:
        """Atomically claim one healthy account for a single job.

        FOR UPDATE SKIP LOCKED guards the narrow claim race between
        concurrently-dequeuing workers; the status flip to "in_use"
        (committed immediately, in this same short transaction) is what
        actually prevents two jobs running concurrently on one IG session
        for the lifetime of the job -- the row lock itself is released at
        commit.
        """
        stmt = (
            select(InstagramAccount)
            .where(InstagramAccount.status == "active")
            .where(
                or_(
                    InstagramAccount.cooldown_until.is_(None),
                    InstagramAccount.cooldown_until <= func.now(),
                )
            )
            .order_by(InstagramAccount.last_used_at.asc().nulls_first())
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        result = await self.session.execute(stmt)
        account = result.scalar_one_or_none()
        if account is None:
            return None

        account.status = "in_use"
        account.locked_by = worker_id
        account.last_used_at = datetime.now(timezone.utc)
        account.lease_expires_at = datetime.now(timezone.utc) + timedelta(
            seconds=settings.ACCOUNT_LEASE_TIMEOUT_S
        )
        await self.session.commit()
        return account

    async def release(
        self,
        account_id: UUID,
        outcome: AccountOutcome,
        retry_after: int | None = None,
    ) -> None:
        account = await self.session.get(InstagramAccount, account_id)
        if account is None:
            return

        account.locked_by = None
        account.lease_expires_at = None

        if outcome == "success":
            account.status = "active"
            account.failure_count = 0
            account.last_success_at = datetime.now(timezone.utc)
            account.error_message = None
        elif outcome == "rate_limited":
            account.status = "active"
            account.failure_count += 1
            account.last_failure_at = datetime.now(timezone.utc)
            cooldown_s = retry_after or 60
            account.cooldown_until = datetime.now(timezone.utc) + timedelta(seconds=cooldown_s)
        elif outcome == "blocked":
            account.status = "checkpoint_required"
            account.failure_count += 1
            account.last_failure_at = datetime.now(timezone.utc)
            account.error_message = "Blocked by Instagram (401/403) -- session may need to be refreshed."
            logger.error(
                "Instagram account blocked, needs manual re-verification",
                username=account.username,
            )
        else:  # "error"
            account.status = "active"
            account.failure_count += 1
            account.last_failure_at = datetime.now(timezone.utc)

        if account.status == "active" and account.failure_count >= settings.ACCOUNT_MAX_CONSECUTIVE_FAILURES:
            account.status = "disabled"
            logger.error(
                "Instagram account disabled after repeated failures",
                username=account.username,
                failure_count=account.failure_count,
            )

        await self.session.commit()

    async def release_stale_leases(self) -> int:
        """Crash-recovery valve: a worker that dies mid-job leaves its
        account stuck in "in_use" forever otherwise."""
        stmt = (
            update(InstagramAccount)
            .where(InstagramAccount.status == "in_use")
            .where(InstagramAccount.lease_expires_at < func.now())
            .values(status="active", locked_by=None, lease_expires_at=None)
        )
        result = await self.session.execute(stmt)
        await self.session.commit()
        return result.rowcount or 0
