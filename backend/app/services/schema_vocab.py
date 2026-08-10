"""Schema-derived vocabulary for domain-agnostic NLP linking.

Builds measure / dimension / fact-table signals from catalog DDL chunks so
routing and linking work for retail, HR, IoT, healthcare, etc. without
hardcoded industry word lists.
"""

from __future__ import annotations

import re
from typing import Any, Protocol

from app.services.schema_chunker import is_synthetic_table

_COLUMN_LINE_RE = re.compile(
    r"^\s*-\s*(?P<name>[A-Za-z_][\w]*)\s*:\s*(?P<type>[^\n(]+)",
    re.MULTILINE,
)
_ID_NAME_RE = re.compile(r"(^id$|_id$)", re.IGNORECASE)

_NUMERIC_TYPE_TOKENS = (
    "int",
    "numeric",
    "decimal",
    "float",
    "double",
    "real",
    "money",
    "bigint",
    "smallint",
    "number",
)
_TEMPORAL_TYPE_TOKENS = ("date", "time", "timestamp")
_TEXT_TYPE_TOKENS = ("char", "text", "enum", "uuid", "bool", "json")

# Structural stems that often hold measures across domains (not industry nouns).
_STRUCTURAL_MEASURE_STEMS = frozenset(
    {
        "amount",
        "total",
        "total_amount",
        "net_amount",
        "line_amount",
        "gross_amount",
        "value",
        "price",
        "unit_price",
        "cost",
        "unit_cost",
        "total_cost",
        "qty",
        "quantity",
        "count",
        "balance",
        "salary",
        "wage",
        "fee",
        "score",
        "rate",
        "ratio",
        "reading",
        "duration",
        "volume",
        "weight",
        "size",
        "length",
        "width",
        "height",
        "temperature",
        "humidity",
        "pressure",
        "usage",
        "metric",
        "measure",
        "headcount",
        "tenure",
        "los",
        "arr",
        "mrr",
    }
)

# English words that usually mean "aggregate a numeric measure" (any domain).
_MEASURE_ASK_TOKENS = frozenset(
    {
        "revenue",
        "sales",
        "gmv",
        "spend",
        "income",
        "turnover",
        "bookings",
        "margin",
        "profit",
        "expense",
        "expenses",
        "cost",
        "costs",
        "kpi",
        "kpis",
        "metric",
        "metrics",
        "measure",
        "measures",
        "total",
        "totals",
        "sum",
        "average",
        "avg",
        "mean",
        "median",
        "count",
        "quantity",
        "volume",
        "salary",
        "compensation",
        "headcount",
        "temperature",
        "humidity",
        "pressure",
        "reading",
        "readings",
        "usage",
        "throughput",
        "latency",
        "duration",
        "score",
        "rate",
    }
)

# Structural fact-table name fragments (domain-neutral).
_FACTISH_NAME_HINTS = (
    "fact",
    "event",
    "events",
    "metric",
    "metrics",
    "measure",
    "txn",
    "transaction",
    "transactions",
    "ledger",
    "entry",
    "entries",
    "line",
    "lines",
    "log",
    "logs",
    "history",
    "reading",
    "readings",
    "usage",
    "record",
    "records",
)


class _ChunkLike(Protocol):
    table: str
    content: str
    metadata: dict[str, Any] | None


def is_numeric_type(data_type: str) -> bool:
    lowered = (data_type or "").lower()
    return any(token in lowered for token in _NUMERIC_TYPE_TOKENS)


def is_temporal_type(data_type: str) -> bool:
    lowered = (data_type or "").lower()
    return any(token in lowered for token in _TEMPORAL_TYPE_TOKENS)


def is_textish_type(data_type: str) -> bool:
    lowered = (data_type or "").lower()
    return any(token in lowered for token in _TEXT_TYPE_TOKENS)


def is_id_column(name: str) -> bool:
    return bool(_ID_NAME_RE.search(name or ""))


def parse_typed_columns(content: str) -> list[dict[str, str]]:
    return [
        {"name": m.group("name"), "data_type": m.group("type").strip()}
        for m in _COLUMN_LINE_RE.finditer(content or "")
    ]


def catalog_measure_columns(catalog_chunks: list[_ChunkLike]) -> list[str]:
    """Numeric non-id columns present in this warehouse (schema-derived)."""
    found: list[str] = []
    seen: set[str] = set()
    for chunk in catalog_chunks:
        if not chunk.table or is_synthetic_table(chunk.table):
            continue
        for col in parse_typed_columns(chunk.content):
            name = col["name"]
            key = name.lower()
            if key in seen or is_id_column(name):
                continue
            if is_numeric_type(col["data_type"]) or key in _STRUCTURAL_MEASURE_STEMS:
                seen.add(key)
                found.append(name)
    return found


def catalog_dimension_columns(catalog_chunks: list[_ChunkLike]) -> list[str]:
    """Likely grouping columns: non-id text/enum/temporal names in this warehouse."""
    found: list[str] = []
    seen: set[str] = set()
    for chunk in catalog_chunks:
        if not chunk.table or is_synthetic_table(chunk.table):
            continue
        for col in parse_typed_columns(chunk.content):
            name = col["name"]
            key = name.lower()
            if key in seen or is_id_column(name):
                continue
            dtype = col["data_type"]
            if is_textish_type(dtype) or is_temporal_type(dtype):
                seen.add(key)
                found.append(name)
    return found


def table_has_fk_metadata(chunk: _ChunkLike) -> bool:
    meta = chunk.metadata or {}
    fks = meta.get("foreign_keys") or []
    return bool(fks)


def table_is_factish(table: str, content: str, *, has_fk: bool = False) -> bool:
    """
    Structural fact-table heuristic (any domain).

    True when the table has a numeric non-id measure and at least one of:
    date/time column, FK metadata, or a structural fact-ish name fragment.
    """
    cols = parse_typed_columns(content)
    has_measure = False
    has_temporal = False
    for col in cols:
        if is_id_column(col["name"]):
            continue
        if is_numeric_type(col["data_type"]) or col["name"].lower() in _STRUCTURAL_MEASURE_STEMS:
            has_measure = True
        if is_temporal_type(col["data_type"]):
            has_temporal = True
    if not has_measure:
        return False
    t = (table or "").lower()
    name_hit = any(hint in t for hint in _FACTISH_NAME_HINTS)
    return has_temporal or has_fk or name_hit


def measure_ask_tokens() -> frozenset[str]:
    return _MEASURE_ASK_TOKENS


def structural_measure_stems() -> frozenset[str]:
    return _STRUCTURAL_MEASURE_STEMS


def synonym_columns_for_question_tokens(
    tokens: list[str],
    *,
    catalog_measure_cols: list[str] | None = None,
) -> set[str]:
    """
    Map question tokens to measure column names without retail-only dictionaries.

    - Exact / stem match against this warehouse's numeric columns
    - Measure-ask words (revenue, salary, temperature, …) expand to structural
      stems that actually exist on the catalog (or all structural stems if empty)
    """
    catalog = {c.lower(): c for c in (catalog_measure_cols or [])}
    out: set[str] = set()
    for token in tokens:
        t = token.lower()
        if t in catalog:
            out.add(catalog[t])
            continue
        for col_l, col in catalog.items():
            if t in col_l or col_l in t:
                out.add(col)
        if t in _MEASURE_ASK_TOKENS or t in _STRUCTURAL_MEASURE_STEMS:
            if catalog:
                for col_l, col in catalog.items():
                    stem = col_l.split("_")[-1]
                    if (
                        col_l in _STRUCTURAL_MEASURE_STEMS
                        or stem in _STRUCTURAL_MEASURE_STEMS
                        or any(s in col_l for s in _STRUCTURAL_MEASURE_STEMS)
                    ):
                        out.add(col)
                # Always allow exact structural stems so matching still works
                # when catalog typing is sparse in offline fixtures.
                out.update(_STRUCTURAL_MEASURE_STEMS)
            else:
                out.update(_STRUCTURAL_MEASURE_STEMS)
    return out
