"""Compile the analytics chat LangGraph."""

from __future__ import annotations

from functools import partial
from typing import Any

from langgraph.graph import END, START, StateGraph

from app.config import settings
from app.graph.nodes import (
    execute_sql_node,
    finalize_failure_node,
    generate_sql_node,
    retrieve_schema_node,
    route_after_execute,
    route_after_validate,
    summarize_node,
    validate_sql_node,
)
from app.graph.state import ChatGraphState
from app.providers.openrouter import OpenRouterClient


def build_chat_graph(
    *,
    schema_context: str,
    client: OpenRouterClient | None = None,
):
    """
    Build a compiled chat graph.

    schema_context is injected at build time so async RAG can run before invoke.
    """
    graph = StateGraph(ChatGraphState)

    graph.add_node(
        "retrieve_schema",
        partial(retrieve_schema_node, schema_context=schema_context),
    )
    graph.add_node("generate_sql", partial(generate_sql_node, client=client))
    graph.add_node("validate_sql", validate_sql_node)
    graph.add_node("execute_sql", execute_sql_node)
    graph.add_node("summarize", partial(summarize_node, client=client))
    graph.add_node("finalize_failure", finalize_failure_node)

    graph.add_edge(START, "retrieve_schema")
    graph.add_edge("retrieve_schema", "generate_sql")
    graph.add_edge("generate_sql", "validate_sql")
    graph.add_conditional_edges(
        "validate_sql",
        route_after_validate,
        {
            "execute": "execute_sql",
            "retry": "generate_sql",
            "fail": "finalize_failure",
        },
    )
    graph.add_conditional_edges(
        "execute_sql",
        route_after_execute,
        {
            "summarize": "summarize",
            "retry": "generate_sql",
            "fail": "finalize_failure",
        },
    )
    graph.add_edge("summarize", END)
    graph.add_edge("finalize_failure", END)

    return graph.compile()


def initial_chat_state(
    *,
    data_source_id,
    question: str,
    connection_url: str,
    schema_name: str | None,
    allowed_tables: list[str],
    session_id=None,
    history: list[dict[str, str]] | None = None,
    max_attempts: int | None = None,
) -> ChatGraphState:
    return ChatGraphState(
        data_source_id=data_source_id,
        session_id=session_id,
        question=question,
        history=history or [],
        schema_name=schema_name,
        schema_context="",
        allowed_tables=allowed_tables,
        connection_url=connection_url,
        sql=None,
        sql_error=None,
        columns=None,
        rows=None,
        answer=None,
        attempts=0,
        max_attempts=max_attempts or settings.sql_max_attempts,
        status="running",
    )


def run_chat_graph(graph, state: ChatGraphState) -> dict[str, Any]:
    """Invoke compiled graph and return final state as a plain dict."""
    result = graph.invoke(state)
    return dict(result)
