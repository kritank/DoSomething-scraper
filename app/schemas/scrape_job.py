from uuid import UUID
from typing import Optional
from datetime import datetime
from pydantic import BaseModel, ConfigDict


class ScrapeJobOut(BaseModel):
    id: UUID
    influencer_id: UUID
    status: str
    # "scrape" (the Graph API/cookie profile+posts run) or "enrich" (the
    # cookie follow-on that fills in comments/views for a hybrid-scraped
    # influencer, see InstagramEnrichProcessor) -- surfaced so the job
    # history table can label rows instead of leaving it ambiguous which
    # job actually owns comments_processed/posts_processed for that run.
    job_type: str
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    duration_s: Optional[float] = None
    error_message: Optional[str] = None
    posts_processed: int
    comments_processed: int
    retry_count: int
    # Human-readable label (Instagram username or YouTube key label) for
    # whichever credential ran this job -- see ScrapeJob.scraper_account.
    scraper_account: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)
