from __future__ import annotations

import pytest

from app.core.config import settings
from app.core.exceptions import UnauthorizedError
from app.core.security import require_api_key


@pytest.mark.asyncio
async def test_debug_mode_bypasses_check(monkeypatch):
    monkeypatch.setattr(settings, "DEBUG", True)
    monkeypatch.setattr(settings, "API_KEY", "secret")
    await require_api_key(x_api_key=None)  # must not raise


@pytest.mark.asyncio
async def test_missing_header_rejected(monkeypatch):
    monkeypatch.setattr(settings, "DEBUG", False)
    monkeypatch.setattr(settings, "API_KEY", "secret")
    with pytest.raises(UnauthorizedError):
        await require_api_key(x_api_key=None)


@pytest.mark.asyncio
async def test_wrong_key_rejected(monkeypatch):
    monkeypatch.setattr(settings, "DEBUG", False)
    monkeypatch.setattr(settings, "API_KEY", "secret")
    with pytest.raises(UnauthorizedError):
        await require_api_key(x_api_key="wrong")


@pytest.mark.asyncio
async def test_correct_key_accepted(monkeypatch):
    monkeypatch.setattr(settings, "DEBUG", False)
    monkeypatch.setattr(settings, "API_KEY", "secret")
    await require_api_key(x_api_key="secret")  # must not raise


@pytest.mark.asyncio
async def test_empty_configured_key_fails_closed(monkeypatch):
    """An unset API_KEY must reject everything, not silently allow --
    the routes should never end up open by omission."""
    monkeypatch.setattr(settings, "DEBUG", False)
    monkeypatch.setattr(settings, "API_KEY", "")
    with pytest.raises(UnauthorizedError):
        await require_api_key(x_api_key=None)
    with pytest.raises(UnauthorizedError):
        await require_api_key(x_api_key="")
