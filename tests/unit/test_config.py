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

    def test_account_rate_limit_positive(self):
        s = self._make_settings()
        assert s.ACCOUNT_RATE_LIMIT_RPS > 0
        assert s.ACCOUNT_RATE_LIMIT_BURST > 0

    def test_max_posts_per_scrape_positive(self):
        s = self._make_settings()
        assert s.MAX_POSTS_PER_SCRAPE > 0

    def test_comment_sync_window_default(self):
        s = self._make_settings()
        assert s.COMMENT_SYNC_WINDOW_DAYS == 30

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


class TestInstagramAccountPoolDefaults:
    """Instagram accounts now live in the instagram_accounts table
    (see app.repositories.instagram_account_repo), provisioned via
    scripts/register_instagram_account.py -- these are just the pool's
    tunable defaults."""

    def _make(self, **overrides) -> Settings:
        base = {"DATABASE_URL": "postgresql+asyncpg://u:p@localhost/db"}
        base.update(overrides)
        return Settings.model_validate(base)

    def test_account_encryption_key_empty_by_default(self):
        s = self._make()
        assert s.ACCOUNT_ENCRYPTION_KEY == ""

    def test_account_lease_timeout_default(self):
        s = self._make()
        assert s.ACCOUNT_LEASE_TIMEOUT_S == 180

    def test_job_heartbeat_interval_default(self):
        s = self._make()
        assert s.JOB_HEARTBEAT_INTERVAL_S == 30

    def test_account_max_consecutive_failures_default(self):
        s = self._make()
        assert s.ACCOUNT_MAX_CONSECUTIVE_FAILURES == 5
