"""Golden Text-to-SQL evaluation cases (Spider/BIRD-style, offline).

Metrics we approximate without a live warehouse LLM call:

1. **Schema-linking recall** — expected tables appear in the allowlist / context
2. **Overview routing** — warehouse-wide asks use catalog_overview; analytics do not
3. **Context hygiene** — synthetic overview chunks must not pollute column-level SQL context
4. **Scope gate** — in-warehouse asks stay answerable

Live execution accuracy (EX) against Postgres is optional via scripts/eval_live.py
when warehouse credentials are available.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class GoldenCase:
    """One offline eval example for prepare / linking / scope."""

    id: str
    question: str
    # Tables that must be available to the SQL planner (allowlist or DDL context).
    must_include_tables: tuple[str, ...] = ()
    # Tables that must NOT be wrongly pulled in via mention linking alone.
    must_exclude_tables: tuple[str, ...] = ()
    expect_overview: bool = False
    expect_scope_answerable: bool = True
    # Substrings that must not appear in non-overview schema_context.
    forbid_in_context: tuple[str, ...] = ()
    notes: str = ""
    # Seed tables returned by fake RAG (before mention linking / expand).
    rag_seed_tables: tuple[str, ...] = field(default=("orders",))


# Catalog used across golden cases (mirrors a slice of sales_extended).
EVAL_CATALOG_TABLES: tuple[str, ...] = (
    "customers",
    "orders",
    "order_lines",
    "products",
    "invoices",
    "invoice_lines",
    "payments",
    "channels",
    "regions",
    "database_metrics",  # trap for stopword/substring "database"
    "amount_limits",  # trap for stopword "amount"
)

GOLDEN_CASES: tuple[GoldenCase, ...] = (
    GoldenCase(
        id="overview_summary_db",
        question="give me the summary of db",
        expect_overview=True,
        must_include_tables=EVAL_CATALOG_TABLES,
        rag_seed_tables=("__catalog__",),
        notes="Warehouse-wide inventory path",
    ),
    GoldenCase(
        id="invoice_amount_range",
        question="what are the amounts ranging in invoices",
        expect_overview=False,
        must_include_tables=("invoices",),
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
        must_include_tables=("invoices",),
        rag_seed_tables=("__relationships__",),
        notes="Must not trigger names-only overview mode",
    ),
    GoldenCase(
        id="orders_by_region",
        question="What is total amount from orders by region?",
        expect_overview=False,
        must_include_tables=("orders",),
        rag_seed_tables=("orders",),
        notes="Core analytics ask with explicit table mention",
    ),
    GoldenCase(
        id="out_of_scope_trivia",
        question="What is the height of the Burj Khalifa?",
        expect_overview=False,
        expect_scope_answerable=False,
        must_include_tables=(),
        must_exclude_tables=("orders", "customers"),
        rag_seed_tables=("orders",),
        notes="Scope gate should refuse trivia (LLM or no overlap)",
    ),
)
