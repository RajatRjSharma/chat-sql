"""LangGraph prepare nodes: intent, entity link, RAG retrieve, expand."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.exceptions import SchemaEmbeddingError
from app.graph.chunk_codec import chunks_from_dicts, chunks_to_dicts
from app.graph.state import ChatGraphState
from app.providers.ai import AIClient
from app.services.catalog_overview import (
    format_catalog_inventory,
    is_catalog_overview_question,
)
from app.services.entity_linker import EntityLinker
from app.services.follow_up import build_retrieval_query, looks_like_follow_up, tables_from_sql
from app.services.intent_router import IntentRouter
from app.services.rag_service import RagService
from app.services.schema_chunker import chunk_tables, is_synthetic_table
from app.services.schema_introspection import SchemaIntrospectionService
from app.services.schema_linker import (
    SchemaChunk,
    SchemaLinker,
    chunk_from_content,
    parse_allowlist_miss_tables,
)
from app.services.schema_linking_pipeline import apply_schema_linking
from app.services.source_metadata import build_source_metadata
from app.services.sql_generator import EMPTY_RESULT_SQL_HINT
from app.warehouse import WarehouseConnectionInfo

logger = logging.getLogger(__name__)


def extract_allowed_tables(
    contents: list[str],
    *,
    linked_chunks: list[SchemaChunk] | None = None,
) -> list[str]:
    tables: set[str] = set()
    if linked_chunks:
        for chunk in linked_chunks:
            if chunk.table and not is_synthetic_table(chunk.table):
                tables.add(chunk.table)
    for chunk in contents:
        for line in chunk.splitlines():
            if line.startswith("Table:"):
                qualified = line.split(":", 1)[1].strip()
                name = (
                    qualified.split(".", 1)[1] if "." in qualified else qualified
                )
                if name and not is_synthetic_table(name):
                    tables.add(name)
    return sorted(tables)


def build_schema_context(
    linked_chunks: list[SchemaChunk],
    *,
    context_mode: str,
    schema_name: str | None,
) -> tuple[str, list[str]]:
    contents = [
        c.content
        for c in linked_chunks
        if context_mode == "catalog_overview" or not is_synthetic_table(c.table)
    ]
    allowed = extract_allowed_tables(contents, linked_chunks=linked_chunks)
    if context_mode == "catalog_overview":
        schema_context = format_catalog_inventory(
            schema_name=schema_name,
            table_names=allowed,
        )
    else:
        schema_context = RagService.format_context(contents)
    return schema_context, allowed


async def route_intent_node(
    state: ChatGraphState,
    *,
    client: AIClient | None = None,
    catalog: list[SchemaChunk] | None = None,
) -> dict[str, Any]:
    """IntentRouter — first NLP node in the graph."""
    catalog = catalog or []
    catalog_names = [
        c.table for c in catalog if c.table and not is_synthetic_table(c.table)
    ]
    question = state["question"]
    history = list(state.get("history") or [])
    prior_sql = state.get("prior_sql")

    intent = await asyncio.to_thread(
        IntentRouter.route,
        question,
        history=history,
        prior_sql_present=bool(prior_sql),
        table_names=catalog_names,
        client=client,
    )

    if prior_sql and intent.intent != "follow_up":
        if not looks_like_follow_up(question, history):
            prior_sql = None
    if intent.intent == "follow_up" and not prior_sql:
        intent = IntentRouter.fallback(
            question,
            history=history,
            prior_sql_present=False,
            table_names=catalog_names,
        )

    overview = intent.intent == "catalog_overview"
    if (
        not overview
        and intent.source == "fallback"
        and is_catalog_overview_question(IntentRouter.normalize_question(question))
    ):
        overview = True

    meta = dict(state.get("source_metadata") or {})
    meta.update(intent.to_metadata())
    meta["overview"] = overview

    return {
        "prior_sql": prior_sql,
        "intent": intent.intent,
        "intent_confidence": intent.confidence,
        "intent_source": intent.source,
        "normalized_question": intent.normalized_question or question,
        "retrieval_question": intent.normalized_question or question,
        "overview": overview,
        "extra_force_tables": [],
        "source_metadata": meta,
        "catalog_table_names": catalog_names,
        "status": "running",
    }


async def link_entities_node(
    state: ChatGraphState,
    *,
    client: AIClient | None = None,
    catalog: list[SchemaChunk] | None = None,
) -> dict[str, Any]:
    """EntityLinker — analytics / follow-up only."""
    catalog = catalog or []
    intent = str(state.get("intent") or "")
    overview = bool(state.get("overview"))
    if intent not in {"analytics", "follow_up"} or overview:
        return {"status": "running"}

    catalog_names = list(state.get("catalog_table_names") or [])
    retrieval_question = state.get("retrieval_question") or state["question"]
    entities = await asyncio.to_thread(
        EntityLinker.link,
        retrieval_question,
        table_names=catalog_names,
        catalog_chunks=catalog,
        client=client,
    )
    meta = dict(state.get("source_metadata") or {})
    meta.update(entities.to_metadata())
    if entities.retrieval_query_extra:
        retrieval_question = (
            f"{retrieval_question} {entities.retrieval_query_extra}".strip()
        )
    return {
        "retrieval_question": retrieval_question,
        "extra_force_tables": list(entities.tables),
        "source_metadata": meta,
        "status": "running",
    }


async def _with_prior_turn_tables(
    session: AsyncSession,
    *,
    data_source_id: Any,
    seed_rows: list[SchemaChunk],
    prior_sql: str | None,
) -> list[SchemaChunk]:
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


async def retrieve_and_link_node(
    state: ChatGraphState,
    *,
    session: AsyncSession,
    data_source_id: Any,
    client: AIClient | None = None,
    catalog: list[SchemaChunk] | None = None,
    warehouse_info: WarehouseConnectionInfo | None = None,
    data_source: Any = None,
) -> dict[str, Any]:
    """RAG retrieve + FK expand + context freeze (was ChatService._prepare)."""
    catalog = list(catalog or [])
    overview = bool(state.get("overview"))
    retrieval_question = state.get("retrieval_question") or state["question"]
    prior_sql = state.get("prior_sql")
    history = list(state.get("history") or [])
    extra_force = list(state.get("extra_force_tables") or [])
    intent = str(state.get("intent") or "")

    retrieval_query = build_retrieval_query(
        retrieval_question, history, prior_sql=prior_sql
    )
    seed_rows = await RagService.retrieve_rows(
        session,
        data_source_id,
        retrieval_query,
        client=client,
    )
    seed_rows = await _with_prior_turn_tables(
        session,
        data_source_id=data_source_id,
        seed_rows=list(seed_rows),
        prior_sql=prior_sql,
    )
    context_mode = "rag" if seed_rows else "empty"
    linked_chunks = list(seed_rows)

    if seed_rows or overview:
        if catalog or overview:
            linking = apply_schema_linking(
                retrieval_question,
                list(seed_rows),
                catalog,
                default_hops=settings.rag_expand_hops,
                max_tables=settings.rag_max_tables,
                overview=overview,
                extra_force_tables=extra_force or None,
            )
            linked_chunks = linking.linked_chunks
            context_mode = linking.context_mode

    if not linked_chunks and warehouse_info is not None:
        try:
            tables = await asyncio.to_thread(
                SchemaIntrospectionService.introspect, warehouse_info
            )
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

    if intent in {"clarify", "out_of_scope"} and not linked_chunks and catalog:
        linked_chunks = list(catalog)[: settings.rag_max_tables]
        context_mode = context_mode if context_mode != "empty" else "rag"

    schema_context, allowed = build_schema_context(
        linked_chunks,
        context_mode=context_mode,
        schema_name=state.get("schema_name"),
    )

    intent_meta = {
        k: v
        for k, v in (state.get("source_metadata") or {}).items()
        if k
        in {
            "intent",
            "intent_confidence",
            "intent_reason",
            "normalized_question",
            "intent_source",
            "llm_router_model",
            "nlp_prefer_llm",
            "linked_tables",
            "linked_measures",
            "linked_dimensions",
            "linked_filters",
            "time_grain",
            "entity_source",
            "overview",
        }
    }
    source_metadata = build_source_metadata(
        data_source,
        tables_in_context=allowed,
        chunks_retrieved=len(linked_chunks),
        context_mode=context_mode,
        intent_metadata=intent_meta,
    )
    if prior_sql:
        source_metadata = {**source_metadata, "prior_successful_sql": prior_sql}

    return {
        "linked_chunks": chunks_to_dicts(linked_chunks),
        "context_mode": context_mode,
        "schema_context": schema_context,
        "allowed_tables": allowed,
        "source_metadata": source_metadata,
        "status": "running",
    }


def inject_schema_node(
    state: ChatGraphState,
    *,
    schema_context: str,
) -> dict[str, Any]:
    """Test / SQL-only path: inject pre-built schema text."""
    from app.services.rag_service import RagService as _Rag

    return {
        "schema_context": schema_context or _Rag.format_context([]),
        "status": "running",
    }


async def expand_schema_node(
    state: ChatGraphState,
    *,
    session: AsyncSession,
    data_source_id: Any,
    catalog: list[SchemaChunk] | None = None,
    data_source: Any = None,
) -> dict[str, Any]:
    """One-shot FK / allowlist expand inside the graph."""
    catalog = list(catalog or [])
    if not catalog:
        catalog = await RagService.load_catalog(session, data_source_id)
    if not catalog:
        return {"expand_noop": True, "did_expand_retry": True}

    existing = chunks_from_dicts(state.get("linked_chunks"))
    extra: list[SchemaChunk] = []
    allowlist_miss = bool(
        parse_allowlist_miss_tables(state.get("sql_error"))
        or parse_allowlist_miss_tables(state.get("answer"))
    )
    unanswerable = state.get("scope") == "out_of_scope"

    if allowlist_miss:
        missing = parse_allowlist_miss_tables(state.get("sql_error"))
        if not missing:
            missing = parse_allowlist_miss_tables(state.get("answer"))
        fetched = await RagService.fetch_chunks_by_tables(
            session, data_source_id, missing
        )
        extra.extend(fetched)

    if unanswerable:
        retry_link = apply_schema_linking(
            state.get("question") or "",
            list(existing) + extra,
            catalog,
            default_hops=max(2, settings.rag_expand_hops + 1),
            max_tables=settings.rag_max_tables,
        )
        neighbor_expanded = retry_link.linked_chunks
    else:
        seeds = list(existing) + extra
        if not seeds:
            return {"expand_noop": True, "did_expand_retry": True}
        neighbor_expanded = SchemaLinker.expand(
            seeds,
            catalog,
            hops=max(1, settings.rag_expand_hops),
            max_tables=settings.rag_max_tables,
        )

    if not neighbor_expanded and not extra:
        return {"expand_noop": True, "did_expand_retry": True}

    merged = SchemaLinker.merge_chunks(
        existing,
        neighbor_expanded if neighbor_expanded else extra,
        max_tables=settings.rag_max_tables,
    )
    before = {c.table for c in existing}
    if not any(c.table not in before for c in merged):
        return {"expand_noop": True, "did_expand_retry": True}

    schema_context, allowed = build_schema_context(
        merged,
        context_mode="rag_expanded",
        schema_name=state.get("schema_name"),
    )
    intent_meta = dict(state.get("source_metadata") or {})
    source_metadata = build_source_metadata(
        data_source,
        tables_in_context=allowed,
        chunks_retrieved=len(merged),
        context_mode="rag_expanded",
        intent_metadata={
            k: intent_meta.get(k)
            for k in (
                "intent",
                "intent_confidence",
                "intent_reason",
                "normalized_question",
                "intent_source",
                "llm_router_model",
                "nlp_prefer_llm",
                "linked_tables",
                "linked_measures",
                "linked_dimensions",
                "linked_filters",
                "time_grain",
                "entity_source",
            )
            if intent_meta.get(k) is not None
        },
    )
    if state.get("prior_sql"):
        source_metadata = {
            **source_metadata,
            "prior_successful_sql": state.get("prior_sql"),
        }

    return {
        "linked_chunks": chunks_to_dicts(merged),
        "context_mode": "rag_expanded",
        "schema_context": schema_context,
        "allowed_tables": allowed,
        "source_metadata": source_metadata,
        "did_expand_retry": True,
        "expand_noop": False,
        "sql": None,
        "sql_error": None,
        "answer": None,
        "columns": None,
        "rows": None,
        "attempts": 0,
        "scope": "answerable",
        "status": "running",
    }


def prepare_empty_retry_node(state: ChatGraphState) -> dict[str, Any]:
    """Reset SQL loop with empty-result hint (same allowlist)."""
    snapshot = {
        "answer": state.get("answer"),
        "sql": state.get("sql"),
        "columns": state.get("columns"),
        "rows": state.get("rows"),
        "status": state.get("status"),
        "scope": state.get("scope"),
        "attempts": state.get("attempts"),
        "sql_error": state.get("sql_error"),
    }
    return {
        "pre_empty_retry_snapshot": snapshot,
        "sql_error": EMPTY_RESULT_SQL_HINT,
        "columns": None,
        "rows": None,
        "answer": None,
        "attempts": 0,
        "scope": "answerable",
        "status": "running",
        "did_empty_retry": True,
        # Keep prior SQL as previous_sql for the generator via state["sql"].
    }


def resolve_empty_retry_node(state: ChatGraphState) -> dict[str, Any]:
    """Keep the better of first empty vs rewrite attempt."""
    from app.graph.retry_policy import empty_retry_improves

    snap = dict(state.get("pre_empty_retry_snapshot") or {})
    if not snap:
        return {"pre_empty_retry_snapshot": {}}
    current = dict(state)
    first_attempts = int(snap.get("attempts") or 0)
    retry_attempts = int(current.get("attempts") or 0)
    total = first_attempts + retry_attempts
    if empty_retry_improves(snap, current):
        return {
            "attempts": total,
            "pre_empty_retry_snapshot": {},
        }
    return {
        "answer": snap.get("answer"),
        "sql": snap.get("sql"),
        "columns": snap.get("columns"),
        "rows": snap.get("rows"),
        "status": snap.get("status") or "ok",
        "scope": snap.get("scope") or "answerable",
        "sql_error": snap.get("sql_error"),
        "attempts": total,
        "pre_empty_retry_snapshot": {},
    }
