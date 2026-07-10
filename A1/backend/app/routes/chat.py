"""Chat API routes — LangGraph-backed analytics Q&A."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ChatPipelineError, OpenRouterError, SchemaEmbeddingError
from app.database import get_db
from app.schemas.chat import (
    ChatRequest,
    ChatResponse,
    SessionDetailResponse,
    SessionMessage,
)
from app.services.chat_persistence import ChatPersistenceService
from app.services.chat_service import ChatService

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
async def ask_question(
    request: ChatRequest,
    db: AsyncSession = Depends(get_db),
) -> ChatResponse:
    """
    Ask a natural-language analytics question against a connected warehouse.
    Runs: RAG → NL→SQL → validate → execute → summarize (LangGraph).
    """
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
    except OpenRouterError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"AI provider error: {exc}",
        ) from exc
    except (ChatPipelineError, SchemaEmbeddingError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Chat pipeline failed: {exc}",
        ) from exc


@router.get("/sessions/{session_id}", response_model=SessionDetailResponse)
async def get_session(
    session_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> SessionDetailResponse:
    chat = await ChatPersistenceService.get_session_with_messages(db, session_id)
    if chat is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    return SessionDetailResponse(
        session_id=chat.session_id,
        data_source_id=chat.data_source_id,
        title=chat.title,
        messages=[SessionMessage(role=m.role, content=m.content) for m in chat.messages],
    )
