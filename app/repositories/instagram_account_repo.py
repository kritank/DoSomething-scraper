from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Literal, Optional
from uuid import UUID

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func

from app.core.config import settings
from app.core.crypto import decrypt_json, encrypt_json
from app.core.exceptions import InstagramAccountNotFoundError
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

    async def get_all(self) -> list[InstagramAccount]:
        result = await self.session.execute(
            select(InstagramAccount).order_by(InstagramAccount.username)
        )
        return list(result.scalars().all())

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

    async def create_pending_login(
        self,
        username: str,
        password: str,
        user_agent: str,
        locale: str,
        tz: str,
    ) -> InstagramAccount:
        """Register a login-method account for async processing.

        Returns immediately with status="pending_login" -- the worker's
        background poll loop (app.workers.account_login_processor) picks
        this up, runs the actual Playwright login, and updates the row to
        active/checkpoint_required/login_failed. Upserts by username, same
        pattern as create()/create_checkpoint_required().
        """
        account = await self._get_by_username(username)
        if account is None:
            account = InstagramAccount(username=username)
            self.session.add(account)

        account.status = "pending_login"
        account.auth_method = "login"
        account.password_encrypted = encrypt_json({"password": password})
        account.session_cookies_encrypted = encrypt_json({})  # placeholder until login succeeds
        account.session_captured_at = datetime.now(timezone.utc)
        account.user_agent = user_agent
        account.locale = locale
        account.timezone = tz
        account.error_message = None
        await self.session.commit()
        return account

    async def mark_login_failed(self, username: str, detail: str) -> None:
        account = await self._get_by_username(username)
        if account is None:
            return
        account.status = "login_failed"
        account.error_message = detail
        await self.session.commit()

    async def get_pending_logins(self) -> list[InstagramAccount]:
        result = await self.session.execute(
            select(InstagramAccount).where(InstagramAccount.status == "pending_login")
        )
        return list(result.scalars().all())

    def decrypt_password(self, account: InstagramAccount) -> str:
        return decrypt_json(account.password_encrypted)["password"]

    async def update_status(self, account_id: UUID, status: str) -> InstagramAccount:
        """Manual active/disabled toggle -- the reversible, default 'remove'
        action. Does not touch cookies/password, just excludes the account
        from acquire_healthy_account()'s pool when disabled."""
        account = await self.session.get(InstagramAccount, account_id)
        if account is None:
            raise InstagramAccountNotFoundError(str(account_id))
        account.status = status
        await self.session.commit()
        return account

    async def delete(self, account_id: UUID) -> None:
        """Hard delete -- actually removes the row (cookies/password
        included). Irreversible."""
        account = await self.session.get(InstagramAccount, account_id)
        if account is None:
            return
        await self.session.delete(account)
        await self.session.commit()

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

    async def renew_lease(self, account_id: UUID) -> None:
        """Slides the lease forward -- called every JOB_HEARTBEAT_INTERVAL_S
        by JobProcessor._heartbeat for as long as its job is genuinely
        alive. Without this, a job legitimately running past
        ACCOUNT_LEASE_TIMEOUT_S would let release_stale_leases() free this
        SAME still-in-use account for a second job to acquire concurrently
        -- two scrapes sharing one live Instagram session at once."""
        await self.session.execute(
            update(InstagramAccount)
            .where(InstagramAccount.id == account_id)
            .values(
                lease_expires_at=datetime.now(timezone.utc)
                + timedelta(seconds=settings.ACCOUNT_LEASE_TIMEOUT_S)
            )
        )
        await self.session.commit()

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
