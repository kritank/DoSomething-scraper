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


class CreatorNotFoundError(NotFoundError):
    code = "CREATOR_NOT_FOUND"

    def __init__(self, name_or_id: str) -> None:
        super().__init__(f"Creator not found: {name_or_id}")


class ScrapeJobNotFoundError(NotFoundError):
    code = "SCRAPE_JOB_NOT_FOUND"

    def __init__(self, job_id: str) -> None:
        super().__init__(f"Scrape job not found: {job_id}")


class InstagramAccountNotFoundError(NotFoundError):
    code = "INSTAGRAM_ACCOUNT_NOT_FOUND"

    def __init__(self, account_id: str) -> None:
        super().__init__(f"Instagram account not found: {account_id}")


class YouTubeApiKeyNotFoundError(NotFoundError):
    code = "YOUTUBE_API_KEY_NOT_FOUND"

    def __init__(self, key_id: str) -> None:
        super().__init__(f"YouTube API key not found: {key_id}")


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


class DuplicateCreatorError(ValidationError):
    code = "DUPLICATE_CREATOR"

    def __init__(self, name: str) -> None:
        super().__init__(f"Creator already exists: {name}")


class QueryNotAllowedError(ValidationError):
    code = "QUERY_NOT_ALLOWED"


class QueryExecutionError(ValidationError):
    code = "QUERY_EXECUTION_ERROR"


# ─────────────────────────────────────────────────────────────────────────────
# 409 — Conflict
# ─────────────────────────────────────────────────────────────────────────────

class ConflictError(ViralyticBaseError):
    http_status = 409
    code = "CONFLICT"


class ActiveJobExistsError(ConflictError):
    """Message is caller-supplied (not derived here) since the same
    condition reads differently for an influencer ("@handle has an active
    job") vs. a category ("has influencer(s) with an active job")."""
    code = "ACTIVE_JOB_EXISTS"


class JobNotCancellableError(ConflictError):
    code = "JOB_NOT_CANCELLABLE"

    def __init__(self, job_id: str, status: str) -> None:
        super().__init__(f"Job {job_id} is already {status} -- nothing to cancel.")


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
    """Shared by both platforms' scrapers -- originally Instagram-only (the
    message hardcoded "Instagram"), later reused as-is for YouTube's
    "key rejected" and "channel not found" cases too, which made every
    YouTube failure of this kind misreport itself as an Instagram problem
    with an irrelevant "session may need to be refreshed" (YouTube has no
    session, just an API key). platform selects the accurate wording;
    defaults to "instagram" so every pre-existing call site (all of
    app/scraper/client.py) keeps its exact original message unchanged.
    """

    code = "SCRAPER_BLOCKED"

    def __init__(self, handle: str = "", platform: str = "instagram") -> None:
        if platform == "youtube":
            label = "YouTube"
            detail = "Check the API key and that the target handle/channel exists."
        else:
            label = "Instagram"
            detail = "Session may need to be refreshed."
        super().__init__(
            f"Scraper blocked by {label}{f' for {handle}' if handle else ''}. {detail}",
            handle=handle,
            platform=platform,
        )


class ScraperTimeoutError(ScraperError):
    code = "SCRAPER_TIMEOUT"

    def __init__(self, handle: str = "") -> None:
        super().__init__(f"Scrape timed out{f' for {handle}' if handle else ''}.")


class NoUsableYouTubeKeyError(ScraperError):
    """Every registered YouTube API key is exhausted, invalid, or disabled --
    mirrors "no healthy Instagram accounts available": the job never got to
    attempt anything, so JobProcessor-equivalents route this to
    retry_pending uncounted against SCRAPER_MAX_RETRIES rather than treating
    it as a real scrape failure."""
    code = "NO_USABLE_YOUTUBE_KEY"

    def __init__(self) -> None:
        super().__init__("No usable YouTube API key available (all exhausted, invalid, or disabled).")


class YouTubeResourceGoneError(ScraperError):
    """A specific YouTube resource is permanently unavailable for a reason
    that isn't a session/quota problem -- e.g. comments disabled on a
    video, or a deleted/private channel. Callers decide per-reason whether
    to skip just that resource or fail the whole job."""
    code = "YOUTUBE_RESOURCE_GONE"

    def __init__(self, reason: str, resource: str = "") -> None:
        super().__init__(
            f"YouTube resource unavailable{f' ({resource})' if resource else ''}: {reason}",
            reason=reason,
            resource=resource,
        )


# ─────────────────────────────────────────────────────────────────────────────
# Queue
# ─────────────────────────────────────────────────────────────────────────────

class QueueError(ViralyticBaseError):
    code = "QUEUE_ERROR"


class QueueConnectionError(QueueError):
    code = "QUEUE_CONNECTION_ERROR"

    def __init__(self, backend: str) -> None:
        super().__init__(f"Cannot connect to queue backend: {backend}")
