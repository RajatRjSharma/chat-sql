"""Retry / expand policy for the chat LangGraph (state-based)."""

from __future__ import annotations

from typing import Any

from app.config import settings
from app.graph.chunk_codec import chunks_from_dicts
from app.services.schema_linker import parse_allowlist_miss_tables
from app.services.scope_guard import ScopeGuard


def needs_allowlist_expand(state: dict[str, Any]) -> bool:
    if not settings.rag_expand_on_retry:
        return False
    if state.get("did_expand_retry"):
        return False
    missing = parse_allowlist_miss_tables(state.get("sql_error"))
    if not missing:
        missing = parse_allowlist_miss_tables(state.get("answer"))
    return bool(missing)


def needs_unanswerable_expand(state: dict[str, Any]) -> bool:
    if not settings.rag_expand_on_retry:
        return False
    if state.get("did_expand_retry"):
        return False
    if state.get("scope") != "out_of_scope":
        return False
    if not chunks_from_dicts(state.get("linked_chunks")):
        return False
    question = state.get("question") or ""
    if not ScopeGuard.has_analytics_intent(question):
        return False
    attempts = int(state.get("attempts") or 0)
    mode = str(state.get("context_mode") or "")
    return attempts > 0 or mode.startswith("rag")


def needs_empty_result_retry(state: dict[str, Any]) -> bool:
    if state.get("did_empty_retry"):
        return False
    if (state.get("status") or "") != "ok":
        return False
    if state.get("scope") in {"out_of_scope", "needs_clarification"}:
        return False
    sql = state.get("sql")
    if not isinstance(sql, str) or not sql.strip():
        return False
    rows = state.get("rows")
    if rows is None or len(rows) > 0:
        return False
    return ScopeGuard.has_analytics_intent(state.get("question") or "")


def empty_retry_improves(first: dict[str, Any], retry: dict[str, Any]) -> bool:
    if (retry.get("status") or "") != "ok":
        return False
    if retry.get("scope") in {"out_of_scope", "needs_clarification"}:
        return False
    rows = retry.get("rows")
    return isinstance(rows, list) and len(rows) > 0
