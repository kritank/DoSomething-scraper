from typing import Any

from pydantic import BaseModel


class QueryRequest(BaseModel):
    sql: str


class QueryResult(BaseModel):
    columns: list[str]
    rows: list[dict[str, Any]]
    row_count: int
    truncated: bool
    duration_ms: float
