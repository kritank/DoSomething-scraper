from datetime import date, datetime, timedelta, timezone
from typing import Sequence

from sqlalchemy import Row, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.credential_health_snapshot import CredentialHealthSnapshot
from app.models.instagram_account import InstagramAccount
from app.models.instagram_api_token import InstagramApiToken
from app.models.youtube_api_key import YouTubeApiKey


class CredentialHealthRepo:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def record_snapshot(self) -> int:
        """Snapshots every currently-registered Instagram account and
        YouTube key's health in one pass -- called once per
        CRON_RETRY_FAILED tick by app.scheduler.runner.snapshot_credential_health.
        Returns the number of snapshot rows written."""
        accounts = (await self.session.execute(select(InstagramAccount))).scalars().all()
        keys = (await self.session.execute(select(YouTubeApiKey))).scalars().all()
        tokens = (await self.session.execute(select(InstagramApiToken))).scalars().all()

        rows = [
            CredentialHealthSnapshot(
                platform="instagram",
                label=a.username,
                status=a.status,
                failure_count=a.failure_count,
                instagram_account_id=a.id,
            )
            for a in accounts
        ] + [
            CredentialHealthSnapshot(
                platform="youtube",
                label=k.label,
                status=k.status,
                failure_count=k.failure_count,
                quota_used_today=k.quota_used_today,
                youtube_api_key_id=k.id,
            )
            for k in keys
        ] + [
            # Distinct platform value ("instagram_api", not "instagram")
            # -- see CredentialHealthSnapshot.instagram_api_token_id's
            # comment for why existing platform="instagram" queries must
            # keep meaning "the cookie pool" only.
            CredentialHealthSnapshot(
                platform="instagram_api",
                label=t.label,
                status=t.status,
                failure_count=t.failure_count,
                buc_usage_pct=t.buc_usage_pct,
                instagram_api_token_id=t.id,
            )
            for t in tokens
        ]
        if not rows:
            return 0
        self.session.add_all(rows)
        await self.session.commit()
        return len(rows)

    async def get_daily_summary(self, start_date: date, end_date: date) -> Sequence[Row]:
        """One row per (day, platform, status): how many of that day's
        snapshots landed in that status. A credential that spent the whole
        day "active" contributes ~144 snapshots (one per 10-minute tick) to
        the active bucket; one that flipped to quota_exhausted for an hour
        shows up as a visible band of snapshots in that status for that
        day -- this is what actually surfaces exhaustion/checkpoint
        *periods*, not just current state.
        """
        range_start = datetime.combine(start_date, datetime.min.time()).replace(tzinfo=timezone.utc)
        range_end = datetime.combine(end_date, datetime.min.time()).replace(tzinfo=timezone.utc) + timedelta(days=1)
        day = func.date_trunc("day", CredentialHealthSnapshot.snapshot_at).label("day")
        stmt = (
            select(
                day,
                CredentialHealthSnapshot.platform,
                CredentialHealthSnapshot.status,
                func.count().label("snapshot_count"),
            )
            .where(CredentialHealthSnapshot.snapshot_at >= range_start)
            .where(CredentialHealthSnapshot.snapshot_at < range_end)
            .group_by(day, CredentialHealthSnapshot.platform, CredentialHealthSnapshot.status)
            .order_by(day)
        )
        result = await self.session.execute(stmt)
        return result.all()
