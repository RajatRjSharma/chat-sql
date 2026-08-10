"""LangGraph state for the analytics chat pipeline."""

from __future__ import annotations

from typing import Any, Literal, TypedDict
from uuid import UUID


class ChatGraphState(TypedDict, total=False):
    data_source_id: UUID
    session_id: UUID | None
    question: str
    history: list[dict[str, str]]
    schema_name: str | None
    schema_context: str
    allowed_tables: list[str]
    connection_url: str
    source_metadata: dict[str, Any]
    sql: str | None
    sql_error: str | None
    columns: list[str] | None
    rows: list[dict[str, Any]] | None
    answer: str | None
    attempts: int
    max_attempts: int
    scope: Literal["answerable", "out_of_scope", "needs_clarification"]
    status: Literal["ok", "failed", "running"]
    # Prepare / NLP (full graph)
    prior_sql: str | None
    intent: str
    intent_confidence: float
    intent_source: str
    normalized_question: str
    retrieval_question: str
    overview: bool
    extra_force_tables: list[str]
    catalog_table_names: list[str]
    linked_chunks: list[dict[str, Any]]
    context_mode: str
    did_expand_retry: bool
    did_empty_retry: bool
    expand_noop: bool
    # Snapshot before empty-retry (keep better outcome)
    pre_empty_retry_snapshot: dict[str, Any]
