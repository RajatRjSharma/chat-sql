"""Persist chat sessions, messages, and query history."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.models import ChatSession, Message, QueryHistory


class ChatPersistenceService:
    """ORM helpers for conversational analytics memory."""

    @staticmethod
    async def get_or_create_session(
        session: AsyncSession,
        *,
        data_source_id: uuid.UUID,
        session_id: uuid.UUID | None = None,
        title: str | None = None,
    ) -> ChatSession:
        if session_id is not None:
            existing = await session.get(ChatSession, session_id)
            if existing is None:
                raise ValueError(f"Chat session not found: {session_id}")
            return existing

        chat = ChatSession(
            session_id=uuid.uuid4(),
            data_source_id=data_source_id,
            title=(title or "Analytics chat")[:255],
            context_cache={},
        )
        session.add(chat)
        await session.flush()
        return chat

    @staticmethod
    async def load_history(
        session: AsyncSession,
        session_id: uuid.UUID,
        *,
        limit: int | None = None,
    ) -> list[dict[str, str]]:
        cap = settings.chat_history_limit if limit is None else limit
        if cap <= 0:
            return []
        result = await session.execute(
            select(Message)
            .where(Message.session_id == session_id)
            .order_by(Message.created_at.desc())
            .limit(cap)
        )
        messages = list(reversed(result.scalars().all()))
        return [{"role": m.role, "content": m.content} for m in messages]

    @staticmethod
    async def add_message(
        session: AsyncSession,
        *,
        session_id: uuid.UUID,
        role: str,
        content: str,
    ) -> Message:
        message = Message(session_id=session_id, role=role, content=content)
        session.add(message)
        await session.flush()
        return message

    @staticmethod
    async def add_query_history(
        session: AsyncSession,
        *,
        session_id: uuid.UUID,
        question: str,
        sql_query: str | None,
        status: str,
    ) -> QueryHistory:
        record = QueryHistory(
            session_id=session_id,
            question=question,
            sql_query=sql_query,
            status=status,
        )
        session.add(record)
        await session.flush()
        return record

    @staticmethod
    async def get_session_with_messages(
        session: AsyncSession,
        session_id: uuid.UUID,
    ) -> ChatSession | None:
        result = await session.execute(
            select(ChatSession)
            .where(ChatSession.session_id == session_id)
            .options(selectinload(ChatSession.messages))
        )
        return result.scalar_one_or_none()
