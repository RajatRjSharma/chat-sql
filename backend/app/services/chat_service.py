"""Orchestrate analytics chat: RAG prep + LangGraph + persistence."""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import SchemaEmbeddingError
from app.graph.chat_graph import build_chat_graph, initial_chat_state, run_chat_graph
from app.providers.ai import AIClient, get_ai_client
from app.services.chat_persistence import ChatPersistenceService
from app.services.data_source_service import DataSourceService
from app.services.rag_service import RagService
from app.services.schema_introspection import SchemaIntrospectionService


class ChatService:
    """High-level chat entrypoint used by the API layer."""

    @staticmethod
    async def ask(
        session: AsyncSession,
        *,
        data_source_id: uuid.UUID,
        question: str,
        session_id: uuid.UUID | None = None,
        client: AIClient | None = None,
    ) -> dict[str, Any]:
        ai = client or get_ai_client()
        data_source = await DataSourceService.get_active(session, data_source_id)
        info = DataSourceService.connection_info_from_record(data_source)

        chat_session = await ChatPersistenceService.get_or_create_session(
            session,
            data_source_id=data_source_id,
            session_id=session_id,
            title=question[:80],
        )
        history = await ChatPersistenceService.load_history(
            session, chat_session.session_id
        )

        chunks = await RagService.retrieve(
            session,
            data_source_id,
            question,
            client=ai,
        )
        if not chunks:
            try:
                tables = await asyncio.to_thread(
                    SchemaIntrospectionService.introspect, info
                )
                from app.services.schema_chunker import chunk_tables

                chunks = [content for content, _ in chunk_tables(tables)]
            except SchemaEmbeddingError:
                chunks = []

        schema_context = RagService.format_context(chunks)
        allowed_tables = ChatService._extract_allowed_tables(chunks, info.schema_name)

        state = initial_chat_state(
            data_source_id=data_source_id,
            question=question,
            connection_url=info.connection_url,
            schema_name=info.schema_name,
            allowed_tables=allowed_tables,
            session_id=chat_session.session_id,
            history=history,
        )
        graph = build_chat_graph(schema_context=schema_context, client=ai)
        final = await asyncio.to_thread(run_chat_graph, graph, state)

        status = final.get("status") or "failed"
        sql = final.get("sql")
        answer = final.get("answer") or "No answer produced."

        await ChatPersistenceService.add_message(
            session,
            session_id=chat_session.session_id,
            role="user",
            content=question,
        )
        await ChatPersistenceService.add_message(
            session,
            session_id=chat_session.session_id,
            role="assistant",
            content=answer,
        )
        await ChatPersistenceService.add_query_history(
            session,
            session_id=chat_session.session_id,
            question=question,
            sql_query=sql,
            status=status,
        )
        await session.flush()

        return {
            "session_id": chat_session.session_id,
            "data_source_id": data_source_id,
            "question": question,
            "answer": answer,
            "sql": sql,
            "columns": final.get("columns") or [],
            "rows": final.get("rows") or [],
            "status": status,
            "attempts": final.get("attempts") or 0,
        }

    @staticmethod
    def _extract_allowed_tables(chunks: list[str], schema_name: str | None) -> list[str]:
        tables: set[str] = set()
        for chunk in chunks:
            for line in chunk.splitlines():
                if line.startswith("Table:"):
                    qualified = line.split(":", 1)[1].strip()
                    if "." in qualified:
                        tables.add(qualified.split(".", 1)[1])
                    else:
                        tables.add(qualified)
        return sorted(tables)
