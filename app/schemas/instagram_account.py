from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class InstagramAccountOut(BaseModel):
    id: UUID
    username: str
    status: str
    auth_method: str
    failure_count: int
    cooldown_until: Optional[datetime] = None
    locked_by: Optional[str] = None
    lease_expires_at: Optional[datetime] = None
    last_used_at: Optional[datetime] = None
    last_success_at: Optional[datetime] = None
    last_failure_at: Optional[datetime] = None
    error_message: Optional[str] = None
    # session_cookies_encrypted, session_captured_at, user_agent, locale,
    # timezone are deliberately not listed -- response_model= strips
    # anything undeclared here, same mechanism every other *Out schema
    # already relies on.

    model_config = ConfigDict(from_attributes=True)
