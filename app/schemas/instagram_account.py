from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class AccountStatusUpdate(BaseModel):
    # Deliberately restricted to these two -- an operator manually setting
    # in_use/pending_login/checkpoint_required would fight the account-pool
    # state machine (acquire_healthy_account, the login processor, etc.),
    # which own those transitions themselves.
    status: Literal["active", "disabled"]


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
    # Presence flag only -- the proxy URL carries credentials and is never
    # returned over the API. Reads the InstagramAccount.has_proxy property.
    has_proxy: bool = False
    # session_cookies_encrypted, session_captured_at, user_agent, locale,
    # timezone are deliberately not listed -- response_model= strips
    # anything undeclared here, same mechanism every other *Out schema
    # already relies on.

    model_config = ConfigDict(from_attributes=True)
