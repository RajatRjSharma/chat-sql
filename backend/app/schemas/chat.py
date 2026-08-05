"""Chat API request/response schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    data_source_id: UUID
    question: str = Field(..., min_length=1, max_length=4000)
    session_id: UUID | None = None


class ChatResponse(BaseModel):
    session_id: UUID
    data_source_id: UUID
    question: str
    answer: str
    sql: str | None = None
    columns: list[str] = Field(default_factory=list)
    rows: list[dict[str, Any]] = Field(default_factory=list)
    status: Literal["ok", "failed", "running"] = "ok"
    attempts: int = 0
    source_metadata: dict[str, Any] | None = None


class EmbedSchemaRequest(BaseModel):
    data_source_id: UUID


class EmbedSchemaResponse(BaseModel):
    data_source_id: UUID
    chunks_embedded: int
    tables_indexed: int = 0
    previous_chunks: int = 0
    indexed_at: datetime | None = None
    status: str = "ok"


class SessionMessage(BaseModel):
    role: str
    content: str


class SessionTurn(BaseModel):
    """One Q&A turn reconstructed for session reload (includes SQL + optional result)."""

    question: str
    answer: str
    sql: str | None = None
    columns: list[str] = Field(default_factory=list)
    rows: list[dict[str, Any]] = Field(default_factory=list)
    status: Literal["ok", "failed", "running"] = "ok"
    attempts: int = 0
    source_metadata: dict[str, Any] | None = None


class SessionSummary(BaseModel):
    session_id: UUID
    data_source_id: UUID | None = None
    title: str | None = None
    created_at: datetime
    updated_at: datetime
    message_count: int = 0


class SessionDetailResponse(BaseModel):
    session_id: UUID
    data_source_id: UUID | None = None
    title: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    messages: list[SessionMessage] = Field(default_factory=list)
    turns: list[SessionTurn] = Field(default_factory=list)
    source_metadata: dict[str, Any] | None = None


class SuggestedQuestion(BaseModel):
    question: str
    source: Literal["schema", "history", "fallback"] = "schema"
    table: str | None = None


class SuggestedQuestionsResponse(BaseModel):
    data_source_id: UUID
    suggestions: list[SuggestedQuestion] = Field(default_factory=list)
    schema_tables: list[str] = Field(default_factory=list)


class ChatStreamStage(BaseModel):
    """SSE `stage` event payload while LangGraph runs."""

    stage: str
    label: str
    attempts: int = 0
    sql: str | None = None
