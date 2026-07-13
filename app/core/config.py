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

    # Read-only role for the SQL query console (POST /admin/query) -- a
    # separate Postgres role with SELECT-only grants (see
    # infra/user_data.sh), never the writable DATABASE_URL above. Empty by
    # default; the query console 500s clearly rather than silently falling
    # back to the writable connection if this isn't configured.
    DATABASE_URL_READONLY: str = ""
    QUERY_CONSOLE_STATEMENT_TIMEOUT_MS: int = 5000
    QUERY_CONSOLE_ROW_CAP: int = 1000

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
    SCRAPER_TIMEOUT_S: int = 30
    SCRAPER_MAX_RETRIES: int = 3
    MAX_POSTS_PER_SCRAPE: int = 50
    # Comment/reply sync is the expensive phase -- this many posts' comment
    # sync run concurrently, each in its own DB session. Higher = faster
    # wall-clock time but a proportionally higher request rate hitting
    # Instagram from one account/session (bounded overall by the per-account
    # rate limiter below, since all concurrent tasks share one InstagramClient).
    COMMENT_SYNC_CONCURRENCY: int = 6
    SCRAPER_HEADLESS: bool = True

    # Only re-sync comments/replies for posts newer than this many days.
    # Comments trickle in slowly on old posts, so re-walking the full
    # comment/reply tree of every post in MAX_POSTS_PER_SCRAPE on every run
    # is mostly wasted request budget. 0 disables the window (sync every
    # selected post regardless of age).
    COMMENT_SYNC_WINDOW_DAYS: int = 30

    # Per-Instagram-account request pacing, as a token bucket: ACCOUNT_RATE_LIMIT_RPS
    # steady-state requests/sec with a small burst allowance. This is the
    # single source of request pacing (replaces ad-hoc per-coroutine sleeps),
    # so it correctly throttles the *aggregate* request rate against one
    # account even when several comment-sync tasks share that account's
    # InstagramClient concurrently (see COMMENT_SYNC_CONCURRENCY).
    ACCOUNT_RATE_LIMIT_RPS: float = 0.3
    ACCOUNT_RATE_LIMIT_BURST: int = 2

    # Spread the midnight dispatch of all active influencers across this
    # many seconds instead of enqueuing every job at once. 0 disables
    # staggering (dispatch everything immediately).
    DAILY_SCRAPE_STAGGER_WINDOW_S: int = 20 * 3600

    # ── Instagram Account Pool ─────────────────────────────────────────────────
    # Accounts are logged in via scripts/register_instagram_account.py (Playwright
    # automation) and stored in the instagram_accounts table -- no more manually
    # pasting session cookies into .env.
    ACCOUNT_ENCRYPTION_KEY: str = ""  # required — Fernet key for cookies at rest
    # Worker liveness TTL -- both the leased account (lease_expires_at) and
    # the running job (last_heartbeat_at) are renewed to now() + this value
    # every JOB_HEARTBEAT_INTERVAL_S by JobProcessor._heartbeat, for as long
    # as the worker is genuinely alive (regardless of how long the scrape
    # itself legitimately takes). Only once heartbeats actually stop --
    # worker killed by SIGKILL/OOM/a Watchtower rolling deploy -- does this
    # window elapse, at which point reap_stale_jobs/release_stale_leases
    # correctly presume the worker dead and recover both the job and the
    # account. Was previously a fixed 1800s measured from job start with no
    # renewal, which (a) falsely reaped legitimately long jobs, and (b) is a
    # worse latent bug: a job running past 1800s let its OWN still-in-use
    # account get silently released and re-acquired by a second, concurrent
    # job -- two scrapes sharing one live Instagram session at once. A
    # short, renewed TTL closes both.
    ACCOUNT_LEASE_TIMEOUT_S: int = 180
    JOB_HEARTBEAT_INTERVAL_S: int = 30
    ACCOUNT_MAX_CONSECUTIVE_FAILURES: int = 5
    # How often the worker's background loop polls for pending_login accounts
    # (dashboard-initiated username/password registrations) to process.
    ACCOUNT_LOGIN_POLL_INTERVAL_S: int = 30

    # ── Scheduler ─────────────────────────────────────────────────────────────
    SCHEDULER_TIMEZONE: str = "UTC"
    CRON_PROFILE_UPDATE: str = "0 2 * * *"
    CRON_POST_DISCOVERY: str = "0 */4 * * *"
    CRON_FEATURE_EXTRACTION: str = "30 */4 * * *"
    CRON_ANALYTICS: str = "0 4 * * *"
    CRON_BENCHMARK: str = "0 5 * * *"
    CRON_RECOMMENDATION: str = "0 6 * * *"
    CRON_CLEANUP: str = "0 3 * * 0"
    # Drives 3 crash-recovery jobs (retry_failed_scrapes, reap_stale_account_leases,
    # reap_stale_jobs) -- all cheap, idempotent, low-volume queries. Hourly meant a
    # worker/scheduler killed by a deploy (Watchtower restarts these routinely) could
    # leave a stale account lease or orphaned job unrecovered for up to ~90 minutes
    # (30-min lease timeout + up to 60 min to the next tick). Every 10 minutes instead.
    CRON_RETRY_FAILED: str = "*/10 * * * *"

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
