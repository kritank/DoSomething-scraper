from datetime import date
from typing import Literal, Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict


class InfluencerCreate(BaseModel):
    handle: str
    category_id: UUID
    platform: Literal["instagram", "youtube"] = "instagram"
    # Don't pull posts older than this date (omit/null = full history).
    scrape_posts_since: Optional[date] = None
    # Free-text creator name -- get-or-create-by-name (see
    # CreatorRepo.get_or_create_by_name), so registering the same
    # creator's second platform account under the same name links them
    # automatically. Omit/blank to leave this platform account unlinked.
    creator_name: Optional[str] = None
    account_type: Literal["business", "individual"] = "individual"


class InfluencerScrapeSettingsUpdate(BaseModel):
    scrape_posts_since: Optional[date] = None
    # Per-influencer override for settings.COMMENT_SYNC_DEFAULT_MAX_PER_POST
    # -- omit/null to use the platform default, 0 for unlimited on this
    # influencer specifically. See Influencer.max_comments_per_post.
    max_comments_per_post: Optional[int] = None


class InfluencerDetailsUpdate(BaseModel):
    # All optional/partial -- only the fields actually provided get
    # applied, same convention as CategoryUpdate. creator_name is
    # tri-state: omitted (None) leaves the link untouched; "" (present but
    # blank) explicitly unlinks; any other value get-or-creates and links.
    handle: Optional[str] = None
    category_id: Optional[UUID] = None
    creator_name: Optional[str] = None
    account_type: Optional[Literal["business", "individual"]] = None


class InfluencerActiveUpdate(BaseModel):
    is_active: bool


class InfluencerOut(BaseModel):
    id: UUID
    handle: str
    category_id: UUID
    platform: str
    creator_id: Optional[UUID] = None
    account_type: str
    is_active: bool
    paused_by_category: bool
    deactivation_reason: Optional[str] = None
    scrape_posts_since: Optional[date] = None
    backfill_completed: bool
    max_comments_per_post: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)
