from __future__ import annotations
"""
Application configuration via Pydantic Settings.

All values are loaded from environment variables or .env file.
No hardcoded defaults for sensitive fields — those are required.

Usage:
    from app.core.config import settings
    print(settings.DATABASE_URL)
"""

from pathlib import Path
from typing import ClassVar

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # ── Application ──────────────────────────────────────────────────────────
    PROJECT_NAME: str = "Viralytics"
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"
    API_V1_PREFIX: str = "/api/v1"
    CORS_ALLOWED_ORIGINS: str = "http://localhost:3000"

    # API key protecting all endpoints (simple shared secret for M2M auth).
    # Required in production. In DEBUG mode, requests without it still work.
    API_KEY: str = ""

    # ── Database ─────────────────────────────────────────────────────────────
    # Format: postgresql+asyncpg://user:password@host:port/dbname
    DATABASE_URL: str  # Required — no default

    # ── Queue ─────────────────────────────────────────────────────────────────
    # "redis" → Redis + RQ (local dev)
    # "sqs"   → Amazon SQS (production)
    QUEUE_BACKEND: str = "redis"

    REDIS_URL: str = "redis://localhost:6379/0"

    # SQS (only needed when QUEUE_BACKEND=sqs)
    AWS_SQS_QUEUE_URL: str = ""
    AWS_REGION: str = "us-east-1"
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""

    # ── Scraper ───────────────────────────────────────────────────────────────
    MAX_SCRAPER_WORKERS: int = 3
    SCRAPE_DELAY_MIN_S: float = 2.0
    SCRAPE_DELAY_MAX_S: float = 6.0
    SCRAPER_TIMEOUT_S: int = 30
    SCRAPER_MAX_RETRIES: int = 3
    MAX_POSTS_PER_SCRAPE: int = 50
    # Comment/reply sync is the expensive phase (paced 2-6s per request) --
    # this many posts' comment sync run concurrently, each in its own DB
    # session. Higher = faster wall-clock time but a proportionally higher
    # request rate hitting Instagram from one account/session.
    COMMENT_SYNC_CONCURRENCY: int = 6
    SCRAPER_HEADLESS: bool = True

    # ── Instagram Account Pool ─────────────────────────────────────────────────
    # Accounts are logged in via scripts/register_instagram_account.py (Playwright
    # automation) and stored in the instagram_accounts table -- no more manually
    # pasting session cookies into .env.
    ACCOUNT_ENCRYPTION_KEY: str = ""  # required — Fernet key for cookies at rest
    ACCOUNT_LEASE_TIMEOUT_S: int = 1800
    ACCOUNT_MAX_CONSECUTIVE_FAILURES: int = 5

    # ── Scheduler ─────────────────────────────────────────────────────────────
    SCHEDULER_TIMEZONE: str = "UTC"
    CRON_PROFILE_UPDATE: str = "0 2 * * *"
    CRON_POST_DISCOVERY: str = "0 */4 * * *"
    CRON_FEATURE_EXTRACTION: str = "30 */4 * * *"
    CRON_ANALYTICS: str = "0 4 * * *"
    CRON_BENCHMARK: str = "0 5 * * *"
    CRON_RECOMMENDATION: str = "0 6 * * *"
    CRON_CLEANUP: str = "0 3 * * 0"
    CRON_RETRY_FAILED: str = "0 * * * *"

    # ── Resolve project root ───────────────────────────────────────────────────
    # parents[2] → .../DoSomething-scraper
    # parents[1] → .../DoSomething-scraper/app
    # parents[0] → .../DoSomething-scraper/app/core
    project_root: ClassVar[Path] = Path(__file__).resolve().parents[2]

    model_config = SettingsConfigDict(
        env_file=str(project_root / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def is_redis_queue(self) -> bool:
        return self.QUEUE_BACKEND.lower() == "redis"

    @property
    def is_sqs_queue(self) -> bool:
        return self.QUEUE_BACKEND.lower() == "sqs"


settings = Settings()
