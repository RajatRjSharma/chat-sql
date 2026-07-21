"""Schemas for CSV / Excel upload responses."""

from __future__ import annotations

from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class UploadResponse(BaseModel):
    data_source_id: UUID
    name: str
    host: str
    port: int
    database: str
    schema_name: str
    table_name: str
    rows_loaded: int
    columns: list[str] = Field(default_factory=list)
    file_kind: Literal["csv", "xlsx"]
    status: str = "loaded"
    message: Optional[str] = None
