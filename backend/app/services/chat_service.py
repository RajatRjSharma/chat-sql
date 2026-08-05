"""Orchestrate analytics chat: RAG prep + LangGraph + persistence."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from queue import Empty, Queue
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.exceptions import SchemaEmbeddingError, SqlValidationError, WarehouseQueryError
from app.graph.chat_graph import (
    STAGE_LABELS,
    build_chat_graph,
    initial_chat_state,
    iter_chat_graph,
    run_chat_graph,
)
from app.providers.ai import AIClient, get_ai_client
from app.services.catalog_overview import (
    format_catalog_inventory,
    is_catalog_overview_question,
    tables_mentioned_in_question,
)
from app.services.chat_persistence import ChatPersistenceService
from app.services.data_source_service import DataSourceService
from app.services.rag_service import RagService
from app.services.schema_chunker import is_synthetic_table
from app.services.schema_introspection import SchemaIntrospectionService
from app.services.schema_linker import (
    SchemaChunk,
    SchemaLinker,
    chunk_from_content,
    parse_allowlist_miss_tables,
)
from app.services.source_metadata import build_source_metadata
from app.services.sql_validator import SqlValidator
from app.services.warehouse_executor import WarehouseExecutor


class ChatService:
    """High-level chat entrypoint used by the API layer."""

    @staticmethod
    async def ask(
        session: AsyncSession,
        *,
        user_id: uuid.UUID,
        data_source_id: uuid.UUID,
        question: str,
        session_id: uuid.UUID | None = None,
        client: AIClient | None = None,
    ) -> dict[str, Any]:
        prepared = await ChatService._prepare(
            session,
            user_id=user_id,
            data_source_id=data_source_id,
            question=question,
            session_id=session_id,
            client=client,
        )
        final = await asyncio.to_thread(
            run_chat_graph, prepared["graph"], prepared["state"]
        )
        prepared, final = await ChatService._maybe_expand_and_retry(
            session,
            prepared=prepared,
            final=final,
        )
        return await ChatService._persist_result(
            session,
            prepared=prepared,
            final=final,
        )

    @staticmethod
    async def ask_stream(
        session: AsyncSession,
        *,
        user_id: uuid.UUID,
        data_source_id: uuid.UUID,
        question: str,
        session_id: uuid.UUID | None = None,
        client: AIClient | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Yield SSE-ready events: stage… then result (or error)."""
        yield ChatService._stage_event("preparing")

        prepared = await ChatService._prepare(
            session,
            user_id=user_id,
            data_source_id=data_source_id,
            question=question,
            session_id=session_id,
            client=client,
        )
        yield ChatService._stage_event("retrieving_context")

        event_queue: Queue[dict[str, Any] | None] = Queue()

        def worker() -> None:
            try:
                final_state: dict[str, Any] | None = None
                for kind, *rest in iter_chat_graph(prepared["graph"], prepared["state"]):
                    if kind == "stage":
                        node_name, current = rest
                        event_queue.put(
                            ChatService._stage_event(
                                str(node_name),
                                attempts=int(current.get("attempts") or 0),
                                sql=current.get("sql"),
                            )
                        )
                    elif kind == "final":
                        final_state = rest[0]
                event_queue.put({"type": "_final", "state": final_state or {}})
            except Exception as exc:  # noqa: BLE001
                event_queue.put({"type": "error", "detail": str(exc)})
            finally:
                event_queue.put(None)

        loop = asyncio.get_running_loop()
        worker_future = loop.run_in_executor(None, worker)

        try:
            while True:
                item = await asyncio.to_thread(ChatService._queue_get, event_queue)
                if item is None:
                    break
                if item.get("type") == "_final":
                    final_state = item.get("state") or {}
                    if ChatService._needs_allowlist_expand(prepared, final_state):
                        yield ChatService._stage_event("expanding_schema")
                    prepared_out, final_out = await ChatService._maybe_expand_and_retry(
                        session,
                        prepared=prepared,
                        final=final_state,
                    )
                    result = await ChatService._persist_result(
                        session,
                        prepared=prepared_out,
                        final=final_out,
                    )
                    yield {"type": "result", **result}
                elif item.get("type") == "error":
                    yield item
                else:
                    yield item
        finally:
            await worker_future

    @staticmethod
    def _queue_get(queue: Queue[dict[str, Any] | None]) -> dict[str, Any] | None:
        while True:
            try:
                return queue.get(timeout=0.25)
            except Empty:
                continue

    @staticmethod
    def _stage_event(
        stage: str,
        *,
        attempts: int = 0,
        sql: str | None = None,
    ) -> dict[str, Any]:
        return {
            "type": "stage",
            "stage": stage,
            "label": STAGE_LABELS.get(stage, stage.replace("_", " ").title()),
            "attempts": attempts,
            "sql": sql,
        }

    @staticmethod
    async def _prepare(
        session: AsyncSession,
        *,
        user_id: uuid.UUID,
        data_source_id: uuid.UUID,
        question: str,
        session_id: uuid.UUID | None,
        client: AIClient | None,
    ) -> dict[str, Any]:
        ai = client or get_ai_client()
        data_source = await DataSourceService.get_active(
            session, data_source_id, user_id=user_id
        )
        info = DataSourceService.connection_info_from_record(data_source)

        chat_session = await ChatPersistenceService.get_or_create_session(
            session,
            user_id=user_id,
            data_source_id=data_source_id,
            session_id=session_id,
            title=question[:80],
        )
        history = await ChatPersistenceService.load_history(
            session, chat_session.session_id
        )

        seed_rows = await RagService.retrieve_rows(
            session,
            data_source_id,
            question,
            client=ai,
        )
        context_mode = "rag" if seed_rows else "empty"
        linked_chunks = list(seed_rows)
        # Names-only full inventory ONLY for explicit warehouse-wide NL.
        # Do not trigger on retrieving the catalog overview chunk — that path
        # strips column DDL and makes asks like "amounts in invoices" fail.
        overview = is_catalog_overview_question(question)

        if seed_rows or overview:
            catalog = await RagService.load_catalog(session, data_source_id)
            if overview and catalog:
                linked_chunks = catalog
                context_mode = "catalog_overview"
            elif seed_rows:
                # Mention linking: force tables named in the question into seeds.
                catalog_names = [c.table for c in catalog]
                mentioned = tables_mentioned_in_question(question, catalog_names)
                if mentioned:
                    by_table = {c.table.lower(): c for c in catalog}
                    seed_by = {c.table.lower(): c for c in seed_rows}
                    for name in mentioned:
                        chunk = by_table.get(name.lower())
                        if chunk and name.lower() not in seed_by:
                            seed_rows = [*seed_rows, chunk]
                            seed_by[name.lower()] = chunk
                    context_mode = "rag_mentioned"

                expanded = SchemaLinker.expand(
                    seed_rows,
                    catalog,
                    hops=settings.rag_expand_hops,
                    max_tables=settings.rag_max_tables,
                )
                seed_names = {c.table for c in seed_rows}
                if any(c.table not in seed_names for c in expanded):
                    context_mode = (
                        "rag_expanded"
                        if context_mode != "rag_mentioned"
                        else "rag_mentioned_expanded"
                    )
                linked_chunks = expanded

        if not linked_chunks:
            try:
                tables = await asyncio.to_thread(
                    SchemaIntrospectionService.introspect, info
                )
                from app.services.schema_chunker import chunk_tables

                fallback: list[SchemaChunk] = []
                for content, metadata in chunk_tables(tables):
                    parsed = chunk_from_content(content, metadata)
                    if parsed:
                        fallback.append(parsed)
                if fallback:
                    if overview:
                        linked_chunks = fallback
                        context_mode = "catalog_overview"
                    else:
                        linked_chunks = fallback[: settings.rag_max_tables]
                        context_mode = "introspection_fallback"
            except SchemaEmbeddingError:
                linked_chunks = []
                context_mode = "empty"

        return ChatService._build_prepared(
            ai=ai,
            data_source=data_source,
            data_source_id=data_source_id,
            question=question,
            chat_session=chat_session,
            history=history,
            info=info,
            linked_chunks=linked_chunks,
            context_mode=context_mode,
        )

    @staticmethod
    def _build_prepared(
        *,
        ai: AIClient,
        data_source: Any,
        data_source_id: uuid.UUID,
        question: str,
        chat_session: Any,
        history: list[dict[str, str]],
        info: Any,
        linked_chunks: list[SchemaChunk],
        context_mode: str,
    ) -> dict[str, Any]:
        contents = [
            c.content
            for c in linked_chunks
            if context_mode == "catalog_overview" or not is_synthetic_table(c.table)
        ]
        allowed_tables = ChatService._extract_allowed_tables(
            contents,
            info.schema_name,
            linked_chunks=linked_chunks,
        )
        if context_mode == "catalog_overview":
            # Names-only inventory (full DDL for 50+ tables blows the planner context).
            schema_context = format_catalog_inventory(
                schema_name=info.schema_name,
                table_names=allowed_tables,
            )
        else:
            # Never inject catalog/ER overview prose into column-level SQL planning.
            schema_context = RagService.format_context(contents)
        source_metadata = build_source_metadata(
            data_source,
            tables_in_context=allowed_tables,
            chunks_retrieved=len(linked_chunks),
            context_mode=context_mode,
        )

        state = initial_chat_state(
            data_source_id=data_source_id,
            question=question,
            connection_url=info.connection_url,
            schema_name=info.schema_name,
            allowed_tables=allowed_tables,
            session_id=chat_session.session_id,
            history=history,
            source_metadata=source_metadata,
        )
        graph = build_chat_graph(schema_context=schema_context, client=ai)
        return {
            "ai": ai,
            "data_source": data_source,
            "data_source_id": data_source_id,
            "question": question,
            "chat_session": chat_session,
            "info": info,
            "history": history,
            "linked_chunks": linked_chunks,
            "graph": graph,
            "state": state,
            "source_metadata": source_metadata,
            "context_mode": context_mode,
        }

    @staticmethod
    def _needs_allowlist_expand(
        prepared: dict[str, Any],
        final: dict[str, Any],
    ) -> bool:
        if not settings.rag_expand_on_retry:
            return False
        if (final.get("status") or "") != "failed":
            return False
        if prepared.get("_expanded_retry"):
            return False
        missing = parse_allowlist_miss_tables(final.get("sql_error"))
        if not missing:
            missing = parse_allowlist_miss_tables(final.get("answer"))
        return bool(missing)

    @staticmethod
    async def _maybe_expand_and_retry(
        session: AsyncSession,
        *,
        prepared: dict[str, Any],
        final: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """
        One service-level expand when SQL failed on an allowlist miss.

        Fetches missing tables (+ 1-hop neighbors), rebuilds the graph once.
        """
        if not ChatService._needs_allowlist_expand(prepared, final):
            return prepared, final

        missing = parse_allowlist_miss_tables(final.get("sql_error"))
        if not missing:
            missing = parse_allowlist_miss_tables(final.get("answer"))

        data_source_id = prepared["data_source_id"]
        fetched = await RagService.fetch_chunks_by_tables(
            session, data_source_id, missing
        )
        if not fetched:
            return prepared, final

        catalog = await RagService.load_catalog(session, data_source_id)
        neighbor_expanded = SchemaLinker.expand(
            fetched,
            catalog,
            hops=max(1, settings.rag_expand_hops),
            max_tables=settings.rag_max_tables,
        )
        merged = SchemaLinker.merge_chunks(
            list(prepared.get("linked_chunks") or []),
            neighbor_expanded,
            max_tables=settings.rag_max_tables,
        )
        before = {c.table for c in (prepared.get("linked_chunks") or [])}
        if not any(c.table not in before for c in merged):
            return prepared, final

        rebuilt = ChatService._build_prepared(
            ai=prepared["ai"],
            data_source=prepared["data_source"],
            data_source_id=data_source_id,
            question=prepared["question"],
            chat_session=prepared["chat_session"],
            history=prepared.get("history") or [],
            info=prepared["info"],
            linked_chunks=merged,
            context_mode="rag_expanded",
        )
        rebuilt["_expanded_retry"] = True

        retry_final = await asyncio.to_thread(
            run_chat_graph, rebuilt["graph"], rebuilt["state"]
        )
        first_attempts = int(final.get("attempts") or 0)
        retry_attempts = int(retry_final.get("attempts") or 0)
        retry_final["attempts"] = first_attempts + retry_attempts
        return rebuilt, retry_final

    @staticmethod
    async def _persist_result(
        session: AsyncSession,
        *,
        prepared: dict[str, Any],
        final: dict[str, Any],
    ) -> dict[str, Any]:
        status = final.get("status") or "failed"
        sql = final.get("sql")
        answer = final.get("answer") or "No answer produced."
        chat_session = prepared["chat_session"]
        question = prepared["question"]
        data_source_id = prepared["data_source_id"]

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
            "source_metadata": prepared.get("source_metadata")
            or final.get("source_metadata"),
        }

    @staticmethod
    async def list_sessions(
        session: AsyncSession,
        *,
        user_id: uuid.UUID,
        data_source_id: uuid.UUID,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        await DataSourceService.get_active(session, data_source_id, user_id=user_id)
        return await ChatPersistenceService.list_sessions_for_data_source(
            session,
            data_source_id,
            user_id=user_id,
            limit=limit,
        )

    @staticmethod
    async def get_session_detail(
        session: AsyncSession,
        session_id: uuid.UUID,
        *,
        user_id: uuid.UUID,
        hydrate_results: bool = True,
    ) -> dict[str, Any]:
        """Load a session with messages and reconstructed turns (SQL + live results)."""
        chat = await ChatPersistenceService.get_session_with_messages(
            session, session_id, user_id=user_id
        )
        if chat is None:
            raise ValueError("Session not found")

        messages = sorted(chat.messages, key=lambda m: m.created_at)
        history = sorted(chat.query_history, key=lambda q: q.created_at)
        history_by_question: dict[str, list[Any]] = {}
        for record in history:
            history_by_question.setdefault(record.question, []).append(record)

        turns = ChatService._build_turns(messages, history_by_question)
        source_metadata: dict[str, Any] | None = None

        if hydrate_results and chat.data_source_id is not None:
            try:
                data_source = await DataSourceService.get_active(
                    session, chat.data_source_id, user_id=user_id
                )
                info = DataSourceService.connection_info_from_record(data_source)
                source_metadata = build_source_metadata(
                    data_source,
                    tables_in_context=[],
                    chunks_retrieved=0,
                    context_mode="session_reload",
                )
                turns = await asyncio.to_thread(
                    ChatService._hydrate_turn_results,
                    turns,
                    info,
                )
                for turn in turns:
                    turn["source_metadata"] = source_metadata
            except ValueError:
                pass

        return {
            "session_id": chat.session_id,
            "data_source_id": chat.data_source_id,
            "title": chat.title,
            "created_at": chat.created_at,
            "updated_at": chat.updated_at,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "turns": turns,
            "source_metadata": source_metadata,
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
                    pass
            hydrated.append(next_turn)
        return hydrated

    @staticmethod
    def _extract_allowed_tables(
        chunks: list[str],
        schema_name: str | None,
        *,
        linked_chunks: list[SchemaChunk] | None = None,
    ) -> list[str]:
        tables: set[str] = set()
        if linked_chunks:
            for chunk in linked_chunks:
                if chunk.table and not is_synthetic_table(chunk.table):
                    tables.add(chunk.table)
        for chunk in chunks:
            for line in chunk.splitlines():
                if line.startswith("Table:"):
                    qualified = line.split(":", 1)[1].strip()
                    name = (
                        qualified.split(".", 1)[1]
                        if "." in qualified
                        else qualified
                    )
                    if name and not is_synthetic_table(name):
                        tables.add(name)
        return sorted(tables)
