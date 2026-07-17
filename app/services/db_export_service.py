from __future__ import annotations
"""
Full-database export for the dashboard's "Export" page.

Runs on the app box itself, which already sits in the same security group
as RDS (see infra/rds.tf) -- unlike a laptop, it needs no SSH tunnel to
reach it (compare scripts/pull_prod_dump.sh, which tunnels through this box
for exactly that reason). Uses the writable DATABASE_URL, not
DATABASE_URL_READONLY -- pg_dump only ever issues reads regardless of which
role it authenticates as, and the readonly role exists for the SQL console's
statement whitelist, not because the master role is unsafe to read with.
"""

import asyncio
import os
import tempfile
from datetime import datetime, timezone
from urllib.parse import urlparse, urlunparse

from app.core.config import settings
from app.core.exceptions import DumpExportError


def _libpq_url(sqlalchemy_url: str) -> str:
    """pg_dump speaks libpq URIs (`postgresql://...`), not SQLAlchemy's
    driver-qualified `postgresql+asyncpg://...` -- strip the `+asyncpg`."""
    parsed = urlparse(sqlalchemy_url)
    scheme = parsed.scheme.split("+")[0]
    return urlunparse(parsed._replace(scheme=scheme))


async def create_dump() -> tuple[str, str]:
    """Runs `pg_dump -Fc` to a temp file and returns (path, filename).

    Custom format (-Fc) rather than plain SQL: compressed, and restorable
    with `pg_restore` selectively or in parallel -- the same format
    scripts/pull_prod_dump.sh defaults to for the laptop-side pull.

    Caller owns the returned file and must delete it once it's done being
    served (see the FileResponse background task in app/api/v1/admin.py).
    """
    filename = f"viralytics_{datetime.now(timezone.utc):%Y%m%d_%H%M%S}.dump"
    fd, path = tempfile.mkstemp(suffix=".dump", prefix="db_export_")
    os.close(fd)

    proc = await asyncio.create_subprocess_exec(
        "pg_dump",
        _libpq_url(settings.DATABASE_URL),
        "-Fc",
        "--no-owner",
        "--no-privileges",
        "-f", path,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()

    if proc.returncode != 0:
        os.remove(path)
        raise DumpExportError(f"pg_dump failed: {stderr.decode(errors='replace').strip()}")

    return path, filename
