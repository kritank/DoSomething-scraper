from typing import Literal

from pydantic import BaseModel


class InstagramBackendOut(BaseModel):
    # "override_active" distinguishes a DB row actually present (true) from
    # falling back to the static settings.INSTAGRAM_BACKEND default (false)
    # -- the dashboard toggle should be able to show "this is the deployed
    # default" vs. "someone flipped this live" rather than looking identical.
    backend: Literal["cookies", "hybrid"]
    override_active: bool


class InstagramBackendUpdate(BaseModel):
    backend: Literal["cookies", "hybrid"]
