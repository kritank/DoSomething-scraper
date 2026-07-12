from __future__ import annotations
"""
Custom exception hierarchy for Viralytics.

All application exceptions inherit from ViralyticBaseError.
The FastAPI exception handler in main.py converts these to structured JSON responses.

Usage:
    raise InfluencerNotFoundError("unknown_handle")

    # or with extra context
    raise ScraperRateLimitError(handle="cristiano", retry_after=60)
"""

from typing import Any


class ViralyticBaseError(Exception):
    """Base class for all application errors."""

    http_status: int = 500
    code: str = "INTERNAL_ERROR"

    def __init__(self, message: str = "", **context: Any) -> None:
        self.message = message or self.code
        self.context = context
        super().__init__(self.message)


# ─────────────────────────────────────────────────────────────────────────────
# 404 — Not Found
# ─────────────────────────────────────────────────────────────────────────────

class NotFoundError(ViralyticBaseError):
    http_status = 404
    code = "NOT_FOUND"


class InfluencerNotFoundError(NotFoundError):
    code = "INFLUENCER_NOT_FOUND"

    def __init__(self, handle_or_id: str) -> None:
        super().__init__(f"Influencer not found: {handle_or_id}")


class CategoryNotFoundError(NotFoundError):
    code = "CATEGORY_NOT_FOUND"

    def __init__(self, name_or_id: str) -> None:
        super().__init__(f"Category not found: {name_or_id}")


class ScrapeJobNotFoundError(NotFoundError):
    code = "SCRAPE_JOB_NOT_FOUND"

    def __init__(self, job_id: str) -> None:
        super().__init__(f"Scrape job not found: {job_id}")


class InstagramAccountNotFoundError(NotFoundError):
    code = "INSTAGRAM_ACCOUNT_NOT_FOUND"

    def __init__(self, account_id: str) -> None:
        super().__init__(f"Instagram account not found: {account_id}")


# ─────────────────────────────────────────────────────────────────────────────
# 400 — Bad Request / Validation
# ─────────────────────────────────────────────────────────────────────────────

class ValidationError(ViralyticBaseError):
    http_status = 400
    code = "VALIDATION_ERROR"


class DuplicateInfluencerError(ValidationError):
    code = "DUPLICATE_INFLUENCER"

    def __init__(self, handle: str) -> None:
        super().__init__(f"Influencer already registered: {handle}")


class DuplicateCategoryError(ValidationError):
    code = "DUPLICATE_CATEGORY"

    def __init__(self, name: str) -> None:
        super().__init__(f"Category already exists: {name}")


class QueryNotAllowedError(ValidationError):
    code = "QUERY_NOT_ALLOWED"


class QueryExecutionError(ValidationError):
    code = "QUERY_EXECUTION_ERROR"


# ─────────────────────────────────────────────────────────────────────────────
# 401 / 403 — Auth
# ─────────────────────────────────────────────────────────────────────────────

class UnauthorizedError(ViralyticBaseError):
    http_status = 401
    code = "UNAUTHORIZED"

    def __init__(self) -> None:
        super().__init__("Missing or invalid API key.")


# ─────────────────────────────────────────────────────────────────────────────
# 429 — Rate Limiting
# ─────────────────────────────────────────────────────────────────────────────

class ScraperRateLimitError(ViralyticBaseError):
    http_status = 429
    code = "SCRAPER_RATE_LIMITED"

    def __init__(self, handle: str = "", retry_after: int | None = None) -> None:
        msg = f"Rate limited while scraping{f' {handle}' if handle else ''}."
        if retry_after:
            msg += f" Retry after {retry_after}s."
        super().__init__(msg, handle=handle, retry_after=retry_after)


# ─────────────────────────────────────────────────────────────────────────────
# 503 — Scraper / External
# ─────────────────────────────────────────────────────────────────────────────

class ScraperError(ViralyticBaseError):
    http_status = 503
    code = "SCRAPER_ERROR"


class ScraperBlockedError(ScraperError):
    code = "SCRAPER_BLOCKED"

    def __init__(self, handle: str = "") -> None:
        super().__init__(
            f"Scraper blocked by Instagram{f' for {handle}' if handle else ''}. "
            "Session may need to be refreshed."
        )


class ScraperTimeoutError(ScraperError):
    code = "SCRAPER_TIMEOUT"

    def __init__(self, handle: str = "") -> None:
        super().__init__(f"Scrape timed out{f' for {handle}' if handle else ''}.")


# ─────────────────────────────────────────────────────────────────────────────
# Queue
# ─────────────────────────────────────────────────────────────────────────────

class QueueError(ViralyticBaseError):
    code = "QUEUE_ERROR"


class QueueConnectionError(QueueError):
    code = "QUEUE_CONNECTION_ERROR"

    def __init__(self, backend: str) -> None:
        super().__init__(f"Cannot connect to queue backend: {backend}")
