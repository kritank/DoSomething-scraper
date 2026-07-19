from typing import Literal, Optional

from pydantic import BaseModel


class BulkImportRowResult(BaseModel):
    # 1-based, counts data rows only (excludes the header row).
    row: int
    creator_name: str
    status: Literal["created", "partial", "error"]
    message: str
    instagram_handle: Optional[str] = None
    instagram_status: Optional[Literal["created", "failed"]] = None
    youtube_handle: Optional[str] = None
    youtube_status: Optional[Literal["created", "failed"]] = None


class BulkImportResult(BaseModel):
    total_rows: int
    # A row with at least one handle created counts here, even if its
    # other handle failed (status="partial") -- see BulkImportRowResult.
    created_count: int
    error_count: int
    rows: list[BulkImportRowResult]
