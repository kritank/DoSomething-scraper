from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class RegisterInstagramTokenFacebookLoginRequest(BaseModel):
    label: str
    app_id: str
    app_secret: str
    # Short-lived User token straight out of Graph API Explorer -- the
    # service does the exchange-to-long-lived + resolve-Page-token dance.
    short_token: str


class RegisterInstagramTokenInstagramLoginRequest(BaseModel):
    label: str
    app_id: str
    app_secret: str
    # Final long-lived token from the app dashboard's own token generator
    # -- no exchange needed for this flavor, unlike facebook_login.
    token: str
    ig_user_id: str


class InstagramApiTokenStatusUpdate(BaseModel):
    # Same reasoning as AccountStatusUpdate/YouTubeApiKeyStatusUpdate --
    # "cooldown" is owned by the BUC rate-limit bookkeeping itself
    # (InstagramApiTokenRepo.mark_exhausted), not something an operator
    # should hand-set.
    status: Literal["active", "invalid"]


class InstagramApiTokenOut(BaseModel):
    id: UUID
    label: str
    ig_user_id: str
    app_id: str
    auth_flavor: str
    token_expires_at: Optional[datetime] = None
    status: str
    calls_today: int
    cooldown_until: Optional[datetime] = None
    buc_usage_pct: Optional[float] = None
    last_used_at: Optional[datetime] = None
    last_success_at: Optional[datetime] = None
    last_failure_at: Optional[datetime] = None
    failure_count: int
    error_message: Optional[str] = None
    # access_token_encrypted, app_secret_encrypted are deliberately not
    # listed -- response_model= strips anything undeclared here, same as
    # InstagramAccountOut/YouTubeApiKeyOut.

    model_config = ConfigDict(from_attributes=True)
