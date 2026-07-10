"""Chat API request/response schemas."""

from __future__ import annotations

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


class SessionDetailResponse(BaseModel):
    session_id: UUID
    data_source_id: Optional[UUID] = None
    title: Optional[str] = None
    messages: list[SessionMessage] = Field(default_factory=list)
