from uuid import UUID
from typing import Optional
from datetime import datetime
from pydantic import BaseModel, ConfigDict


class ScrapeJobOut(BaseModel):
    id: UUID
    influencer_id: UUID
    status: str
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    duration_s: Optional[float] = None
    error_message: Optional[str] = None
    posts_processed: int
    comments_processed: int
    retry_count: int

    model_config = ConfigDict(from_attributes=True)
