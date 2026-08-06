"""Profile warehouse tables for LLM SQL planning (date windows, measures, dims).

Run at schema-index time; results are stored on ``DataSource.extra_config`` and
injected into SQL / summary prompts so relative time phrases (\"last 12 months\")
align with observed data rather than wall-clock ``CURRENT_DATE``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from psycopg2 import sql
from psycopg2.extensions import connection as PgConnection

from app.services.schema_introspection import ColumnInfo, TableInfo
from app.warehouse import WarehouseConnectionInfo
from app.warehouse.connect import connect_warehouse

_TEMPORAL_TYPES = frozenset(
    {
        "date",
        "timestamp without time zone",
        "timestamp with time zone",
        "timestamp",
        "time without time zone",
        "time with time zone",
        "time",
    }
)
_NUMERIC_TYPES = frozenset(
    {
        "smallint",
        "integer",
        "bigint",
        "decimal",
        "numeric",
        "real",
        "double precision",
        "money",
        "float",
        "float4",
        "float8",
        "int2",
        "int4",
        "int8",
    }
)
_CATEGORICAL_TYPES = frozenset(
    {
        "character varying",
        "varchar",
        "character",
        "char",
        "text",
        "name",
        "citext",
        "user-defined",  # enums often show up this way
    }
)
# Structural name cues only (any domain). Prefer label/status/type/code fields;
# never encode a specific industry vocabulary here.
_CATEGORICAL_EXACT = frozenset(
    {
        "name",
        "title",
        "label",
        "status",
        "state",
        "type",
        "kind",
        "code",
        "category",
        "class",
        "group",
        "mode",
        "phase",
        "level",
        "role",
        "priority",
        "source",
    }
)
_CATEGORICAL_SUFFIXES = (
    "_name",
    "_title",
    "_label",
    "_status",
    "_state",
    "_type",
    "_kind",
    "_code",
    "_category",
    "_class",
    "_group",
)
_CATEGORICAL_SKIP = frozenset(
    {
        "description",
        "comment",
        "comments",
        "notes",
        "note",
        "body",
        "content",
        "message",
        "email",
        "url",
        "path",
    }
)
_CATEGORICAL_SKIP_SUFFIXES = (
    "_description",
    "_comment",
    "_notes",
    "_body",
    "_message",
    "_email",
    "_url",
)
_SKIP_NUMERIC_NAME_SUFFIXES = ("_id", "_uuid", "_pk")
_MAX_TABLES_DEFAULT = 80
_MAX_TEMPORAL_COLS = 4
_MAX_NUMERIC_COLS = 4
_MAX_CATEGORICAL_COLS = 4
_MAX_TOP_VALUES = 12


@dataclass
class DataProfiler:
    """Collect compact table/column stats from a read-only warehouse."""

    max_tables: int = _MAX_TABLES_DEFAULT
    max_temporal_cols: int = _MAX_TEMPORAL_COLS
    max_numeric_cols: int = _MAX_NUMERIC_COLS
    max_categorical_cols: int = _MAX_CATEGORICAL_COLS
    max_top_values: int = _MAX_TOP_VALUES

    def profile(
        self,
        info: WarehouseConnectionInfo,
        tables: list[TableInfo],
    ) -> dict[str, Any]:
        ordered = sorted(tables, key=lambda t: t.table_name.lower())[: self.max_tables]
        with connect_warehouse(info.connection_url, host=info.host) as conn:
            clock = self._warehouse_clock(conn)
            table_profiles: list[dict[str, Any]] = []
            for table in ordered:
                try:
                    table_profiles.append(self._profile_table(conn, table))
                except Exception as exc:  # noqa: BLE001 — keep indexing resilient
                    table_profiles.append(
                        {
                            "schema": table.schema_name,
                            "table": table.table_name,
                            "qualified_name": table.qualified_name,
                            "error": str(exc)[:200],
                        }
                    )
        return build_profile_document(clock=clock, tables=table_profiles)

    def _warehouse_clock(self, conn: PgConnection) -> dict[str, Any]:
        with conn.cursor() as cur:
            cur.execute("SELECT CURRENT_DATE, NOW()")
            current_date, now = cur.fetchone()
        return {
            "current_date": _jsonable(current_date),
            "now": _jsonable(now),
        }

    def _profile_table(self, conn: PgConnection, table: TableInfo) -> dict[str, Any]:
        temporal = _pick_columns(
            table.columns, _is_temporal, limit=self.max_temporal_cols
        )
        numeric = _pick_columns(
            table.columns,
            lambda c: _is_numeric(c) and not _looks_like_surrogate_key(c),
            limit=self.max_numeric_cols,
        )
        categorical = _pick_categorical(table.columns, limit=self.max_categorical_cols)

        aggregates = self._run_aggregates(conn, table, temporal, numeric)
        cat_stats: list[dict[str, Any]] = []
        for col in categorical:
            cat_stats.append(
                self._run_categorical(conn, table, col, limit=self.max_top_values)
            )

        return {
            "schema": table.schema_name,
            "table": table.table_name,
            "qualified_name": table.qualified_name,
            "row_count": aggregates.get("row_count"),
            "temporal_columns": aggregates.get("temporal_columns") or [],
            "numeric_columns": aggregates.get("numeric_columns") or [],
            "categorical_columns": cat_stats,
            "primary_keys": [c.name for c in table.columns if c.is_primary_key],
            "foreign_keys": [
                {
                    "column": fk.column,
                    "referenced_table": fk.referenced_table,
                    "referenced_column": fk.referenced_column,
                }
                for fk in table.foreign_keys
            ],
        }

    def _run_aggregates(
        self,
        conn: PgConnection,
        table: TableInfo,
        temporal: list[ColumnInfo],
        numeric: list[ColumnInfo],
    ) -> dict[str, Any]:
        select_parts: list[sql.Composable] = [sql.SQL("COUNT(*)::bigint")]
        labels: list[tuple[str, str, str]] = [("row_count", "", "count")]

        for col in temporal:
            select_parts.append(sql.SQL("MIN({})").format(sql.Identifier(col.name)))
            select_parts.append(sql.SQL("MAX({})").format(sql.Identifier(col.name)))
            labels.append(("temporal", col.name, "min"))
            labels.append(("temporal", col.name, "max"))

        for col in numeric:
            select_parts.append(sql.SQL("MIN({})").format(sql.Identifier(col.name)))
            select_parts.append(sql.SQL("MAX({})").format(sql.Identifier(col.name)))
            select_parts.append(
                sql.SQL("AVG({})::float8").format(sql.Identifier(col.name))
            )
            labels.append(("numeric", col.name, "min"))
            labels.append(("numeric", col.name, "max"))
            labels.append(("numeric", col.name, "avg"))

        query = sql.SQL("SELECT {} FROM {}.{}").format(
            sql.SQL(", ").join(select_parts),
            sql.Identifier(table.schema_name),
            sql.Identifier(table.table_name),
        )
        with conn.cursor() as cur:
            cur.execute(query)
            row = cur.fetchone()

        values = list(row or [])
        out: dict[str, Any] = {"row_count": int(values[0] or 0) if values else 0}
        temporal_map: dict[str, dict[str, Any]] = {}
        numeric_map: dict[str, dict[str, Any]] = {}
        for idx, (kind, name, stat) in enumerate(labels[1:], start=1):
            raw = values[idx] if idx < len(values) else None
            if kind == "temporal":
                bucket = temporal_map.setdefault(
                    name, {"name": name, "data_type": _type_of(table, name)}
                )
                bucket[stat] = _jsonable(raw)
            else:
                bucket = numeric_map.setdefault(
                    name, {"name": name, "data_type": _type_of(table, name)}
                )
                bucket[stat] = _jsonable(raw)
        out["temporal_columns"] = list(temporal_map.values())
        out["numeric_columns"] = list(numeric_map.values())
        return out

    def _run_categorical(
        self,
        conn: PgConnection,
        table: TableInfo,
        col: ColumnInfo,
        *,
        limit: int,
    ) -> dict[str, Any]:
        query = sql.SQL(
            """
            SELECT {col} AS value, COUNT(*)::bigint AS freq
            FROM {schema}.{table}
            WHERE {col} IS NOT NULL
            GROUP BY 1
            ORDER BY freq DESC, value ASC
            LIMIT %s
            """
        ).format(
            col=sql.Identifier(col.name),
            schema=sql.Identifier(table.schema_name),
            table=sql.Identifier(table.table_name),
        )
        with conn.cursor() as cur:
            cur.execute(query, (limit,))
            rows = cur.fetchall()
            cur.execute(
                sql.SQL(
                    "SELECT COUNT(DISTINCT {col})::bigint FROM {schema}.{table}"
                ).format(
                    col=sql.Identifier(col.name),
                    schema=sql.Identifier(table.schema_name),
                    table=sql.Identifier(table.table_name),
                )
            )
            distinct = cur.fetchone()[0]
        return {
            "name": col.name,
            "data_type": col.data_type,
            "distinct_count": int(distinct or 0),
            "top_values": [
                {"value": _jsonable(value), "count": int(freq or 0)}
                for value, freq in rows
            ],
        }


def build_profile_document(
    *,
    clock: dict[str, Any],
    tables: list[dict[str, Any]],
) -> dict[str, Any]:
    temporal_windows: list[dict[str, Any]] = []
    total_rows = 0
    for table in tables:
        if table.get("row_count") is not None:
            total_rows += int(table["row_count"] or 0)
        qn = table.get("qualified_name") or table.get("table")
        for col in table.get("temporal_columns") or []:
            if col.get("min") is None and col.get("max") is None:
                continue
            temporal_windows.append(
                {
                    "table": qn,
                    "column": col.get("name"),
                    "min": col.get("min"),
                    "max": col.get("max"),
                    "data_type": col.get("data_type"),
                }
            )

    return {
        "version": 1,
        "profiled_at": _jsonable(datetime.now(UTC).replace(microsecond=0)),
        "warehouse_clock": clock,
        "table_count": len(tables),
        "approx_total_rows": total_rows,
        "temporal_windows": temporal_windows,
        "tables": tables,
    }


def profile_for_tables_in_context(
    profile: dict[str, Any] | None,
    tables_in_context: list[str] | None,
) -> dict[str, Any] | None:
    """Shrink a stored profile to tables relevant to the current RAG context."""
    if not profile:
        return None
    if not tables_in_context:
        return profile

    wanted = {t.lower() for t in tables_in_context if t}
    # Always keep short names and qualified forms.
    filtered_tables: list[dict[str, Any]] = []
    for table in profile.get("tables") or []:
        name = str(table.get("table") or "").lower()
        qn = str(table.get("qualified_name") or "").lower()
        bare_qn = qn.split(".")[-1] if qn else ""
        if name in wanted or qn in wanted or bare_qn in wanted:
            filtered_tables.append(table)

    if not filtered_tables:
        # Keep global clock + windows that touch context tables.
        windows = [
            w
            for w in (profile.get("temporal_windows") or [])
            if str(w.get("table") or "").lower().split(".")[-1] in wanted
            or str(w.get("table") or "").lower() in wanted
        ]
        return {
            **profile,
            "tables": [],
            "temporal_windows": windows,
            "table_count": 0,
            "approx_total_rows": 0,
            "context_filtered": True,
        }

    total_rows = sum(int(t.get("row_count") or 0) for t in filtered_tables)
    windows = [
        w
        for w in (profile.get("temporal_windows") or [])
        if str(w.get("table") or "").lower().split(".")[-1] in wanted
        or str(w.get("table") or "").lower() in wanted
    ]
    return {
        **profile,
        "tables": filtered_tables,
        "temporal_windows": windows,
        "table_count": len(filtered_tables),
        "approx_total_rows": total_rows,
        "context_filtered": True,
    }


def format_data_profile_for_llm(profile: dict[str, Any] | None) -> str:
    """Compact multi-line block for SQL / summary prompts."""
    if not profile:
        return (
            "Data profile: (not yet indexed — refresh schema index to capture "
            "date windows, row counts, and measure ranges)."
        )

    lines: list[str] = [
        "Data profile (authoritative for relative time filters + value domains):",
        f"  Profiled at: {profile.get('profiled_at')}",
    ]
    clock = profile.get("warehouse_clock") or {}
    if clock:
        lines.append(
            f"  Warehouse clock: CURRENT_DATE={clock.get('current_date')} "
            f"NOW={clock.get('now')}"
        )
    lines.append(
        f"  Tables profiled: {profile.get('table_count')} | "
        f"Approx total rows: {profile.get('approx_total_rows')}"
    )
    if profile.get("context_filtered"):
        lines.append("  (filtered to tables in the current schema context)")

    windows = profile.get("temporal_windows") or []
    if windows:
        lines.append(
            "  Observed temporal windows — for 'last N months/years/weeks', prefer "
            "filters relative to these MAX dates (or within min..max), NOT wall-clock "
            "CURRENT_DATE when the window ends earlier than today:"
        )
        for win in windows[:40]:
            lines.append(
                f"    - {win.get('table')}.{win.get('column')}: "
                f"{win.get('min')} .. {win.get('max')}"
            )

    for table in (profile.get("tables") or [])[:60]:
        qn = table.get("qualified_name") or table.get("table")
        if table.get("error"):
            lines.append(f"  {qn}: profile error ({table.get('error')})")
            continue
        bits = [f"rows={table.get('row_count')}"]
        for col in table.get("temporal_columns") or []:
            bits.append(f"{col.get('name')}[{col.get('min')}..{col.get('max')}]")
        for col in table.get("numeric_columns") or []:
            bits.append(
                f"{col.get('name')}[min={col.get('min')}, max={col.get('max')}, "
                f"avg={col.get('avg')}]"
            )
        lines.append(f"  {qn}: " + "; ".join(bits))
        for col in table.get("categorical_columns") or []:
            tops = col.get("top_values") or []
            sample = ", ".join(
                f"{item.get('value')}×{item.get('count')}" for item in tops[:8]
            )
            lines.append(
                f"    {col.get('name')} distinct≈{col.get('distinct_count')}: {sample}"
            )
        fks = table.get("foreign_keys") or []
        if fks:
            fk_txt = ", ".join(
                f"{fk.get('column')}→{fk.get('referenced_table')}."
                f"{fk.get('referenced_column')}"
                for fk in fks[:12]
            )
            lines.append(f"    FKs: {fk_txt}")

    return "\n".join(lines)


def table_profile_lookup(profile: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    """Map bare table name → profile dict."""
    out: dict[str, dict[str, Any]] = {}
    if not profile:
        return out
    for table in profile.get("tables") or []:
        name = str(table.get("table") or "")
        if name:
            out[name.lower()] = table
    return out


def _pick_columns(
    columns: list[ColumnInfo],
    predicate,
    *,
    limit: int,
) -> list[ColumnInfo]:
    picked = [c for c in columns if predicate(c)]
    return picked[:limit]


def _pick_categorical(columns: list[ColumnInfo], *, limit: int) -> list[ColumnInfo]:
    """Pick text-like dims using structural naming — works for any warehouse domain."""
    scored: list[tuple[int, ColumnInfo]] = []
    for col in columns:
        if not _is_categorical(col):
            continue
        if col.is_primary_key or _looks_like_surrogate_key(col):
            continue
        lower = col.name.lower()
        # Skip free-text blobs that are rarely useful as group-by dims.
        if lower in _CATEGORICAL_SKIP:
            continue
        if any(lower.endswith(s) for s in _CATEGORICAL_SKIP_SUFFIXES):
            continue

        score = 1  # any remaining text/enum column is eligible
        if lower in _CATEGORICAL_EXACT:
            score += 5
        if any(lower.endswith(suf) for suf in _CATEGORICAL_SUFFIXES):
            score += 4
        # Prefer shorter attribute names over long free-text fields.
        score += max(0, 3 - (len(lower) // 12))
        scored.append((score, col))
    scored.sort(key=lambda item: (-item[0], item[1].name))
    return [c for _, c in scored[:limit]]


def _is_temporal(col: ColumnInfo) -> bool:
    return (col.data_type or "").lower() in _TEMPORAL_TYPES


def _is_numeric(col: ColumnInfo) -> bool:
    return (col.data_type or "").lower() in _NUMERIC_TYPES


def _is_categorical(col: ColumnInfo) -> bool:
    return (col.data_type or "").lower() in _CATEGORICAL_TYPES


def _looks_like_surrogate_key(col: ColumnInfo) -> bool:
    name = (col.name or "").lower()
    if col.is_primary_key:
        return True
    if name in {"id", "uuid", "guid"}:
        return True
    if name.endswith(_SKIP_NUMERIC_NAME_SUFFIXES):
        return True
    return False


def _type_of(table: TableInfo, name: str) -> str:
    for col in table.columns:
        if col.name == name:
            return col.data_type
    return ""


def _jsonable(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, bytes | memoryview):
        return None
    if isinstance(value, float):
        return round(value, 6)
    return value
