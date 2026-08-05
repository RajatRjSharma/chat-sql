"""Unit tests for shared schema linking pipeline (used by chat + eval)."""

from __future__ import annotations

from app.services.schema_linking_pipeline import apply_schema_linking, real_tables
from tests.eval.catalog_fixture import build_eval_catalog, build_table_chunk


def test_revenue_by_region_channel_includes_customers() -> None:
    catalog = build_eval_catalog()
    result = apply_schema_linking(
        "Total revenue by region and channel",
        [build_table_chunk("orders")],
        catalog,
        default_hops=1,
        max_tables=15,
    )
    allow = set(real_tables(result.linked_chunks))
    assert {"orders", "customers", "channels"} <= allow
    assert result.hops_used >= 2
    assert result.overview is False


def test_overview_returns_full_catalog() -> None:
    catalog = build_eval_catalog()
    result = apply_schema_linking(
        "give me the summary of db",
        [build_table_chunk("__catalog__")],
        catalog,
        default_hops=1,
        max_tables=15,
    )
    assert result.overview is True
    assert result.context_mode == "catalog_overview"
    assert len(real_tables(result.linked_chunks)) >= 10


def test_empty_seeds_without_overview() -> None:
    catalog = build_eval_catalog()
    result = apply_schema_linking("anything", [], catalog)
    assert result.linked_chunks == []
    assert result.context_mode == "empty"
