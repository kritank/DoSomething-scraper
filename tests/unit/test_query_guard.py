from __future__ import annotations
"""
Covers the app-level statement whitelist only. Function-call-based attacks
(e.g. a SELECT that calls a superuser-only function) are intentionally out
of scope here -- that's the read-only DB role's job (no such grants), not
this regex's."""

import pytest

from app.core.exceptions import QueryNotAllowedError
from app.core.query_guard import validate_readonly_sql


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT 1",
        "select id, handle from influencers limit 5",
        "SELECT * FROM influencers;",  # trailing semicolon is stripped, not rejected
        "with x as (select 1) select * from x",  # lowercase WITH
        "  SELECT 1  ",  # surrounding whitespace
    ],
)
def test_allowed_queries_pass(sql):
    assert validate_readonly_sql(sql)


@pytest.mark.parametrize(
    "sql",
    [
        "",
        "   ",
        "DROP TABLE influencers",
        "drop table influencers",
        "SELECT 1; DROP TABLE influencers;",  # multi-statement
        "INSERT INTO influencers (handle) VALUES ('x')",
        "UPDATE influencers SET is_active = false",
        "DELETE FROM influencers",
        "ALTER TABLE influencers ADD COLUMN x text",
        "TRUNCATE influencers",
        "GRANT ALL ON influencers TO someone",
        "CREATE TABLE evil (id int)",
        "COPY influencers TO '/tmp/x'",
        "SET statement_timeout = 0",
        "CALL some_procedure()",
        "SELECT 1 AS x -- ignore this\nDROP TABLE influencers",  # comment-based bypass attempt
    ],
)
def test_disallowed_queries_rejected(sql):
    with pytest.raises(QueryNotAllowedError):
        validate_readonly_sql(sql)
