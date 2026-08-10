"""Generic multi-domain NLP / linking eval (HR + IoT + cross-cutting).

Proves IntentRouter + schema linking are not retail/sales-coupled.
Run: pytest tests/eval/test_generic_domains_eval.py -q
"""

from __future__ import annotations

import pytest

from app.config import settings
from app.services.intent_router import IntentRouter
from app.services.schema_linking_pipeline import apply_schema_linking, real_tables
from app.services.schema_vocab import (
    catalog_dimension_columns,
    catalog_measure_columns,
    table_is_factish,
)
from tests.eval.generic_golden_cases import GENERIC_GOLDEN_CASES, GenericGoldenCase
from tests.eval.hr_catalog_fixture import HR_CATALOG_TABLES, build_hr_catalog
from tests.eval.iot_catalog_fixture import IOT_CATALOG_TABLES, build_iot_catalog


def _catalog_for(domain: str):
    if domain == "hr":
        return build_hr_catalog(), list(HR_CATALOG_TABLES)
    if domain == "iot":
        return build_iot_catalog(), list(IOT_CATALOG_TABLES)
    raise AssertionError(f"unknown domain {domain}")


def _run_linking(case: GenericGoldenCase):
    catalog, names = _catalog_for(case.domain)
    by_name = {c.table: c for c in catalog}
    seeds = [by_name[t] for t in case.rag_seed_tables if t in by_name]
    intent = IntentRouter.fallback(
        case.question,
        history=list(case.history),
        prior_sql_present=case.prior_sql_present,
        table_names=names,
    )
    overview = intent.intent == "catalog_overview" or case.expect_overview
    return apply_schema_linking(
        IntentRouter.normalize_question(case.question),
        seeds,
        catalog,
        default_hops=settings.rag_expand_hops,
        max_tables=settings.rag_max_tables,
        overview=overview,
    ), intent


@pytest.mark.parametrize("case", GENERIC_GOLDEN_CASES, ids=lambda c: c.id)
def test_generic_intent_router(case: GenericGoldenCase) -> None:
    catalog, names = _catalog_for(case.domain)
    decision = IntentRouter.fallback(
        case.question,
        history=list(case.history),
        prior_sql_present=case.prior_sql_present,
        table_names=names,
    )
    assert decision.intent == case.expect_intent, (
        f"{case.id}: expected {case.expect_intent}, got {decision.intent}"
    )


@pytest.mark.parametrize(
    "case",
    [c for c in GENERIC_GOLDEN_CASES if c.must_include_tables and not c.expect_overview],
    ids=lambda c: c.id,
)
def test_generic_linking_recall(case: GenericGoldenCase) -> None:
    result, _intent = _run_linking(case)
    assert result.overview is False
    allow = set(real_tables(result.linked_chunks))
    missing = [t for t in case.must_include_tables if t not in allow]
    assert not missing, (
        f"{case.id} ({case.domain}): missing {missing}; got={sorted(allow)}; "
        f"force={result.force_tables} hops={result.hops_used}"
    )
    if case.min_hops is not None:
        assert result.hops_used >= case.min_hops


@pytest.mark.parametrize(
    "case",
    [c for c in GENERIC_GOLDEN_CASES if c.expect_overview],
    ids=lambda c: c.id,
)
def test_generic_catalog_overview(case: GenericGoldenCase) -> None:
    result, intent = _run_linking(case)
    assert intent.intent == "catalog_overview"
    assert result.overview is True
    allow = set(real_tables(result.linked_chunks))
    for table in case.must_include_tables:
        assert table in allow


def test_hr_vocab_is_schema_derived() -> None:
    catalog = build_hr_catalog()
    measures = {c.lower() for c in catalog_measure_columns(catalog)}
    dims = {c.lower() for c in catalog_dimension_columns(catalog)}
    assert "salary" in measures
    assert "bonus" in measures
    assert "name" in dims or "title" in dims or "status" in dims
    assert "amount" not in measures  # sales column must not appear


def test_iot_vocab_is_schema_derived() -> None:
    catalog = build_iot_catalog()
    measures = {c.lower() for c in catalog_measure_columns(catalog)}
    assert "temperature" in measures
    assert "humidity" in measures
    assert "pressure" in measures
    payroll = build_hr_catalog()
    assert "salary" not in {c.lower() for c in catalog_measure_columns(catalog)}
    assert table_is_factish(
        "sensor_readings",
        next(c.content for c in catalog if c.table == "sensor_readings"),
        has_fk=True,
    )
    assert table_is_factish(
        "payroll_entries",
        next(c.content for c in payroll if c.table == "payroll_entries"),
        has_fk=True,
    )


def test_dp_department_not_rewritten_to_db() -> None:
    q = "list employees in DP"
    assert IntentRouter.normalize_question(q) == q
    # Overview context still rewrites.
    overview = "summary for the DP"
    assert "db" in IntentRouter.normalize_question(overview).lower()


def test_entity_linker_hr_has_no_retail_filters() -> None:
    from app.services.entity_linker import EntityLinker

    catalog = build_hr_catalog()
    result = EntityLinker.fallback(
        "Total leave days for Engineering",
        table_names=list(HR_CATALOG_TABLES),
        catalog_chunks=catalog,
    )
    assert "Engineering" in result.filters
    assert "Web Store" not in result.filters
    assert "North" not in result.filters
