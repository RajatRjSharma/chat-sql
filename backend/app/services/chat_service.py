"""Orchestrate analytics chat: RAG prep + LangGraph + persistence."""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import SchemaEmbeddingError, SqlValidationError, WarehouseQueryError
from app.graph.chat_graph import build_chat_graph, initial_chat_state, run_chat_graph
from app.providers.ai import AIClient, get_ai_client
from app.services.chat_persistence import ChatPersistenceService
from app.services.data_source_service import DataSourceService
from app.services.rag_service import RagService
from app.services.schema_introspection import SchemaIntrospectionService
from app.services.sql_validator import SqlValidator
from app.services.warehouse_executor import WarehouseExecutor


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
        await ChatPersistenceService.touch_session(session, chat_session)
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
    async def list_sessions(
        session: AsyncSession,
        *,
        data_source_id: uuid.UUID,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        await DataSourceService.get_active(session, data_source_id)
        return await ChatPersistenceService.list_sessions_for_data_source(
            session,
            data_source_id,
            limit=limit,
        )

    @staticmethod
    async def get_session_detail(
        session: AsyncSession,
        session_id: uuid.UUID,
        *,
        hydrate_results: bool = True,
    ) -> dict[str, Any]:
        """Load a session with messages and reconstructed turns (SQL + live results)."""
        chat = await ChatPersistenceService.get_session_with_messages(session, session_id)
        if chat is None:
            raise ValueError("Session not found")

        messages = sorted(chat.messages, key=lambda m: m.created_at)
        history = sorted(chat.query_history, key=lambda q: q.created_at)
        history_by_question: dict[str, list[Any]] = {}
        for record in history:
            history_by_question.setdefault(record.question, []).append(record)

        turns = ChatService._build_turns(messages, history_by_question)

        if hydrate_results and chat.data_source_id is not None:
            try:
                data_source = await DataSourceService.get_active(
                    session, chat.data_source_id
                )
                info = DataSourceService.connection_info_from_record(data_source)
                turns = await asyncio.to_thread(
                    ChatService._hydrate_turn_results,
                    turns,
                    info,
                )
            except ValueError:
                # Data source deactivated — still return text + SQL.
                pass

        return {
            "session_id": chat.session_id,
            "data_source_id": chat.data_source_id,
            "title": chat.title,
            "created_at": chat.created_at,
            "updated_at": chat.updated_at,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "turns": turns,
        }

    @staticmethod
    def _build_turns(
        messages: list[Any],
        history_by_question: dict[str, list[Any]],
    ) -> list[dict[str, Any]]:
        turns: list[dict[str, Any]] = []
        i = 0
        while i < len(messages):
            msg = messages[i]
            if msg.role != "user":
                i += 1
                continue

            question = msg.content
            answer = ""
            status: str = "ok"
            sql: str | None = None

            if i + 1 < len(messages) and messages[i + 1].role == "assistant":
                answer = messages[i + 1].content
                i += 2
            else:
                i += 1

            queue = history_by_question.get(question)
            if queue:
                record = queue.pop(0)
                sql = record.sql_query
                if record.status in ("ok", "failed", "running"):
                    status = record.status

            turns.append(
                {
                    "question": question,
                    "answer": answer or "No answer stored.",
                    "sql": sql,
                    "columns": [],
                    "rows": [],
                    "status": status,
                    "attempts": 0,
                }
            )
        return turns

    @staticmethod
    def _hydrate_turn_results(
        turns: list[dict[str, Any]],
        info: Any,
    ) -> list[dict[str, Any]]:
        """Best-effort re-run of stored SELECT SQL so charts/tables reload."""
        hydrated: list[dict[str, Any]] = []
        for turn in turns:
            next_turn = dict(turn)
            sql = turn.get("sql")
            if turn.get("status") == "ok" and sql:
                try:
                    cleaned = SqlValidator.validate(
                        sql,
                        allowed_schema=info.schema_name,
                        allowed_tables=None,
                    )
                    result = WarehouseExecutor.execute(info, cleaned)
                    next_turn["columns"] = result.columns
                    next_turn["rows"] = result.rows
                except (SqlValidationError, WarehouseQueryError, Exception):
                    # Keep text + SQL even if warehouse refresh fails.
                    pass
            hydrated.append(next_turn)
        return hydrated

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
