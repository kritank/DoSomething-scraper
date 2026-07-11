from __future__ import annotations
"""
App-level statement whitelist for the SQL query console. This is one layer
of defense in depth alongside the read-only DB role (app/core/readonly_db.py,
infra/user_data.sh) and the forced-rollback transaction -- a bug here still
can't produce a write, because the DB role has no write grants at all.
"""

import re

from app.core.exceptions import QueryNotAllowedError

_ALLOWED_START = re.compile(r"^\s*(SELECT|WITH)\b", re.IGNORECASE)
_FORBIDDEN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE|GRANT|REVOKE|CREATE|COPY|VACUUM|"
    r"REINDEX|EXECUTE|CALL|MERGE|REFRESH|LOCK|SET|RESET|LISTEN|NOTIFY|DO)\b",
    re.IGNORECASE,
)


def validate_readonly_sql(raw_sql: str) -> str:
    sql = raw_sql.strip()
    if sql.endswith(";"):
        sql = sql[:-1].strip()
    if not sql:
        raise QueryNotAllowedError("Query is empty.")
    if ";" in sql:
        raise QueryNotAllowedError("Only a single statement is allowed.")
    if not _ALLOWED_START.match(sql):
        raise QueryNotAllowedError("Only SELECT/WITH statements are allowed.")
    if _FORBIDDEN.search(sql):
        raise QueryNotAllowedError("Query contains a disallowed keyword.")
    return sql
