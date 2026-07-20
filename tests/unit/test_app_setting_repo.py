from __future__ import annotations

from app.repositories.app_setting_repo import INSTAGRAM_BACKEND_KEY


def test_instagram_backend_key_is_stable():
    # Regression guard: this literal is read by DispatchService,
    # alerts_service, and the admin API route -- if it ever drifts between
    # those call sites, get()/set() silently stop agreeing with each other.
    assert INSTAGRAM_BACKEND_KEY == "instagram_backend"
