"""Chat API routes — LangGraph-backed analytics Q&A."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AIProviderError, ChatPipelineError, SchemaEmbeddingError
from app.database import get_db
from app.schemas.chat import (
    ChatRequest,
    ChatResponse,
    SessionDetailResponse,
    SessionSummary,
)
from app.services.chat_service import ChatService

router = APIRouter(prefix="/api/chat", tags=["chat"])


def _chat_http_exception(exc: Exception) -> HTTPException:
    if isinstance(exc, ValueError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, AIProviderError):
        return HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"AI provider error: {exc}",
        )
    if isinstance(exc, (ChatPipelineError, SchemaEmbeddingError)):
        return HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail=f"Chat pipeline failed: {exc}",
    )


def _sse_encode(event: str, payload: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, default=str)}\n\n"


@router.post("", response_model=ChatResponse)
async def ask_question(
    request: ChatRequest,
    db: AsyncSession = Depends(get_db),
) -> ChatResponse:
    """Ask a natural-language analytics question against a connected warehouse."""
    try:
        result = await ChatService.ask(
            db,
            data_source_id=request.data_source_id,
            question=request.question,
            session_id=request.session_id,
        )
        return ChatResponse.model_validate(result)
    except Exception as exc:
        raise _chat_http_exception(exc) from exc


@router.post("/stream")
async def ask_question_stream(
    request: ChatRequest,
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """
    Same pipeline as POST /api/chat, streamed as SSE.

    Events:
      - `stage`  — pipeline progress (preparing → LangGraph nodes)
      - `result` — final ChatResponse-shaped payload
      - `error`  — terminal failure (`detail` string)
    """

    async def event_generator() -> AsyncIterator[str]:
        try:
            async for event in ChatService.ask_stream(
                db,
                data_source_id=request.data_source_id,
                question=request.question,
                session_id=request.session_id,
            ):
                event_type = str(event.get("type") or "stage")
                if event_type == "result":
                    payload = {k: v for k, v in event.items() if k != "type"}
                    yield _sse_encode("result", payload)
                elif event_type == "error":
                    yield _sse_encode(
                        "error",
                        {"detail": event.get("detail") or "Chat stream failed"},
                    )
                else:
                    payload = {
                        "stage": event.get("stage"),
                        "label": event.get("label"),
                        "attempts": event.get("attempts") or 0,
                        "sql": event.get("sql"),
                    }
                    yield _sse_encode("stage", payload)
        except Exception as exc:
            http_exc = _chat_http_exception(exc)
            yield _sse_encode("error", {"detail": http_exc.detail})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/sessions", response_model=list[SessionSummary])
async def list_sessions(
    data_source_id: UUID = Query(..., description="Warehouse data source id"),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> list[SessionSummary]:
    """List chat sessions for a data source (newest activity first)."""
    try:
        rows = await ChatService.list_sessions(
            db, data_source_id=data_source_id, limit=limit
        )
        return [SessionSummary.model_validate(row) for row in rows]
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/sessions/{session_id}", response_model=SessionDetailResponse)
async def get_session(
    session_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> SessionDetailResponse:
    """Load a full session: messages + reconstructed turns (SQL / table / chart data)."""
    try:
        result = await ChatService.get_session_detail(db, session_id)
        return SessionDetailResponse.model_validate(result)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
