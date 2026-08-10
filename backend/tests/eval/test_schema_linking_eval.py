"""Offline Text-to-SQL eval: full linking pipeline + routing + hygiene + scope.

Uses the same `apply_schema_linking` path as production ChatService prepare.
Run: `make eval` or `pytest tests/eval -q`
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from app.config import settings
from app.services.catalog_overview import (
    is_catalog_overview_question,
    tables_mentioned_in_question,
)
from app.services.chat_service import ChatService
from app.services.intent_router import IntentRouter
from app.services.schema_chunker import is_synthetic_table
from app.services.schema_linking_pipeline import apply_schema_linking, real_tables
from app.services.scope_guard import ScopeGuard
from tests.eval.catalog_fixture import (
    EVAL_CATALOG_TABLES,
    build_eval_catalog,
    build_table_chunk,
)
from tests.eval.golden_cases import GOLDEN_CASES, GoldenCase


def _run_linking(case: GoldenCase):
    catalog = build_eval_catalog()
    by_name = {c.table: c for c in catalog}
    seeds = [by_name[t] for t in case.rag_seed_tables if t in by_name]
    # IntentRouter fallback drives overview override (covers DP typo).
    intent = IntentRouter.fallback(
        case.question,
        history=list(case.history),
        prior_sql_present=case.prior_sql_present,
        table_names=list(EVAL_CATALOG_TABLES),
    )
    overview = intent.intent == "catalog_overview" or case.expect_overview
    # Missing seed names are ignored (simulates sparse RAG).
    return apply_schema_linking(
        IntentRouter.normalize_question(case.question),
        seeds,
        catalog,
        default_hops=settings.rag_expand_hops,
        max_tables=settings.rag_max_tables,
        overview=overview,
    )


def _capture_schema_context(prepared_mode: str, linked) -> tuple[str, list[str]]:
    info = SimpleNamespace(schema_name="sales", connection_url="postgresql://x")
    data_source = SimpleNamespace(
        id=uuid4(),
        name="Eval Warehouse",
        db_type="postgres",
        host="localhost",
        port=5432,
        database="bi_warehouse",
        schema_name="sales",
        is_readonly=True,
    )
    captured: dict[str, str] = {}

    def _fake_graph(*, schema_context: str, client):  # noqa: ANN001
        captured["schema_context"] = schema_context
        return object()

    with patch("app.services.chat_service.build_chat_graph", side_effect=_fake_graph):
        prepared = ChatService._build_prepared(
            ai=MagicMock(),
            data_source=data_source,
            data_source_id=data_source.id,
            question="eval",
            chat_session=SimpleNamespace(session_id=uuid4()),
            history=[],
            info=info,
            linked_chunks=linked,
            context_mode=prepared_mode,
        )
    return captured["schema_context"], prepared["state"]["allowed_tables"]


@pytest.mark.parametrize("case", GOLDEN_CASES, ids=lambda c: c.id)
def test_overview_routing(case: GoldenCase) -> None:
    normalized = IntentRouter.normalize_question(case.question)
    assert is_catalog_overview_question(normalized) is case.expect_overview


@pytest.mark.parametrize(
    "case",
    [c for c in GOLDEN_CASES if c.expect_intent],
    ids=lambda c: c.id,
)
def test_intent_router_fallback(case: GoldenCase) -> None:
    decision = IntentRouter.fallback(
        case.question,
        history=list(case.history),
        prior_sql_present=case.prior_sql_present,
        table_names=list(EVAL_CATALOG_TABLES),
    )
    assert decision.intent == case.expect_intent, (
        f"{case.id}: expected intent {case.expect_intent}, got {decision.intent}"
    )


@pytest.mark.parametrize(
    "case",
    [c for c in GOLDEN_CASES if c.must_mention_tables],
    ids=lambda c: c.id,
)
def test_mention_linking_recall(case: GoldenCase) -> None:
    mentioned = tables_mentioned_in_question(
        case.question, list(EVAL_CATALOG_TABLES)
    )
    for table in case.must_mention_tables:
        assert table in mentioned, (
            f"{case.id}: expected mention of {table}, got {mentioned}"
        )
    for table in case.must_exclude_tables:
        assert table not in mentioned, (
            f"{case.id}: unexpected mention of {table}"
        )


@pytest.mark.parametrize(
    "case",
    [c for c in GOLDEN_CASES if c.must_include_tables and not c.expect_overview],
    ids=lambda c: c.id,
)
def test_full_pipeline_linking_recall(case: GoldenCase) -> None:
    """End-to-end offline check: production linking must surface required tables.

    This is the gate that would have caught 'revenue by region and channel'
    missing customers before deploy.
    """
    result = _run_linking(case)
    assert result.overview is False
    allow = set(real_tables(result.linked_chunks))

    missing = [t for t in case.must_include_tables if t not in allow]
    assert not missing, (
        f"{case.id}: allowlist missing {missing}. "
        f"got={sorted(allow)} force={result.force_tables} "
        f"hops={result.hops_used} mode={result.context_mode}"
    )
    for table in case.must_exclude_tables:
        assert table not in allow, f"{case.id}: trap table {table} linked"
    if case.min_hops is not None:
        assert result.hops_used >= case.min_hops, (
            f"{case.id}: expected hops>={case.min_hops}, got {result.hops_used}"
        )


@pytest.mark.parametrize(
    "case",
    [c for c in GOLDEN_CASES if c.forbid_in_context],
    ids=lambda c: c.id,
)
def test_context_hygiene_strips_synthetic_overview(case: GoldenCase) -> None:
    result = _run_linking(case)
    # Analytics path must keep real DDL, not names-only inventory.
    mode = "rag_mentioned" if result.context_mode.startswith("rag") else result.context_mode
    context, allowed = _capture_schema_context(mode, result.linked_chunks)
    for table in case.must_include_tables:
        assert table in allowed
        assert f"sales.{table}" in context or f"Table: sales.{table}" in context
    for needle in case.forbid_in_context:
        assert needle not in context
    # Synthetic placeholders never enter allowlist.
    assert not any(is_synthetic_table(t) for t in allowed)


def test_overview_mode_inventory_lists_all_tables() -> None:
    case = next(c for c in GOLDEN_CASES if c.id == "overview_summary_db")
    result = _run_linking(case)
    assert result.overview is True
    assert result.context_mode == "catalog_overview"
    context, allowed = _capture_schema_context("catalog_overview", result.linked_chunks)
    assert "Complete indexed table inventory" in context
    for table in case.must_include_tables:
        assert table in allowed
        assert f"sales.{table}" in context


def test_scope_gate_analytics_vs_trivia() -> None:
    schema = (
        build_table_chunk("orders").content
        + "\n\n"
        + build_table_chunk("invoices").content
    )
    invoice_case = next(c for c in GOLDEN_CASES if c.id == "invoice_amount_range")
    trivia = next(c for c in GOLDEN_CASES if c.id == "out_of_scope_trivia")
    revenue = next(c for c in GOLDEN_CASES if c.id == "revenue_by_region_channel")

    with patch("app.services.scope_guard.get_ai_client") as get_client:
        get_client.return_value.complete.return_value = "OUT_OF_SCOPE"
        for case in (invoice_case, revenue):
            assert (
                ScopeGuard.assess(
                    question=case.question,
                    schema_context=schema,
                    allowed_tables=["orders", "invoices", "customers", "channels"],
                )
                == "answerable"
            ), case.id
        decision = ScopeGuard.assess(
            question=trivia.question,
            schema_context=schema,
            allowed_tables=["orders", "invoices"],
        )
        assert decision == "out_of_scope"


@pytest.mark.parametrize(
    "case",
    [c for c in GOLDEN_CASES if c.expect_scope_answerable],
    ids=lambda c: c.id,
)
def test_scope_answerable_without_llm_when_analytics(case: GoldenCase) -> None:
    """Deterministic analytics/schema overlap must not need the LLM refuse path."""
    result = _run_linking(case)
    schema = "\n\n".join(c.content for c in result.linked_chunks if not is_synthetic_table(c.table))
    with patch("app.services.scope_guard.get_ai_client") as get_client:
        get_client.return_value.complete.return_value = "OUT_OF_SCOPE"
        decision = ScopeGuard.assess(
            question=case.question,
            schema_context=schema or build_table_chunk("orders").content,
            allowed_tables=real_tables(result.linked_chunks) or ["orders"],
        )
    assert decision == "answerable", case.id


def test_empty_allowlist_rejects_tables() -> None:
    from app.services.sql_validator import SqlValidationError, SqlValidator

    with pytest.raises(SqlValidationError, match="allowed table set"):
        SqlValidator.validate(
            "SELECT 1 FROM sales.orders",
            allowed_schema="sales",
            allowed_tables=set(),
        )


def test_revenue_region_channel_regression_snapshot() -> None:
    """Pinned regression for the shipped UNANSWERABLE bug."""
    case = next(c for c in GOLDEN_CASES if c.id == "revenue_by_region_channel")
    result = _run_linking(case)
    allow = set(real_tables(result.linked_chunks))
    assert {"orders", "customers", "channels"} <= allow
    assert result.hops_used >= 2
    # Channel mention must not only latch onto campaign_channels.
    assert "channels" in allow
