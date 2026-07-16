from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class RegisterYouTubeApiKeyRequest(BaseModel):
    label: str
    api_key: str


class YouTubeApiKeyStatusUpdate(BaseModel):
    # Same reasoning as AccountStatusUpdate -- quota_exhausted/invalid are
    # owned by the client's own rotation logic (see YouTubeApiKeyRepo),
    # not something an operator should hand-set.
    status: Literal["active", "disabled"]


class YouTubeApiKeyOut(BaseModel):
    id: UUID
    label: str
    status: str
    quota_used_today: int
    quota_reset_at: Optional[datetime] = None
    last_used_at: Optional[datetime] = None
    last_success_at: Optional[datetime] = None
    last_failure_at: Optional[datetime] = None
    failure_count: int
    error_message: Optional[str] = None
    # api_key_encrypted is deliberately not listed -- response_model=
    # strips anything undeclared here, same as InstagramAccountOut.

    model_config = ConfigDict(from_attributes=True)
