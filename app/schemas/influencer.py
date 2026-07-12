from datetime import date
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict


class InfluencerCreate(BaseModel):
    handle: str
    category_id: UUID
    # Don't pull posts older than this date (omit/null = full history).
    scrape_posts_since: Optional[date] = None


class InfluencerScrapeSettingsUpdate(BaseModel):
    scrape_posts_since: Optional[date] = None


class InfluencerActiveUpdate(BaseModel):
    is_active: bool


class InfluencerOut(BaseModel):
    id: UUID
    handle: str
    category_id: UUID
    is_active: bool
    scrape_posts_since: Optional[date] = None
    backfill_completed: bool

    model_config = ConfigDict(from_attributes=True)
