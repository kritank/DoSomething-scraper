
from __future__ import annotations
"""
Viralytics — FastAPI application entry point.

Architecture:
  - Self-contained Instagram Influencer Intelligence Platform
  - Scrapes public profiles, computes benchmarks, surfaces recommendations
  - All analytics are pre-computed; API is read-only at runtime
"""

import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.database import close_db, init_db
from app.core.readonly_db import close_readonly_db
from app.core.exceptions import ViralyticBaseError
from app.core.logging import configure_logging, get_logger, set_request_id
from app.api.v1 import health, admin, benchmarks, influencers, recommendations

configure_logging(log_level=settings.LOG_LEVEL, json_logs=not settings.DEBUG)
logger = get_logger(__name__)
# ─────────────────────────────────────────────────────────────────────────────
# Lifespan
# ─────────────────────────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("startup.begin", project=settings.PROJECT_NAME, debug=settings.DEBUG)
    await init_db()
    logger.info("startup.complete", db="connected")
    yield
    logger.info("shutdown.begin")
    await close_db()
    await close_readonly_db()
    logger.info("shutdown.complete")


# ─────────────────────────────────────────────────────────────────────────────
# App
# ─────────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title=settings.PROJECT_NAME,
    description=(
        "Viralytics — Instagram Influencer Intelligence Platform. "
        "Continuously scrapes public data, computes category benchmarks, "
        "and surfaces actionable recommendations for creators."
    ),
    version="1.0.0",
    debug=settings.DEBUG,
    lifespan=lifespan,
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
)


# ─────────────────────────────────────────────────────────────────────────────
# Middleware — CORS
# ─────────────────────────────────────────────────────────────────────────────

_origins = [o.strip() for o in settings.CORS_ALLOWED_ORIGINS.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "PATCH"],
    allow_headers=["*"],
)


# ─────────────────────────────────────────────────────────────────────────────
# Middleware — Request logging + correlation ID injection
# ─────────────────────────────────────────────────────────────────────────────

@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    set_request_id(request_id)

    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = (time.perf_counter() - start) * 1000

    logger.info(
        "http.request",
        method=request.method,
        path=request.url.path,
        status=response.status_code,
        duration_ms=round(duration_ms, 2),
    )

    response.headers["X-Request-ID"] = request_id
    return response


# ─────────────────────────────────────────────────────────────────────────────
# Exception handlers
# ─────────────────────────────────────────────────────────────────────────────

@app.exception_handler(ViralyticBaseError)
async def viralytics_error_handler(request: Request, exc: ViralyticBaseError):
    logger.warning("app.error", error=exc.code, detail=exc.message, path=request.url.path)
    return JSONResponse(status_code=exc.http_status, content={"error": exc.code, "detail": exc.message})


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("app.unhandled_error", path=request.url.path, exc_info=exc)
    return JSONResponse(
        status_code=500,
        content={"error": "INTERNAL_ERROR", "detail": "An unexpected error occurred."},
    )


# ─────────────────────────────────────────────────────────────────────────────
# Routers
# ─────────────────────────────────────────────────────────────────────────────

app.include_router(health.router, tags=["Health"])

# Phase 3+ routers registered here as phases are completed:
# app.include_router(categories.router, prefix=settings.API_V1_PREFIX, tags=["Categories"])
app.include_router(benchmarks.router, prefix=settings.API_V1_PREFIX, tags=["Benchmarks"])
app.include_router(recommendations.router, prefix=settings.API_V1_PREFIX, tags=["Recommendations"])
app.include_router(influencers.router, prefix=settings.API_V1_PREFIX, tags=["Influencers"])
app.include_router(admin.router, prefix=settings.API_V1_PREFIX, tags=["Admin"])
