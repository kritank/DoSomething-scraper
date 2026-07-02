from __future__ import annotations
"""
Structured JSON logging using structlog.

Provides:
  - JSON output in production, colorised console in DEBUG mode
  - Context variables bound per request/job: request_id, job_id, worker_id,
    correlation_id — automatically included in every log line
  - get_logger() factory for module-level loggers
  - configure_logging() called once at application startup

Usage:
    from app.core.logging import configure_logging, get_logger, set_job_id

    configure_logging(log_level="INFO", json_logs=True)
    logger = get_logger(__name__)

    set_job_id("abc-123")           # bind to current context
    logger.info("job.started", influencer="cristiano")
"""

import logging
import sys
from contextvars import ContextVar
from typing import Any

import structlog

# ─────────────────────────────────────────────────────────────────────────────
# Context variables — set per request/job; always included in log output
# ─────────────────────────────────────────────────────────────────────────────

_request_id: ContextVar[str] = ContextVar("request_id", default="-")
_job_id: ContextVar[str] = ContextVar("job_id", default="-")
_worker_id: ContextVar[str] = ContextVar("worker_id", default="-")
_correlation_id: ContextVar[str] = ContextVar("correlation_id", default="-")
_influencer: ContextVar[str] = ContextVar("influencer", default="-")
_category: ContextVar[str] = ContextVar("category", default="-")


def set_request_id(value: str) -> None:
    _request_id.set(value)


def set_job_id(value: str) -> None:
    _job_id.set(value)


def set_worker_id(value: str) -> None:
    _worker_id.set(value)


def set_correlation_id(value: str) -> None:
    _correlation_id.set(value)


def set_influencer(value: str) -> None:
    _influencer.set(value)


def set_category(value: str) -> None:
    _category.set(value)


# ─────────────────────────────────────────────────────────────────────────────
# Processor — injects context vars into every log event dict
# ─────────────────────────────────────────────────────────────────────────────

def _inject_context(
    _logger: Any,
    _method: str,
    event_dict: dict[str, Any],
) -> dict[str, Any]:
    event_dict["request_id"] = _request_id.get()
    event_dict["job_id"] = _job_id.get()
    event_dict["worker_id"] = _worker_id.get()
    event_dict["correlation_id"] = _correlation_id.get()
    influencer = _influencer.get()
    if influencer != "-":
        event_dict["influencer"] = influencer
    category = _category.get()
    if category != "-":
        event_dict["category"] = category
    return event_dict


# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────

def configure_logging(log_level: str = "INFO", json_logs: bool = True) -> None:
    """
    Configure structlog and the stdlib root logger.

    Call exactly once at application startup, before any loggers are created.
    """
    # Shared processors run on every log call, both from structlog and stdlib
    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        _inject_context,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]

    renderer: Any = (
        structlog.processors.JSONRenderer()
        if json_logs
        else structlog.dev.ConsoleRenderer(colors=True)
    )

    # Configure structlog to hand off to stdlib (so third-party libs integrate)
    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Stdlib formatter that applies structlog processors to foreign log records
    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(log_level.upper())

    # Silence noisy third-party loggers in production
    for noisy in ("uvicorn.access", "sqlalchemy.engine", "httpx", "asyncio"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


# ─────────────────────────────────────────────────────────────────────────────
# Factory
# ─────────────────────────────────────────────────────────────────────────────

def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Return a bound structlog logger for the given module name.

    Example:
        logger = get_logger(__name__)
        logger.info("scraper.started", handle="@cristiano")
    """
    return structlog.get_logger(name)
