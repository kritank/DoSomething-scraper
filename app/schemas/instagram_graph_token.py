from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class RegisterInstagramGraphTokenRequest(BaseModel):
    label: str
    access_token: str


class InstagramGraphTokenStatusUpdate(BaseModel):
    status: Literal["active", "disabled"]


class InstagramGraphTokenOut(BaseModel):
    id: UUID
    label: str
    status: str
    last_used_at: Optional[datetime] = None
    last_success_at: Optional[datetime] = None
    last_failure_at: Optional[datetime] = None
    cooldown_until: Optional[datetime] = None
    failure_count: int
    error_message: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)
