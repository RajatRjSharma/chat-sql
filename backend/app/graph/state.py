"""LangGraph state for the analytics chat pipeline."""

from __future__ import annotations

from typing import Any, Literal, TypedDict
from uuid import UUID


class ChatGraphState(TypedDict, total=False):
    data_source_id: UUID
    session_id: UUID | None
    question: str
    history: list[dict[str, str]]
    schema_name: str | None
    schema_context: str
    allowed_tables: list[str]
    connection_url: str
    sql: str | None
    sql_error: str | None
    columns: list[str] | None
    rows: list[dict[str, Any]] | None
    answer: str | None
    attempts: int
    max_attempts: int
    status: Literal["ok", "failed", "running"]
