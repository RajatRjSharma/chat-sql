"""Golden Text-to-SQL evaluation cases (Spider/BIRD-style, offline).

Metrics we approximate without a live warehouse LLM call:

1. **Schema-linking recall** — expected tables in final allowlist after full pipeline
2. **Overview routing** — warehouse-wide asks use catalog_overview; analytics do not
3. **Context hygiene** — synthetic overview chunks must not pollute column-level SQL context
4. **Scope gate** — in-warehouse asks stay answerable; trivia stays out
5. **UNANSWERABLE expand** — analytics refuses retry with deeper linking

Live execution accuracy (EX) against Postgres is optional via scripts/eval_live.py
when warehouse credentials are available.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from tests.eval.catalog_fixture import EVAL_CATALOG_TABLES

__all__ = [
    "EVAL_CATALOG_TABLES",
    "GOLDEN_CASES",
    "GoldenCase",
]


@dataclass(frozen=True, slots=True)
class GoldenCase:
    """One offline eval example for prepare / linking / scope."""

    id: str
    question: str
    # Tables that must appear after full linking pipeline (mention+column+FK expand).
    must_include_tables: tuple[str, ...] = ()
    # Optional: tables that must be name-mentioned (stricter than column linking).
    must_mention_tables: tuple[str, ...] = ()
    # Tables that must NOT be wrongly pulled in via mention linking alone.
    must_exclude_tables: tuple[str, ...] = ()
    expect_overview: bool = False
    expect_scope_answerable: bool = True
    # IntentRouter fallback label (demo-day / routing regressions).
    expect_intent: str | None = None
    # Minimum FK hops the pipeline should choose (multi-dim asks → 2).
    min_hops: int | None = None
    # Substrings that must not appear in non-overview schema_context.
    forbid_in_context: tuple[str, ...] = ()
    notes: str = ""
    # Seed tables returned by fake RAG (before mention linking / expand).
    rag_seed_tables: tuple[str, ...] = field(default=("orders",))
    # When True, thin first-pass allowlist should still recover via retry path tests.
    expect_unanswerable_retry: bool = False
    # Optional history + prior SQL for follow-up intent cases.
    history: tuple[dict[str, str], ...] = ()
    prior_sql_present: bool = False


GOLDEN_CASES: tuple[GoldenCase, ...] = (
    GoldenCase(
        id="overview_summary_db",
        question="give me the summary of db",
        expect_overview=True,
        expect_intent="catalog_overview",
        must_include_tables=EVAL_CATALOG_TABLES,
        rag_seed_tables=("__catalog__",),
        notes="Warehouse-wide inventory path",
    ),
    GoldenCase(
        id="overview_summary_dp_typo",
        question="tell me the summary for the DP",
        expect_overview=True,
        expect_intent="catalog_overview",
        must_include_tables=EVAL_CATALOG_TABLES,
        rag_seed_tables=("__catalog__",),
        notes="Demo-day typo DP→DB must still catalog-overview",
    ),
    GoldenCase(
        id="overview_summary_db_shout",
        question="give me SUMMARY FOR THE DB",
        expect_overview=True,
        expect_intent="catalog_overview",
        must_include_tables=EVAL_CATALOG_TABLES,
        rag_seed_tables=("__catalog__",),
        notes="Demo-day shouted catalog ask",
    ),
    GoldenCase(
        id="clarify_bare_summary",
        question="summary",
        expect_overview=False,
        expect_intent="clarify",
        expect_scope_answerable=False,
        must_include_tables=(),
        rag_seed_tables=("orders",),
        notes="Bare summary must clarify, not invent SQL",
    ),
    GoldenCase(
        id="invoice_amount_range",
        question="what are the amounts ranging in invoices",
        expect_overview=False,
        expect_intent="analytics",
        must_include_tables=("invoices",),
        must_mention_tables=("invoices",),
        forbid_in_context=(
            "Include EVERY table below",
            "Database catalog / schema inventory",
        ),
        rag_seed_tables=("__catalog__", "orders"),
        notes="Regression: catalog chunk must not strip invoice DDL",
    ),
    GoldenCase(
        id="show_tables_related_invoices",
        question="show tables related to invoices",
        expect_overview=False,
        expect_intent="analytics",
        must_include_tables=("invoices",),
        must_mention_tables=("invoices",),
        rag_seed_tables=("__relationships__",),
        notes="Must not trigger names-only overview mode",
    ),
    GoldenCase(
        id="orders_by_region",
        question="What is total amount from orders by region?",
        expect_overview=False,
        expect_intent="analytics",
        must_include_tables=("orders", "customers"),
        must_mention_tables=("orders",),
        min_hops=2,
        rag_seed_tables=("orders",),
        notes="Region is a customers column — must force customers into allowlist",
    ),
    GoldenCase(
        id="revenue_by_region_channel",
        question="give me revenue BASED ON REGION AND SALES CHANNEL",
        expect_overview=False,
        expect_intent="analytics",
        # The production bug: missing customers → SQL UNANSWERABLE.
        must_include_tables=("orders", "customers", "channels"),
        must_mention_tables=("channels", "regions"),
        min_hops=2,
        rag_seed_tables=("orders",),
        expect_unanswerable_retry=True,
        notes="Multi-dim BI ask: revenue synonym + region column + channel dim",
    ),
    GoldenCase(
        id="north_monthly_follow_up",
        question="BREAK DOWN THE MONTHLY REVENUE FOR THE NORTH",
        expect_overview=False,
        expect_intent="follow_up",
        must_include_tables=("orders", "customers"),
        min_hops=2,
        rag_seed_tables=("orders",),
        history=(
            {"role": "user", "content": "revenue by region and channel"},
            {"role": "assistant", "content": "North Web Store leads revenue…"},
        ),
        prior_sql_present=True,
        notes="Demo-day follow-up must reuse prior SQL path",
    ),
    GoldenCase(
        id="revenue_by_segment",
        question="Total revenue by customer segment",
        expect_overview=False,
        expect_intent="analytics",
        must_include_tables=("orders", "customers"),
        min_hops=2,
        rag_seed_tables=("products",),
        notes="Wrong RAG seed still recovers via column/synonym linking",
    ),
    GoldenCase(
        id="invoice_vs_payment_scatter",
        question="Compare invoice total_amount and payment amount",
        expect_overview=False,
        expect_intent="analytics",
        must_include_tables=("invoices", "payments"),
        rag_seed_tables=("orders",),
        notes="Two-measure ask should surface both fact tables",
    ),
    GoldenCase(
        id="out_of_scope_trivia",
        question="What is the height of the Burj Khalifa?",
        expect_overview=False,
        expect_intent=None,
        expect_scope_answerable=False,
        must_include_tables=(),
        must_exclude_tables=("orders", "customers"),
        rag_seed_tables=("orders",),
        notes="Scope gate should refuse trivia (LLM or no overlap)",
    ),
    GoldenCase(
        id="out_of_scope_world_cup",
        question="WHO WON WORLD CUP",
        expect_overview=False,
        expect_intent="out_of_scope",
        expect_scope_answerable=False,
        must_include_tables=(),
        rag_seed_tables=("orders",),
        notes="Demo-day hard refuse",
    ),
    GoldenCase(
        id="stopword_database_trap",
        question="query the database for orders by region",
        expect_overview=False,
        expect_intent="analytics",
        must_include_tables=("orders", "customers"),
        must_exclude_tables=("database_metrics", "amount_limits"),
        rag_seed_tables=("orders",),
        notes="Stopwords must not link trap tables",
    ),
)
