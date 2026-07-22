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
    account_type: str
    is_active: bool
    # True when is_active=false was set by that category being deactivated,
    # not a direct per-influencer toggle -- lets the UI distinguish "paused
    # because its category is held" from "manually paused".
    paused_by_category: bool
    # Set only when a scrape job itself deactivated this influencer because
    # the platform confirmed the handle doesn't resolve (currently only
    # "handle_not_found") -- None for a manual deactivate or a category
    # pause. See Influencer.deactivation_reason.
    deactivation_reason: Optional[str] = None
    backfill_completed: bool
    scrape_posts_since: Optional[date] = None
    max_comments_per_post: Optional[int] = None
    last_job_id: Optional[UUID] = None
    last_job_status: Optional[str] = None
    last_job_started_at: Optional[datetime] = None
    last_job_finished_at: Optional[datetime] = None
    last_job_duration_s: Optional[float] = None
    last_job_error_message: Optional[str] = None
    last_job_posts_processed: Optional[int] = None
    last_job_comments_processed: Optional[int] = None
    last_job_scraper_account: Optional[str] = None
    # Lifetime job reliability (docs -- see ScrapeJobRepo.get_job_stats_by_influencer):
    # counts only terminal runs (completed/failed), so a currently
    # queued/running job doesn't skew the rate. total_job_runs is every
    # ScrapeJob row ever created for this influencer, terminal or not.
    total_job_runs: int = 0
    completed_job_runs: int = 0
    failed_job_runs: int = 0
    job_success_rate: Optional[float] = None
    # How many of the most recent *terminal* jobs in a row failed, walking
    # back from the latest -- 0 the moment a completed run breaks the
    # streak. This is what "failing frequently right now" means, as
    # distinct from a poor lifetime average that already recovered.
    consecutive_job_failures: int = 0
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
