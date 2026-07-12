from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.influencer_repo import InfluencerRepo
from app.repositories.scrape_job_repo import ScrapeJobRepo
from app.schemas.dashboard import DailyMetricBucket, DashboardMetricsOut, DashboardStatusRow


class DashboardService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.influencer_repo = InfluencerRepo(session)
        self.job_repo = ScrapeJobRepo(session)

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
                    category_id=influencer.category_id,
                    category_name=influencer.category.name,
                    is_active=influencer.is_active,
                    backfill_completed=influencer.backfill_completed,
                    last_job_id=job.id if job else None,
                    last_job_status=job.status if job else None,
                    last_job_started_at=job.started_at if job else None,
                    last_job_finished_at=job.finished_at if job else None,
                    last_job_duration_s=job.duration_s if job else None,
                    last_job_error_message=job.error_message if job else None,
                    last_job_posts_processed=job.posts_processed if job else None,
                    last_job_comments_processed=job.comments_processed if job else None,
                )
            )
        return rows

    async def get_daily_metrics(self, start_date: date, end_date: date) -> DashboardMetricsOut:
        rows = await self.job_repo.get_daily_metrics(start_date, end_date)
        buckets = [
            DailyMetricBucket(
                date=row.day.date(),
                status=row.status,
                job_count=row.job_count,
                avg_duration_s=row.avg_duration_s,
                posts_processed=row.posts_processed,
                comments_processed=row.comments_processed,
            )
            for row in rows
        ]
        return DashboardMetricsOut(start_date=start_date, end_date=end_date, buckets=buckets)
