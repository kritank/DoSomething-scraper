from __future__ import annotations
"""
Unit tests for app.core.config.Settings.

Tests that:
  - All required fields are present
  - Computed properties work correctly
  - Queue backend selection logic is correct
  - Default values are as specified
"""

import os

import pytest

from app.core.config import Settings


class TestSettingsDefaults:
    """Verify default values without a .env file."""

    def _make_settings(self, **overrides) -> Settings:
        """Create a Settings with required fields + any overrides."""
        base = {
            "DATABASE_URL": "postgresql+asyncpg://postgres:postgres@localhost:5432/viralytics",
        }
        base.update(overrides)
        # Bypass .env file loading in tests
        return Settings.model_validate(base)

    def test_project_name_default(self):
        s = self._make_settings()
        assert s.PROJECT_NAME == "Viralytics"

    def test_debug_default_false(self):
        s = self._make_settings()
        assert s.DEBUG is False

    def test_log_level_default(self):
        s = self._make_settings()
        assert s.LOG_LEVEL == "INFO"

    def test_queue_backend_default_redis(self):
        s = self._make_settings()
        assert s.QUEUE_BACKEND == "redis"

    def test_max_scraper_workers_default(self):
        s = self._make_settings()
        assert s.MAX_SCRAPER_WORKERS == 3

    def test_scrape_delay_bounds(self):
        s = self._make_settings()
        assert s.SCRAPE_DELAY_MIN_S < s.SCRAPE_DELAY_MAX_S

    def test_max_posts_per_scrape_positive(self):
        s = self._make_settings()
        assert s.MAX_POSTS_PER_SCRAPE > 0

    def test_api_v1_prefix(self):
        s = self._make_settings()
        assert s.API_V1_PREFIX.startswith("/")


class TestQueueProperties:
    """is_redis_queue / is_sqs_queue computed properties."""

    def _make(self, backend: str) -> Settings:
        return Settings.model_validate({
            "DATABASE_URL": "postgresql+asyncpg://u:p@localhost/db",
            "QUEUE_BACKEND": backend,
        })

    def test_redis_backend(self):
        s = self._make("redis")
        assert s.is_redis_queue is True
        assert s.is_sqs_queue is False

    def test_sqs_backend(self):
        s = self._make("sqs")
        assert s.is_redis_queue is False
        assert s.is_sqs_queue is True

    def test_case_insensitive(self):
        s = self._make("SQS")
        assert s.is_sqs_queue is True


class TestInstagramSessionProperty:
    """instagram_cookies and has_instagram_session properties."""

    def _make(self, **overrides) -> Settings:
        base = {"DATABASE_URL": "postgresql+asyncpg://u:p@localhost/db"}
        base.update(overrides)
        return Settings.model_validate(base)

    def test_has_session_false_when_empty(self):
        s = self._make()
        assert s.has_instagram_session is False

    def test_has_session_true_when_populated(self):
        s = self._make(
            INSTAGRAM_SESSION_ID="abc",
            INSTAGRAM_CSRF_TOKEN="def",
            INSTAGRAM_DS_USER_ID="123",
        )
        assert s.has_instagram_session is True

    def test_instagram_cookies_returns_dict(self):
        s = self._make(
            INSTAGRAM_SESSION_ID="sid",
            INSTAGRAM_CSRF_TOKEN="csrf",
            INSTAGRAM_DS_USER_ID="uid",
            INSTAGRAM_IG_DID="did",
        )
        cookies = s.instagram_cookies
        assert cookies["sessionid"] == "sid"
        assert cookies["csrftoken"] == "csrf"
        assert cookies["ds_user_id"] == "uid"
        assert cookies["ig_did"] == "did"
