from datetime import date, datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class DashboardStatusRow(BaseModel):
    influencer_id: UUID
    handle: str
    platform: str
    creator_id: Optional[UUID] = None
    creator_name: Optional[str] = None
    category_id: UUID
    category_name: str
    is_active: bool
    backfill_completed: bool
    scrape_posts_since: Optional[date] = None
    last_job_id: Optional[UUID] = None
    last_job_status: Optional[str] = None
    last_job_started_at: Optional[datetime] = None
    last_job_finished_at: Optional[datetime] = None
    last_job_duration_s: Optional[float] = None
    last_job_error_message: Optional[str] = None
    last_job_posts_processed: Optional[int] = None
    last_job_comments_processed: Optional[int] = None
    last_job_scraper_account: Optional[str] = None
    # No ConfigDict(from_attributes=True) -- unlike every other *Out schema
    # in this repo, this is an aggregated view model assembled in
    # DashboardService by merging influencers + latest-job-per-influencer,
    # not mapped straight off one ORM object.


class DailyMetricBucket(BaseModel):
    date: date
    status: str
    platform: str
    job_count: int
    avg_duration_s: Optional[float] = None
    min_duration_s: Optional[float] = None
    max_duration_s: Optional[float] = None
    posts_processed: int
    comments_processed: int
    # YouTube Data API quota units consumed -- None for Instagram buckets
    # (no quota concept there), never a fabricated 0.
    quota_units_used: Optional[int] = None


class DashboardMetricsOut(BaseModel):
    start_date: date
    end_date: date
    buckets: list[DailyMetricBucket]


class CredentialHealthBucket(BaseModel):
    date: date
    platform: str
    status: str
    # How many of that day's periodic snapshots landed in this status --
    # not a count of distinct credentials. A credential that spent an hour
    # in quota_exhausted contributes a visible run of snapshots in that
    # status for that day, surfacing the *period*, not just current state.
    snapshot_count: int


class CredentialHealthOut(BaseModel):
    start_date: date
    end_date: date
    buckets: list[CredentialHealthBucket]


class QueueDepthBucket(BaseModel):
    hour: datetime
    avg_main_depth: Optional[float] = None
    max_main_depth: Optional[int] = None
    # None wherever the backend has no DLQ concept (Redis) -- see
    # QueueDepthSnapshot.
    avg_dlq_depth: Optional[float] = None
    max_dlq_depth: Optional[int] = None


class QueueDepthHistoryOut(BaseModel):
    start_date: date
    end_date: date
    buckets: list[QueueDepthBucket]
