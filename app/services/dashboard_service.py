from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.credential_health_repo import CredentialHealthRepo
from app.repositories.influencer_repo import InfluencerRepo
from app.repositories.queue_depth_repo import QueueDepthRepo
from app.repositories.scrape_job_repo import ScrapeJobRepo
from app.schemas.dashboard import (
    CredentialHealthBucket,
    CredentialHealthOut,
    DailyMetricBucket,
    DashboardMetricsOut,
    DashboardStatusRow,
    QueueDepthBucket,
    QueueDepthHistoryOut,
)


class DashboardService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.influencer_repo = InfluencerRepo(session)
        self.job_repo = ScrapeJobRepo(session)
        self.credential_health_repo = CredentialHealthRepo(session)
        self.queue_depth_repo = QueueDepthRepo(session)

    async def get_status_rows(self) -> list[DashboardStatusRow]:
        influencers = await self.influencer_repo.get_all_with_category()
        latest_jobs = await self.job_repo.get_latest_per_influencer()
        jobs_by_influencer = {job.influencer_id: job for job in latest_jobs}

        rows: list[DashboardStatusRow] = []
        for influencer in influencers:
            job = jobs_by_influencer.get(influencer.id)
            rows.append(
                DashboardStatusRow(
                    influencer_id=influencer.id,
                    handle=influencer.handle,
                    platform=influencer.platform,
                    creator_id=influencer.creator_id,
                    creator_name=influencer.creator.name if influencer.creator else None,
                    category_id=influencer.category_id,
                    category_name=influencer.category.name,
                    is_active=influencer.is_active,
                    backfill_completed=influencer.backfill_completed,
                    scrape_posts_since=influencer.scrape_posts_since,
                    last_job_id=job.id if job else None,
                    last_job_status=job.status if job else None,
                    last_job_started_at=job.started_at if job else None,
                    last_job_finished_at=job.finished_at if job else None,
                    last_job_duration_s=job.duration_s if job else None,
                    last_job_error_message=job.error_message if job else None,
                    last_job_posts_processed=job.posts_processed if job else None,
                    last_job_comments_processed=job.comments_processed if job else None,
                    last_job_scraper_account=job.scraper_account if job else None,
                )
            )
        return rows

    async def get_daily_metrics(self, start_date: date, end_date: date) -> DashboardMetricsOut:
        rows = await self.job_repo.get_daily_metrics(start_date, end_date)
        buckets = [
            DailyMetricBucket(
                date=row.day.date(),
                status=row.status,
                platform=row.platform,
                job_count=row.job_count,
                avg_duration_s=row.avg_duration_s,
                min_duration_s=row.min_duration_s,
                max_duration_s=row.max_duration_s,
                posts_processed=row.posts_processed,
                comments_processed=row.comments_processed,
                quota_units_used=row.quota_units_used,
            )
            for row in rows
        ]
        return DashboardMetricsOut(start_date=start_date, end_date=end_date, buckets=buckets)

    async def get_credential_health(self, start_date: date, end_date: date) -> CredentialHealthOut:
        rows = await self.credential_health_repo.get_daily_summary(start_date, end_date)
        buckets = [
            CredentialHealthBucket(
                date=row.day.date(),
                platform=row.platform,
                status=row.status,
                snapshot_count=row.snapshot_count,
            )
            for row in rows
        ]
        return CredentialHealthOut(start_date=start_date, end_date=end_date, buckets=buckets)

    async def get_queue_history(self, start_date: date, end_date: date) -> QueueDepthHistoryOut:
        rows = await self.queue_depth_repo.get_hourly_history(start_date, end_date)
        buckets = [
            QueueDepthBucket(
                hour=row.hour,
                avg_main_depth=row.avg_main_depth,
                max_main_depth=row.max_main_depth,
                avg_dlq_depth=row.avg_dlq_depth,
                max_dlq_depth=row.max_dlq_depth,
            )
            for row in rows
        ]
        return QueueDepthHistoryOut(start_date=start_date, end_date=end_date, buckets=buckets)
