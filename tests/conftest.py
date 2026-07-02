from __future__ import annotations
"""
Pytest configuration and shared fixtures.

Fixtures available to all tests:
  - settings      — the Settings instance
  - anyio_backend — forces asyncio backend for pytest-asyncio
"""

import pytest

from app.core.config import settings as _settings


@pytest.fixture(scope="session")
def anyio_backend():
    """Force asyncio backend (not trio)."""
    return "asyncio"


@pytest.fixture(scope="session")
def settings():
    """Return the application Settings singleton."""
    return _settings
