"""Compile the analytics chat LangGraph (prepare + SQL loop)."""

from __future__ import annotations

from functools import partial
from typing import Any

from langgraph.graph import END, START, StateGraph
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.graph.nodes import (
    assess_relevance_node,
    execute_sql_node,
    finalize_failure_node,
    generate_sql_node,
    retrieve_schema_node,
    route_after_empty_retry,
    route_after_execute,
    route_after_expand,
    route_after_generate,
    route_after_relevance,
    route_after_summarize,
    route_after_validate,
    summarize_node,
    validate_sql_node,
)
from app.graph.prep_nodes import (
    expand_schema_node,
    link_entities_node,
    prepare_empty_retry_node,
    resolve_empty_retry_node,
    retrieve_and_link_node,
    route_intent_node,
)
from app.graph.state import ChatGraphState
from app.providers.ai import AIClient
from app.services.schema_linker import SchemaChunk
from app.warehouse import WarehouseConnectionInfo


def build_chat_graph(
    *,
    schema_context: str | None = None,
    client: AIClient | None = None,
    session: AsyncSession | None = None,
    data_source_id: Any = None,
    catalog: list[SchemaChunk] | None = None,
    warehouse_info: WarehouseConnectionInfo | None = None,
    data_source: Any = None,
):
    """
    Build a compiled chat graph.

    Full pipeline (industry default): pass ``session`` + ``data_source_id`` (+ catalog).
    Nodes: route_intent → link_entities → retrieve_and_link → SQL loop.

    SQL-only (unit tests): pass ``schema_context`` without ``session``.
    Nodes: retrieve_schema (inject) → SQL loop.
    """
    graph = StateGraph(ChatGraphState)
    catalog = list(catalog or [])
    full_prepare = session is not None and data_source_id is not None

    # --- nodes ---
    if full_prepare:
        graph.add_node(
            "route_intent",
            partial(route_intent_node, client=client, catalog=catalog),
        )
        graph.add_node(
            "link_entities",
            partial(link_entities_node, client=client, catalog=catalog),
        )
        graph.add_node(
            "retrieve_and_link",
            partial(
                retrieve_and_link_node,
                session=session,
                data_source_id=data_source_id,
                client=client,
                catalog=catalog,
                warehouse_info=warehouse_info,
                data_source=data_source,
            ),
        )
        graph.add_node(
            "expand_schema",
            partial(
                expand_schema_node,
                session=session,
                data_source_id=data_source_id,
                catalog=catalog,
                data_source=data_source,
            ),
        )
    else:
        graph.add_node(
            "retrieve_schema",
            partial(retrieve_schema_node, schema_context=schema_context or ""),
        )

        def _expand_noop(state: ChatGraphState) -> dict[str, Any]:
            return {"expand_noop": True, "did_expand_retry": True}

        graph.add_node("expand_schema", _expand_noop)

    graph.add_node(
        "assess_relevance",
        partial(assess_relevance_node, client=client),
    )
    graph.add_node("generate_sql", partial(generate_sql_node, client=client))
    graph.add_node("validate_sql", validate_sql_node)
    graph.add_node("execute_sql", execute_sql_node)
    graph.add_node("summarize", partial(summarize_node, client=client))
    graph.add_node("finalize_failure", finalize_failure_node)
    graph.add_node("prepare_empty_retry", prepare_empty_retry_node)
    graph.add_node("resolve_empty_retry", resolve_empty_retry_node)

    # --- edges ---
    if full_prepare:
        graph.add_edge(START, "route_intent")
        graph.add_edge("route_intent", "link_entities")
        graph.add_edge("link_entities", "retrieve_and_link")
        graph.add_edge("retrieve_and_link", "assess_relevance")
    else:
        graph.add_edge(START, "retrieve_schema")
        graph.add_edge("retrieve_schema", "assess_relevance")

    graph.add_conditional_edges(
        "assess_relevance",
        route_after_relevance,
        {"generate": "generate_sql", "end": END},
    )
    graph.add_conditional_edges(
        "generate_sql",
        route_after_generate,
        {
            "validate": "validate_sql",
            "expand": "expand_schema",
            "resolve_empty": "resolve_empty_retry",
            "end": END,
        },
    )
    graph.add_conditional_edges(
        "validate_sql",
        route_after_validate,
        {
            "execute": "execute_sql",
            "retry": "generate_sql",
            "expand": "expand_schema",
            "resolve_empty": "resolve_empty_retry",
            "fail": "finalize_failure",
        },
    )
    graph.add_conditional_edges(
        "execute_sql",
        route_after_execute,
        {
            "summarize": "summarize",
            "retry": "generate_sql",
            "resolve_empty": "resolve_empty_retry",
            "fail": "finalize_failure",
        },
    )
    graph.add_conditional_edges(
        "summarize",
        route_after_summarize,
        {
            "empty_retry": "prepare_empty_retry",
            "resolve_empty": "resolve_empty_retry",
            "end": END,
        },
    )
    graph.add_conditional_edges(
        "expand_schema",
        route_after_expand,
        {"generate": "generate_sql", "fail": "finalize_failure", "end": END},
    )
    graph.add_conditional_edges(
        "prepare_empty_retry",
        route_after_empty_retry,
        {"generate": "generate_sql"},
    )
    graph.add_edge("resolve_empty_retry", END)
    graph.add_edge("finalize_failure", END)

    return graph.compile()


def initial_chat_state(
    *,
    data_source_id,
    question: str,
    connection_url: str,
    schema_name: str | None,
    allowed_tables: list[str] | None = None,
    session_id=None,
    history: list[dict[str, str]] | None = None,
    max_attempts: int | None = None,
    source_metadata: dict | None = None,
    prior_sql: str | None = None,
) -> ChatGraphState:
    return ChatGraphState(
        data_source_id=data_source_id,
        session_id=session_id,
        question=question,
        history=history or [],
        schema_name=schema_name,
        schema_context="",
        allowed_tables=list(allowed_tables or []),
        connection_url=connection_url,
        source_metadata=source_metadata or {},
        sql=None,
        sql_error=None,
        columns=None,
        rows=None,
        answer=None,
        attempts=0,
        max_attempts=max_attempts or settings.sql_max_attempts,
        scope="answerable",
        status="running",
        prior_sql=prior_sql,
        linked_chunks=[],
        context_mode="",
        did_expand_retry=False,
        did_empty_retry=False,
        expand_noop=False,
        overview=False,
        extra_force_tables=[],
        catalog_table_names=[],
    )


def run_chat_graph(graph, state: ChatGraphState) -> dict[str, Any]:
    """Invoke compiled graph synchronously (SQL-only / tests)."""
    result = graph.invoke(state)
    return dict(result)


async def arun_chat_graph(graph, state: ChatGraphState) -> dict[str, Any]:
    """Invoke compiled graph asynchronously (full prepare + SQL)."""
    result = await graph.ainvoke(state)
    return dict(result)


STAGE_LABELS: dict[str, str] = {
    "preparing": "Preparing session",
    "route_intent": "Routing question intent",
    "link_entities": "Linking schema entities",
    "retrieve_and_link": "Retrieving schema context",
    "retrieve_schema": "Loading schema into the planner",
    "expand_schema": "Expanding related tables",
    "prepare_empty_retry": "Retrying query with safer joins",
    "resolve_empty_retry": "Choosing best query result",
    "retrieving_context": "Retrieving schema context",
    "expanding_schema": "Expanding related tables",
    "retrying_empty_sql": "Retrying query with safer joins",
    "assess_relevance": "Checking question scope",
    "generate_sql": "Generating SQL",
    "validate_sql": "Validating SQL",
    "execute_sql": "Running query",
    "summarize": "Summarizing results",
    "finalize_failure": "Could not complete the analysis",
}


def iter_chat_graph(graph, state: ChatGraphState):
    """
    Stream LangGraph node updates synchronously, then yield the merged final state.

    Yields:
      ("stage", node_name, merged_state_dict)
      ("final", merged_state_dict)
    """
    current: dict[str, Any] = dict(state)
    for update in graph.stream(state, stream_mode="updates"):
        if not isinstance(update, dict):
            continue
        for node_name, patch in update.items():
            if isinstance(patch, dict):
                current.update(patch)
            yield "stage", str(node_name), dict(current)
    yield "final", dict(current)


async def aiter_chat_graph(graph, state: ChatGraphState):
    """Async stream of LangGraph node updates (full pipeline)."""
    current: dict[str, Any] = dict(state)
    async for update in graph.astream(state, stream_mode="updates"):
        if not isinstance(update, dict):
            continue
        for node_name, patch in update.items():
            if isinstance(patch, dict):
                current.update(patch)
            yield "stage", str(node_name), dict(current)
    yield "final", dict(current)
