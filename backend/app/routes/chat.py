"""Chat API routes — LangGraph-backed analytics Q&A."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ChatPipelineError, AIProviderError, SchemaEmbeddingError
from app.database import get_db
from app.schemas.chat import (
    ChatRequest,
    ChatResponse,
    SessionDetailResponse,
    SessionSummary,
)
from app.services.chat_service import ChatService

router = APIRouter(prefix="/api/chat", tags=["chat"])


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
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except AIProviderError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"AI provider error: {exc}",
        ) from exc
    except (ChatPipelineError, SchemaEmbeddingError) as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Chat pipeline failed: {exc}",
        ) from exc


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
