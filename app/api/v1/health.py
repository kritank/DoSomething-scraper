from __future__ import annotations
"""
Health and readiness endpoints.

GET /health   — liveness probe (always fast, no external calls)
GET /ready    — readiness probe (checks DB connectivity)
"""

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.core.database import get_session
from app.core.logging import get_logger

router = APIRouter()
logger = get_logger(__name__)


@router.get("/health", summary="Liveness probe")
async def health() -> dict:
    """Returns 200 immediately. Used by load balancers / container orchestrators."""
    return {"status": "ok"}


@router.get("/ready", summary="Readiness probe — checks DB connectivity")
async def ready() -> JSONResponse:
    """
    Returns 200 when all dependencies are reachable, 503 otherwise.
    Checked by EC2/ECS before sending traffic.
    """
    checks: dict[str, str] = {}

    # PostgreSQL
    try:
        async with get_session() as session:
            await session.execute(text("SELECT 1"))
        checks["postgres"] = "ok"
    except Exception as exc:
        logger.warning("ready.postgres_check_failed", error=str(exc))
        checks["postgres"] = f"error: {exc}"

    all_ok = all(v == "ok" for v in checks.values())
    return JSONResponse(
        status_code=200 if all_ok else 503,
        content={
            "status": "ready" if all_ok else "degraded",
            "checks": checks,
        },
    )


@router.get("/", include_in_schema=False)
async def root() -> dict:
    return {"service": "Viralytics", "version": "1.0.0"}
