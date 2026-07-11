from __future__ import annotations

from fastapi import Header

from app.core.config import settings
from app.core.exceptions import UnauthorizedError


async def require_api_key(x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> None:
    """FastAPI dependency enforcing settings.API_KEY on admin routes.

    DEBUG mode bypasses the check (local dev convenience); everywhere else
    fails closed -- a missing/empty API_KEY setting rejects rather than
    silently leaving the routes open.
    """
    if settings.DEBUG:
        return
    if not settings.API_KEY or x_api_key != settings.API_KEY:
        raise UnauthorizedError()
