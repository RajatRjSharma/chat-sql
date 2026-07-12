"""LangGraph node implementations — thin wrappers over services."""

from __future__ import annotations

from typing import Any

from app.config import settings
from app.core.exceptions import SqlValidationError, WarehouseQueryError
from app.graph.state import ChatGraphState
from app.providers.ai import AIClient
from app.services.rag_service import RagService
from app.services.result_summarizer import ResultSummarizer
from app.services.sql_generator import SqlGenerator
from app.services.sql_validator import SqlValidator
from app.services.warehouse_executor import WarehouseExecutor
from app.warehouse import WarehouseConnectionInfo


def retrieve_schema_node(
    state: ChatGraphState,
    *,
    schema_context: str,
) -> dict[str, Any]:
    """Inject pre-fetched RAG context (loaded async before graph invoke)."""
    return {
        "schema_context": schema_context or RagService.format_context([]),
        "status": "running",
    }


def generate_sql_node(
    state: ChatGraphState,
    *,
    client: AIClient | None = None,
) -> dict[str, Any]:
    attempts = int(state.get("attempts") or 0) + 1
    sql = SqlGenerator.generate(
        question=state["question"],
        schema_context=state.get("schema_context") or "",
        schema_name=state.get("schema_name"),
        history=state.get("history") or [],
        previous_sql=state.get("sql"),
        previous_error=state.get("sql_error"),
        client=client,
    )
    return {
        "sql": sql,
        "sql_error": None,
        "attempts": attempts,
        "status": "running",
    }


def validate_sql_node(state: ChatGraphState) -> dict[str, Any]:
    allowed = set(state.get("allowed_tables") or [])
    try:
        cleaned = SqlValidator.validate(
            state.get("sql") or "",
            allowed_schema=state.get("schema_name"),
            allowed_tables=allowed or None,
        )
        return {"sql": cleaned, "sql_error": None, "status": "running"}
    except SqlValidationError as exc:
        return {"sql_error": str(exc), "status": "running"}


def execute_sql_node(state: ChatGraphState) -> dict[str, Any]:
    info = WarehouseConnectionInfo(
        name="runtime",
        host="",
        port=0,
        database="",
        schema_name=state.get("schema_name"),
        connection_url=state["connection_url"],
        is_readonly=True,
    )
    try:
        result = WarehouseExecutor.execute(info, state["sql"] or "")
        return {
            "columns": result.columns,
            "rows": result.rows,
            "sql_error": None,
            "status": "running",
        }
    except WarehouseQueryError as exc:
        return {"sql_error": str(exc), "columns": None, "rows": None, "status": "running"}


def summarize_node(
    state: ChatGraphState,
    *,
    client: AIClient | None = None,
) -> dict[str, Any]:
    columns = state.get("columns") or []
    rows = state.get("rows") or []
    answer = ResultSummarizer.summarize(
        question=state["question"],
        sql=state.get("sql") or "",
        columns=columns,
        rows=rows,
        client=client,
    )
    return {"answer": answer, "status": "ok"}


def finalize_failure_node(state: ChatGraphState) -> dict[str, Any]:
    error = state.get("sql_error") or "Unable to produce a valid query."
    answer = (
        "I couldn't answer that safely after several attempts. "
        f"Last error: {error}"
    )
    return {"answer": answer, "status": "failed"}


def route_after_validate(state: ChatGraphState) -> str:
    if not state.get("sql_error"):
        return "execute"
    attempts = int(state.get("attempts") or 0)
    max_attempts = int(state.get("max_attempts") or settings.sql_max_attempts)
    if attempts < max_attempts:
        return "retry"
    return "fail"


def route_after_execute(state: ChatGraphState) -> str:
    if state.get("sql_error"):
        attempts = int(state.get("attempts") or 0)
        max_attempts = int(state.get("max_attempts") or settings.sql_max_attempts)
        if attempts < max_attempts:
            return "retry"
        return "fail"
    return "summarize"
