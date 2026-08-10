"""Orchestrate analytics chat: session bootstrap + LangGraph + persistence."""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    AIProviderError,
    SqlValidationError,
    WarehouseQueryError,
)
from app.core.memory_guard import heavy_memory_op
from app.graph.chat_graph import (
    STAGE_LABELS,
    aiter_chat_graph,
    arun_chat_graph,
    build_chat_graph,
    initial_chat_state,
)
from app.graph.chunk_codec import chunks_from_dicts
from app.graph.prep_nodes import _with_prior_turn_tables as _prior_turn_tables_impl
from app.graph.prep_nodes import (
    build_schema_context,
    extract_allowed_tables,
)
from app.graph.retry_policy import (
    empty_retry_improves as graph_empty_retry_improves,
)
from app.graph.retry_policy import (
    needs_allowlist_expand as graph_needs_allowlist_expand,
)
from app.graph.retry_policy import (
    needs_empty_result_retry as graph_needs_empty_result_retry,
)
from app.graph.retry_policy import (
    needs_unanswerable_expand as graph_needs_unanswerable_expand,
)
from app.providers.ai import AIClient, get_ai_client
from app.security.http_errors import GENERIC_AI, GENERIC_CHAT, safe_public_detail
from app.services.chat_persistence import ChatPersistenceService
from app.services.data_source_service import DataSourceService
from app.services.follow_up import sanitize_source_metadata_for_client
from app.services.rag_service import RagService
from app.services.schema_linker import SchemaChunk
from app.services.source_metadata import build_source_metadata
from app.services.sql_validator import SqlValidator
from app.services.warehouse_executor import WarehouseExecutor

logger = logging.getLogger(__name__)


def _public_chat_error(exc: BaseException) -> str:
    """Map pipeline failures to a safe browser-facing detail."""
    if isinstance(exc, AIProviderError):
        return GENERIC_AI
    return safe_public_detail(exc, fallback=GENERIC_CHAT)


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
        prepared = await ChatService._bootstrap(
            session,
            user_id=user_id,
            data_source_id=data_source_id,
            question=question,
            session_id=session_id,
            client=client,
        )
        with heavy_memory_op("chat_graph"):
            final = await arun_chat_graph(prepared["graph"], prepared["state"])
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
        q_preview = (question or "").strip()[:120]

        try:
            prepared = await ChatService._bootstrap(
                session,
                user_id=user_id,
                data_source_id=data_source_id,
                question=question,
                session_id=session_id,
                client=client,
            )
        except Exception as exc:
            logger.exception(
                "chat bootstrap failed user=%s data_source=%s question=%r",
                user_id,
                data_source_id,
                q_preview,
            )
            yield {
                "type": "error",
                "detail": _public_chat_error(exc),
                "error_type": type(exc).__name__,
                "stage": "preparing",
            }
            return

        session_key = str(prepared["chat_session"].session_id)
        last_stage = "preparing"
        final_state: dict[str, Any] | None = None

        try:
            with heavy_memory_op("chat_graph_stream"):
                async for kind, *rest in aiter_chat_graph(
                    prepared["graph"], prepared["state"]
                ):
                    if kind == "stage":
                        node_name, current = rest
                        last_stage = str(node_name)
                        logger.info(
                            "chat stage=%s attempts=%s session=%s",
                            last_stage,
                            int(current.get("attempts") or 0),
                            session_key,
                        )
                        yield ChatService._stage_event(
                            last_stage,
                            attempts=int(current.get("attempts") or 0),
                            sql=current.get("sql"),
                        )
                    elif kind == "final":
                        final_state = rest[0]
        except Exception as exc:
            logger.exception(
                "chat graph stream failed stage=%s session=%s question=%r",
                last_stage,
                session_key,
                q_preview,
            )
            yield {
                "type": "error",
                "detail": _public_chat_error(exc),
                "error_type": type(exc).__name__,
                "stage": last_stage,
            }
            return

        try:
            result = await ChatService._persist_result(
                session,
                prepared=prepared,
                final=final_state or {},
            )
            yield {"type": "result", **result}
        except Exception as exc:
            logger.exception(
                "chat persist failed session=%s question=%r",
                session_key,
                q_preview,
            )
            yield {
                "type": "error",
                "detail": _public_chat_error(exc),
                "error_type": type(exc).__name__,
                "stage": "persist",
            }

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
    async def _bootstrap(
        session: AsyncSession,
        *,
        user_id: uuid.UUID,
        data_source_id: uuid.UUID,
        question: str,
        session_id: uuid.UUID | None,
        client: AIClient | None,
    ) -> dict[str, Any]:
        """Load auth/session/catalog; NLP + SQL run inside LangGraph."""
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
        prior_sql = await ChatPersistenceService.load_last_successful_sql(
            session, chat_session.session_id
        )
        catalog = await RagService.load_catalog(session, data_source_id)

        state = initial_chat_state(
            data_source_id=data_source_id,
            question=question,
            connection_url=info.connection_url,
            schema_name=info.schema_name,
            allowed_tables=[],
            session_id=chat_session.session_id,
            history=history,
            source_metadata={},
            prior_sql=prior_sql,
        )
        graph = build_chat_graph(
            client=ai,
            session=session,
            data_source_id=data_source_id,
            catalog=catalog,
            warehouse_info=info,
            data_source=data_source,
        )
        return {
            "ai": ai,
            "data_source": data_source,
            "data_source_id": data_source_id,
            "question": question,
            "chat_session": chat_session,
            "info": info,
            "history": history,
            "catalog": catalog,
            "graph": graph,
            "state": state,
            "prior_successful_sql": prior_sql,
        }

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
        prior_successful_sql: str | None = None,
        intent_metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Test helper: build a SQL-only graph with pre-linked context."""
        schema_context, allowed_tables = build_schema_context(
            linked_chunks,
            context_mode=context_mode,
            schema_name=info.schema_name,
        )
        source_metadata = build_source_metadata(
            data_source,
            tables_in_context=allowed_tables,
            chunks_retrieved=len(linked_chunks),
            context_mode=context_mode,
            intent_metadata=intent_metadata,
        )
        if prior_successful_sql:
            source_metadata = {
                **source_metadata,
                "prior_successful_sql": prior_successful_sql,
            }

        state = initial_chat_state(
            data_source_id=data_source_id,
            question=question,
            connection_url=info.connection_url,
            schema_name=info.schema_name,
            allowed_tables=allowed_tables,
            session_id=chat_session.session_id,
            history=history,
            source_metadata=source_metadata,
            prior_sql=prior_successful_sql,
        )
        state["schema_context"] = schema_context
        state["context_mode"] = context_mode
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
            "prior_successful_sql": prior_successful_sql,
            "intent_metadata": intent_metadata or {},
        }

    # --- Compat shims for unit/eval tests (logic lives in graph.retry_policy) ---

    @staticmethod
    def _needs_allowlist_expand(
        prepared: dict[str, Any],
        final: dict[str, Any],
    ) -> bool:
        merged = {
            **final,
            "did_expand_retry": bool(prepared.get("_expanded_retry")),
        }
        return graph_needs_allowlist_expand(merged)

    @staticmethod
    def _needs_unanswerable_expand(
        prepared: dict[str, Any],
        final: dict[str, Any],
    ) -> bool:
        from app.graph.chunk_codec import chunks_to_dicts

        merged = {
            **final,
            "did_expand_retry": bool(prepared.get("_expanded_retry")),
            "question": prepared.get("question") or final.get("question"),
            "context_mode": prepared.get("context_mode") or "",
            "linked_chunks": chunks_to_dicts(
                list(prepared.get("linked_chunks") or [])
            ),
        }
        return graph_needs_unanswerable_expand(merged)

    @staticmethod
    def _needs_empty_result_retry(
        prepared: dict[str, Any],
        final: dict[str, Any],
    ) -> bool:
        merged = {
            **final,
            "did_empty_retry": bool(prepared.get("_empty_sql_retry")),
            "question": prepared.get("question") or final.get("question"),
        }
        return graph_needs_empty_result_retry(merged)

    @staticmethod
    async def _maybe_expand_and_retry(
        session: AsyncSession,
        *,
        prepared: dict[str, Any],
        final: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Test helper: one expand via graph node, then SQL-only re-invoke."""
        from app.graph.chat_graph import run_chat_graph
        from app.graph.chunk_codec import chunks_to_dicts
        from app.graph.prep_nodes import expand_schema_node

        allowlist_miss = ChatService._needs_allowlist_expand(prepared, final)
        unanswerable = ChatService._needs_unanswerable_expand(prepared, final)
        if not allowlist_miss and not unanswerable:
            return prepared, final

        seed_state = dict(final)
        seed_state["question"] = prepared.get("question") or final.get("question")
        seed_state["linked_chunks"] = chunks_to_dicts(
            list(prepared.get("linked_chunks") or [])
        )
        seed_state["schema_name"] = prepared["info"].schema_name
        seed_state["prior_sql"] = prepared.get("prior_successful_sql")
        seed_state["source_metadata"] = prepared.get("source_metadata") or {}
        seed_state["did_expand_retry"] = False

        patch = await expand_schema_node(
            seed_state,  # type: ignore[arg-type]
            session=session,
            data_source_id=prepared["data_source_id"],
            catalog=list(prepared.get("catalog") or []),
            data_source=prepared.get("data_source"),
        )
        if patch.get("expand_noop"):
            return prepared, final

        merged_chunks = chunks_from_dicts(patch.get("linked_chunks"))
        rebuilt = ChatService._build_prepared(
            ai=prepared["ai"],
            data_source=prepared["data_source"],
            data_source_id=prepared["data_source_id"],
            question=prepared["question"],
            chat_session=prepared["chat_session"],
            history=prepared.get("history") or [],
            info=prepared["info"],
            linked_chunks=merged_chunks,
            context_mode="rag_expanded",
            prior_successful_sql=prepared.get("prior_successful_sql"),
            intent_metadata=prepared.get("intent_metadata"),
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
    async def _maybe_empty_result_retry(
        *,
        prepared: dict[str, Any],
        final: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Test helper mirroring in-graph empty-result retry."""
        from app.graph.chat_graph import run_chat_graph
        from app.graph.retry_policy import empty_retry_improves
        from app.services.sql_generator import EMPTY_RESULT_SQL_HINT

        if not ChatService._needs_empty_result_retry(prepared, final):
            return prepared, final

        retry_state = dict(prepared["state"])
        retry_state["sql"] = final.get("sql")
        retry_state["sql_error"] = EMPTY_RESULT_SQL_HINT
        retry_state["columns"] = None
        retry_state["rows"] = None
        retry_state["answer"] = None
        retry_state["attempts"] = 0
        retry_state["scope"] = "answerable"
        retry_state["status"] = "running"
        retry_state["did_empty_retry"] = True

        retry_final = await asyncio.to_thread(
            run_chat_graph, prepared["graph"], retry_state
        )
        first_attempts = int(final.get("attempts") or 0)
        retry_attempts = int(retry_final.get("attempts") or 0)
        next_prepared = dict(prepared)
        next_prepared["_empty_sql_retry"] = True

        if empty_retry_improves(final, retry_final):
            retry_final["attempts"] = first_attempts + retry_attempts
            return next_prepared, retry_final

        kept = dict(final)
        kept["attempts"] = first_attempts + retry_attempts
        return next_prepared, kept

    @staticmethod
    def _empty_retry_improves(
        first: dict[str, Any],
        retry: dict[str, Any],
    ) -> bool:
        return graph_empty_retry_improves(first, retry)

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

        source_metadata = sanitize_source_metadata_for_client(
            final.get("source_metadata") or prepared.get("source_metadata")
        )

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
            "source_metadata": source_metadata,
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
    async def _with_prior_turn_tables(
        session: AsyncSession,
        *,
        data_source_id: uuid.UUID | str,
        seed_rows: list[SchemaChunk],
        prior_sql: str | None,
    ) -> list[SchemaChunk]:
        """Compat wrapper — used by unit tests; graph uses prep_nodes directly."""
        return await _prior_turn_tables_impl(
            session,
            data_source_id=data_source_id,
            seed_rows=seed_rows,
            prior_sql=prior_sql,
        )

    @staticmethod
    def _extract_allowed_tables(
        chunks: list[str],
        schema_name: str | None,
        *,
        linked_chunks: list[SchemaChunk] | None = None,
    ) -> list[str]:
        _ = schema_name
        return extract_allowed_tables(chunks, linked_chunks=linked_chunks)