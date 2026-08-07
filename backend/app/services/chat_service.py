"""Orchestrate analytics chat: RAG prep + LangGraph + persistence."""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import AsyncIterator
from queue import Empty, Queue
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.exceptions import (
    AIProviderError,
    SchemaEmbeddingError,
    SqlValidationError,
    WarehouseQueryError,
)
from app.core.memory_guard import heavy_memory_op
from app.graph.chat_graph import (
    STAGE_LABELS,
    build_chat_graph,
    initial_chat_state,
    iter_chat_graph,
    run_chat_graph,
)
from app.providers.ai import AIClient, get_ai_client
from app.security.http_errors import GENERIC_AI, GENERIC_CHAT, safe_public_detail
from app.services.catalog_overview import (
    format_catalog_inventory,
    is_catalog_overview_question,
)
from app.services.chat_persistence import ChatPersistenceService
from app.services.data_source_service import DataSourceService
from app.services.follow_up import (
    build_retrieval_query,
    looks_like_follow_up,
    sanitize_source_metadata_for_client,
    tables_from_sql,
)
from app.services.rag_service import RagService
from app.services.schema_chunker import is_synthetic_table
from app.services.schema_introspection import SchemaIntrospectionService
from app.services.schema_linker import (
    SchemaChunk,
    SchemaLinker,
    chunk_from_content,
    parse_allowlist_miss_tables,
)
from app.services.schema_linking_pipeline import apply_schema_linking
from app.services.scope_guard import ScopeGuard
from app.services.source_metadata import build_source_metadata
from app.services.sql_generator import EMPTY_RESULT_SQL_HINT
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
    def _run_graph(graph: Any, state: dict[str, Any]) -> dict[str, Any]:
        """Run LangGraph under the process memory guard (no overlap with TTS)."""
        with heavy_memory_op("chat_graph"):
            return run_chat_graph(graph, state)

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
            ChatService._run_graph, prepared["graph"], prepared["state"]
        )
        prepared, final = await ChatService._maybe_expand_and_retry(
            session,
            prepared=prepared,
            final=final,
        )
        prepared, final = await ChatService._maybe_empty_result_retry(
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
        q_preview = (question or "").strip()[:120]

        try:
            prepared = await ChatService._prepare(
                session,
                user_id=user_id,
                data_source_id=data_source_id,
                question=question,
                session_id=session_id,
                client=client,
            )
        except Exception as exc:
            logger.exception(
                "chat prepare failed user=%s data_source=%s question=%r",
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

        yield ChatService._stage_event("retrieving_context")

        event_queue: Queue[dict[str, Any] | None] = Queue()
        session_key = str(prepared["chat_session"].session_id)

        def worker() -> None:
            last_stage = "retrieving_context"
            try:
                final_state: dict[str, Any] | None = None
                with heavy_memory_op("chat_graph_stream"):
                    for kind, *rest in iter_chat_graph(
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
                            event_queue.put(
                                ChatService._stage_event(
                                    last_stage,
                                    attempts=int(current.get("attempts") or 0),
                                    sql=current.get("sql"),
                                )
                            )
                        elif kind == "final":
                            final_state = rest[0]
                event_queue.put({"type": "_final", "state": final_state or {}})
            except Exception as exc:  # noqa: BLE001
                logger.exception(
                    "chat graph stream failed stage=%s session=%s question=%r",
                    last_stage,
                    session_key,
                    q_preview,
                )
                event_queue.put(
                    {
                        "type": "error",
                        "detail": _public_chat_error(exc),
                        "error_type": type(exc).__name__,
                        "stage": last_stage,
                    }
                )
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
                    try:
                        if ChatService._needs_allowlist_expand(
                            prepared, final_state
                        ) or ChatService._needs_unanswerable_expand(
                            prepared, final_state
                        ):
                            yield ChatService._stage_event("expanding_schema")
                        prepared_out, final_out = await ChatService._maybe_expand_and_retry(
                            session,
                            prepared=prepared,
                            final=final_state,
                        )
                        if ChatService._needs_empty_result_retry(prepared_out, final_out):
                            yield ChatService._stage_event("retrying_empty_sql")
                        prepared_out, final_out = await ChatService._maybe_empty_result_retry(
                            prepared=prepared_out,
                            final=final_out,
                        )
                        result = await ChatService._persist_result(
                            session,
                            prepared=prepared_out,
                            final=final_out,
                        )
                        yield {"type": "result", **result}
                    except Exception as exc:
                        logger.exception(
                            "chat post-graph failed session=%s question=%r",
                            session_key,
                            q_preview,
                        )
                        yield {
                            "type": "error",
                            "detail": _public_chat_error(exc),
                            "error_type": type(exc).__name__,
                            "stage": "persist",
                        }
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
        prior_sql = await ChatPersistenceService.load_last_successful_sql(
            session, chat_session.session_id
        )
        # Only reuse prior SQL for clear follow-ups (not every turn in the session).
        if prior_sql and not looks_like_follow_up(question, history):
            prior_sql = None

        # Follow-ups are retrieval-poor on their own text; anchor with the prior
        # question + its tables so the join path survives the refinement.
        retrieval_query = build_retrieval_query(
            question, history, prior_sql=prior_sql
        )
        seed_rows = await RagService.retrieve_rows(
            session,
            data_source_id,
            retrieval_query,
            client=ai,
        )
        seed_rows = await ChatService._with_prior_turn_tables(
            session,
            data_source_id=data_source_id,
            seed_rows=list(seed_rows),
            prior_sql=prior_sql,
        )
        context_mode = "rag" if seed_rows else "empty"
        linked_chunks = list(seed_rows)
        overview = is_catalog_overview_question(question)

        if seed_rows or overview:
            catalog = await RagService.load_catalog(session, data_source_id)
            if catalog or overview:
                linking = apply_schema_linking(
                    question,
                    list(seed_rows),
                    catalog,
                    default_hops=settings.rag_expand_hops,
                    max_tables=settings.rag_max_tables,
                )
                linked_chunks = linking.linked_chunks
                context_mode = linking.context_mode

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
            prior_successful_sql=prior_sql,
        )

    @staticmethod
    async def _with_prior_turn_tables(
        session: AsyncSession,
        *,
        data_source_id: uuid.UUID,
        seed_rows: list[SchemaChunk],
        prior_sql: str | None,
    ) -> list[SchemaChunk]:
        """Re-seed the tables the prior turn actually joined (follow-up continuity)."""
        wanted = tables_from_sql(prior_sql)
        if not wanted:
            return seed_rows
        present = {c.table.lower() for c in seed_rows if c.table}
        missing = [name for name in wanted if name.lower() not in present]
        if not missing:
            return seed_rows
        fetched = await RagService.fetch_chunks_by_tables(
            session, data_source_id, missing
        )
        if not fetched:
            return seed_rows
        return SchemaLinker.merge_chunks(
            seed_rows,
            fetched,
            max_tables=settings.rag_max_tables,
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
        prior_successful_sql: str | None = None,
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
            "prior_successful_sql": prior_successful_sql,
        }

    @staticmethod
    def _needs_allowlist_expand(
        prepared: dict[str, Any],
        final: dict[str, Any],
    ) -> bool:
        if not settings.rag_expand_on_retry:
            return False
        if prepared.get("_expanded_retry"):
            return False
        if (final.get("status") or "") == "failed":
            missing = parse_allowlist_miss_tables(final.get("sql_error"))
            if not missing:
                missing = parse_allowlist_miss_tables(final.get("answer"))
            return bool(missing)
        return False

    @staticmethod
    def _needs_unanswerable_expand(
        prepared: dict[str, Any],
        final: dict[str, Any],
    ) -> bool:
        """Retry with deeper linking when SQL model refused a BI-shaped ask."""
        if not settings.rag_expand_on_retry:
            return False
        if prepared.get("_expanded_retry"):
            return False
        if final.get("scope") != "out_of_scope":
            return False
        if not prepared.get("linked_chunks"):
            return False
        question = prepared.get("question") or ""
        if not ScopeGuard.has_analytics_intent(question):
            return False
        # Trivia / hard refuse from the scope gate already set answer before SQL.
        # UNANSWERABLE path also sets OUT_OF_SCOPE_MESSAGE — only retry when we
        # actually entered SQL generation (attempts > 0) or had thin context.
        attempts = int(final.get("attempts") or 0)
        return attempts > 0 or (prepared.get("context_mode") or "").startswith("rag")

    @staticmethod
    async def _maybe_expand_and_retry(
        session: AsyncSession,
        *,
        prepared: dict[str, Any],
        final: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """
        One service-level expand when SQL failed on an allowlist miss, or when
        the SQL model returned UNANSWERABLE for an analytics-shaped question.
        """
        allowlist_miss = ChatService._needs_allowlist_expand(prepared, final)
        unanswerable = ChatService._needs_unanswerable_expand(prepared, final)
        if not allowlist_miss and not unanswerable:
            return prepared, final

        data_source_id = prepared["data_source_id"]
        catalog = await RagService.load_catalog(session, data_source_id)
        if not catalog:
            return prepared, final

        extra: list[SchemaChunk] = []
        if allowlist_miss:
            missing = parse_allowlist_miss_tables(final.get("sql_error"))
            if not missing:
                missing = parse_allowlist_miss_tables(final.get("answer"))
            fetched = await RagService.fetch_chunks_by_tables(
                session, data_source_id, missing
            )
            extra.extend(fetched)

        if unanswerable:
            # Re-run full linking with deeper default hops from original seeds.
            retry_link = apply_schema_linking(
                prepared.get("question") or "",
                list(prepared.get("linked_chunks") or []) + extra,
                catalog,
                default_hops=max(2, settings.rag_expand_hops + 1),
                max_tables=settings.rag_max_tables,
            )
            neighbor_expanded = retry_link.linked_chunks
        else:
            seeds = list(prepared.get("linked_chunks") or []) + extra
            if not seeds:
                return prepared, final
            neighbor_expanded = SchemaLinker.expand(
                seeds,
                catalog,
                hops=max(1, settings.rag_expand_hops),
                max_tables=settings.rag_max_tables,
            )

        if not neighbor_expanded and not extra:
            return prepared, final

        merged = SchemaLinker.merge_chunks(
            list(prepared.get("linked_chunks") or []),
            neighbor_expanded if neighbor_expanded else extra,
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
            prior_successful_sql=prepared.get("prior_successful_sql"),
        )
        rebuilt["_expanded_retry"] = True

        retry_final = await asyncio.to_thread(
            ChatService._run_graph, rebuilt["graph"], rebuilt["state"]
        )
        first_attempts = int(final.get("attempts") or 0)
        retry_attempts = int(retry_final.get("attempts") or 0)
        retry_final["attempts"] = first_attempts + retry_attempts
        return rebuilt, retry_final

    @staticmethod
    def _needs_empty_result_retry(
        prepared: dict[str, Any],
        final: dict[str, Any],
    ) -> bool:
        """One rewrite when SQL ran cleanly but returned zero rows on a BI ask."""
        if prepared.get("_empty_sql_retry"):
            return False
        if (final.get("status") or "") != "ok":
            return False
        if final.get("scope") in {"out_of_scope", "needs_clarification"}:
            return False
        sql = final.get("sql")
        if not isinstance(sql, str) or not sql.strip():
            return False
        rows = final.get("rows")
        if rows is None or len(rows) > 0:
            return False
        question = prepared.get("question") or ""
        return ScopeGuard.has_analytics_intent(question)

    @staticmethod
    async def _maybe_empty_result_retry(
        *,
        prepared: dict[str, Any],
        final: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """
        Re-run the graph once with join-path feedback after an empty result set.

        Does not expand the allowlist — same schema context, corrected SQL.
        """
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

        retry_final = await asyncio.to_thread(
            ChatService._run_graph, prepared["graph"], retry_state
        )
        first_attempts = int(final.get("attempts") or 0)
        retry_attempts = int(retry_final.get("attempts") or 0)

        next_prepared = dict(prepared)
        next_prepared["_empty_sql_retry"] = True

        # Industry pattern: keep the better outcome — never replace a clean empty
        # answer with a failed/out-of-scope retry.
        if ChatService._empty_retry_improves(final, retry_final):
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
        """Retry wins only when it returns a successful non-empty result set."""
        if (retry.get("status") or "") != "ok":
            return False
        if retry.get("scope") in {"out_of_scope", "needs_clarification"}:
            return False
        rows = retry.get("rows")
        return isinstance(rows, list) and len(rows) > 0

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
            prepared.get("source_metadata") or final.get("source_metadata")
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
