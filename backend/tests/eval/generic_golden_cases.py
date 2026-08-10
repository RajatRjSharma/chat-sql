"""Cross-domain golden cases — NLP/linking must not assume retail/sales."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class GenericGoldenCase:
    id: str
    domain: str  # hr | iot | sales
    question: str
    expect_intent: str
    must_include_tables: tuple[str, ...] = ()
    min_hops: int | None = None
    rag_seed_tables: tuple[str, ...] = ()
    notes: str = ""
    history: tuple[dict[str, str], ...] = ()
    prior_sql_present: bool = False
    expect_overview: bool = False


GENERIC_GOLDEN_CASES: tuple[GenericGoldenCase, ...] = (
    # --- HR ---
    GenericGoldenCase(
        id="hr_avg_salary_by_department",
        domain="hr",
        question="What is average salary by department?",
        expect_intent="analytics",
        must_include_tables=("payroll_entries", "employees", "departments"),
        min_hops=2,
        rag_seed_tables=("payroll_entries",),
        notes="HR measure salary + dimension department — no sales columns",
    ),
    GenericGoldenCase(
        id="hr_headcount_by_title",
        domain="hr",
        question="Count employees by title",
        expect_intent="analytics",
        must_include_tables=("employees",),
        rag_seed_tables=("employees",),
        notes="Headcount-style ask on employees",
    ),
    GenericGoldenCase(
        id="hr_leave_days_engineering",
        domain="hr",
        question="Total leave days for Engineering",
        expect_intent="analytics",
        must_include_tables=("leave_requests", "employees"),
        min_hops=1,
        rag_seed_tables=("leave_requests",),
        notes="Filter label Engineering must not require North/Web Store lists",
    ),
    GenericGoldenCase(
        id="hr_catalog_overview",
        domain="hr",
        question="summary of the database",
        expect_intent="catalog_overview",
        expect_overview=True,
        must_include_tables=("employees", "departments", "payroll_entries", "leave_requests"),
        rag_seed_tables=("employees",),
        notes="Catalog overview is domain-agnostic",
    ),
    GenericGoldenCase(
        id="hr_follow_up_monthly",
        domain="hr",
        question="break that down by month",
        expect_intent="follow_up",
        must_include_tables=("payroll_entries",),
        rag_seed_tables=("payroll_entries",),
        history=(
            {"role": "user", "content": "average salary by department"},
            {"role": "assistant", "content": "Engineering leads average salary…"},
        ),
        prior_sql_present=True,
        notes="Follow-up detection is structural, not retail",
    ),
    # --- IoT ---
    GenericGoldenCase(
        id="iot_avg_temperature_by_site",
        domain="iot",
        question="Average temperature by site",
        expect_intent="analytics",
        must_include_tables=("sensor_readings", "sensors", "devices", "sites"),
        min_hops=2,
        rag_seed_tables=("sensor_readings",),
        notes="IoT measure temperature + site dimension",
    ),
    GenericGoldenCase(
        id="iot_humidity_trend",
        domain="iot",
        question="Show monthly humidity trends",
        expect_intent="analytics",
        must_include_tables=("sensor_readings",),
        rag_seed_tables=("sensor_readings",),
        notes="humidity is a measure column, not revenue/amount",
    ),
    GenericGoldenCase(
        id="iot_devices_offline",
        domain="iot",
        question="How many devices have status offline?",
        expect_intent="analytics",
        must_include_tables=("devices",),
        rag_seed_tables=("devices",),
        notes="Status filter without retail channel vocab",
    ),
    # --- Cross-cutting refuse / clarify ---
    GenericGoldenCase(
        id="generic_world_cup_refuse",
        domain="hr",
        question="Who won the World Cup?",
        expect_intent="out_of_scope",
        rag_seed_tables=("employees",),
        notes="Trivia refuse on non-sales schema",
    ),
    GenericGoldenCase(
        id="generic_bare_summary_clarify",
        domain="iot",
        question="summary",
        expect_intent="clarify",
        rag_seed_tables=("devices",),
        notes="Clarify is domain-agnostic",
    ),
    GenericGoldenCase(
        id="generic_dp_as_department_not_db",
        domain="hr",
        question="list employees in DP",
        expect_intent="analytics",
        must_include_tables=("employees",),
        rag_seed_tables=("employees",),
        notes="DP alone must NOT become database typo rewrite",
    ),
)
