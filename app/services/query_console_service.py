from __future__ import annotations

import time
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.core.config import settings
from app.core.exceptions import QueryExecutionError
from app.core.query_guard import validate_readonly_sql
from app.core.readonly_db import get_readonly_session
from app.schemas.query_console import QueryResult


def _json_safe(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (bytes, bytearray, memoryview)):
        return bytes(value).hex()
    return value


async def run_readonly_query(raw_sql: str) -> QueryResult:
    sql = validate_readonly_sql(raw_sql)
    row_cap = settings.QUERY_CONSOLE_ROW_CAP
    start = time.perf_counter()
    try:
        async with get_readonly_session() as session:
            # SET LOCAL scopes the timeout to this transaction only -- it
            # can never leak onto a pooled connection's next, unrelated
            # checkout, since get_readonly_session() always rolls back
            # right after this block. The value is a server-side constant
            # (not user input), so interpolating it directly is fine --
            # SET doesn't accept bind params the way SELECT/DML do.
            await session.execute(
                text(f"SET LOCAL statement_timeout = {settings.QUERY_CONSOLE_STATEMENT_TIMEOUT_MS}")
            )
            result = await session.execute(text(sql))
            columns = list(result.keys())
            raw_rows = result.fetchmany(row_cap + 1)  # +1 detects truncation without a separate COUNT(*)
            truncated = len(raw_rows) > row_cap
            rows = [
                dict(zip(columns, (_json_safe(v) for v in r)))
                for r in raw_rows[:row_cap]
            ]
    except DBAPIError as exc:
        raise QueryExecutionError(str(exc.orig) if exc.orig else str(exc)) from exc

    duration_ms = (time.perf_counter() - start) * 1000
    return QueryResult(
        columns=columns,
        rows=rows,
        row_count=len(rows),
        truncated=truncated,
        duration_ms=round(duration_ms, 2),
    )
