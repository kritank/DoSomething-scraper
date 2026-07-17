# ── API service ───────────────────────────────────────────────────────────────
FROM python:3.13-slim AS base

# uv for fast, deterministic dependency installation
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# postgresql-client for pg_dump, used by GET /admin/export/dump (the
# dashboard's "Export" page). Pulled from the PGDG repo rather than Debian's
# default package: pg_dump refuses to dump from a server newer than itself,
# and RDS runs Postgres 18 while Debian's own postgresql-client is older.
RUN apt-get update && apt-get install -y --no-install-recommends curl gnupg ca-certificates \
 && install -d /usr/share/postgresql-common/pgdg \
 && curl -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc --fail \
      https://www.postgresql.org/media/keys/ACCC4CF8.asc \
 && . /etc/os-release \
 && echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] https://apt.postgresql.org/pub/repos/apt ${VERSION_CODENAME}-pgdg main" \
      > /etc/apt/sources.list.d/pgdg.list \
 && apt-get update && apt-get install -y --no-install-recommends postgresql-client-18 \
 && apt-get purge -y curl gnupg \
 && apt-get autoremove -y \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install dependencies first (cached layer)
COPY pyproject.toml uv.lock* ./
RUN uv sync --frozen --no-install-project --no-dev

# Copy source and install the project
COPY . .
RUN uv sync --frozen --no-dev

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
