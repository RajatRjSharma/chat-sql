"""Chat API request/response schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    data_source_id: UUID
    question: str = Field(..., min_length=1, max_length=4000)
    session_id: Optional[UUID] = None


class ChatResponse(BaseModel):
    session_id: UUID
    data_source_id: UUID
    question: str
    answer: str
    sql: Optional[str] = None
    columns: list[str] = Field(default_factory=list)
    rows: list[dict[str, Any]] = Field(default_factory=list)
    status: Literal["ok", "failed", "running"] = "ok"
    attempts: int = 0


class EmbedSchemaRequest(BaseModel):
    data_source_id: UUID


class EmbedSchemaResponse(BaseModel):
    data_source_id: UUID
    chunks_embedded: int
    status: str = "ok"


class SessionMessage(BaseModel):
    role: str
    content: str


class SessionTurn(BaseModel):
    """One Q&A turn reconstructed for session reload (includes SQL + optional result)."""

    question: str
    answer: str
    sql: Optional[str] = None
    columns: list[str] = Field(default_factory=list)
    rows: list[dict[str, Any]] = Field(default_factory=list)
    status: Literal["ok", "failed", "running"] = "ok"
    attempts: int = 0


class SessionSummary(BaseModel):
    session_id: UUID
    data_source_id: Optional[UUID] = None
    title: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    message_count: int = 0


class SessionDetailResponse(BaseModel):
    session_id: UUID
    data_source_id: Optional[UUID] = None
    title: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    messages: list[SessionMessage] = Field(default_factory=list)
    turns: list[SessionTurn] = Field(default_factory=list)
