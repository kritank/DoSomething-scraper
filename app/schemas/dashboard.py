from datetime import date, datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class DashboardStatusRow(BaseModel):
    influencer_id: UUID
    handle: str
    category_id: UUID
    category_name: str
    is_active: bool
    backfill_completed: bool
    last_job_id: Optional[UUID] = None
    last_job_status: Optional[str] = None
    last_job_started_at: Optional[datetime] = None
    last_job_finished_at: Optional[datetime] = None
    last_job_duration_s: Optional[float] = None
    last_job_error_message: Optional[str] = None
    last_job_posts_processed: Optional[int] = None
    # No ConfigDict(from_attributes=True) -- unlike every other *Out schema
    # in this repo, this is an aggregated view model assembled in
    # DashboardService by merging influencers + latest-job-per-influencer,
    # not mapped straight off one ORM object.


class DailyMetricBucket(BaseModel):
    date: date
    status: str
    job_count: int
    avg_duration_s: Optional[float] = None
    posts_processed: int


class DashboardMetricsOut(BaseModel):
    days: int
    buckets: list[DailyMetricBucket]
