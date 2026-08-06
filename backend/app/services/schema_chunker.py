"""Convert introspected tables into RAG text chunks.

Industry Text-to-SQL pattern: one chunk per table **plus** compact
warehouse-wide overview chunks (catalog inventory + relationship/ER graph)
so cosine retrieval can surface schema-wide context for overview / join asks.
"""

from __future__ import annotations

from typing import Any

from app.services.schema_introspection import TableInfo

# Synthetic table keys — stored in metadata so chunk_from_content works,
# never added to SQL allowlists.
SYNTHETIC_CATALOG_TABLE = "__catalog__"
SYNTHETIC_RELATIONSHIPS_TABLE = "__relationships__"

CHUNK_KIND_TABLE = "table"
CHUNK_KIND_CATALOG = "catalog_overview"
CHUNK_KIND_RELATIONSHIPS = "relationship_graph"

_OVERVIEW_KINDS = frozenset({CHUNK_KIND_CATALOG, CHUNK_KIND_RELATIONSHIPS})


def is_synthetic_table(name: str | None) -> bool:
    """True for overview-chunk placeholders (not real warehouse tables)."""
    if not name:
        return False
    return name.startswith("__") and name.endswith("__")


def is_overview_chunk_metadata(metadata: dict[str, Any] | None) -> bool:
    kind = (metadata or {}).get("chunk_kind")
    return kind in _OVERVIEW_KINDS


def is_catalog_overview_chunk_metadata(metadata: dict[str, Any] | None) -> bool:
    return (metadata or {}).get("chunk_kind") == CHUNK_KIND_CATALOG


def chunk_table(
    table: TableInfo,
    *,
    warehouse_header: str | None = None,
    table_profile: dict[str, Any] | None = None,
) -> str:
    """Build a single searchable text chunk for one warehouse table."""
    lines: list[str] = []
    if warehouse_header:
        lines.append(warehouse_header)
        lines.append("")
    lines.extend(
        [
            f"Table: {table.qualified_name}",
            "Columns:",
        ]
    )
    for col in table.columns:
        flags: list[str] = []
        if col.is_primary_key:
            flags.append("PK")
        if not col.is_nullable:
            flags.append("NOT NULL")
        suffix = f" ({', '.join(flags)})" if flags else ""
        lines.append(f"  - {col.name}: {col.data_type}{suffix}")

    if table.foreign_keys:
        lines.append("Foreign keys:")
        for fk in table.foreign_keys:
            lines.append(
                f"  - {fk.column} -> {table.schema_name}.{fk.referenced_table}"
                f".{fk.referenced_column}"
            )

    if table_profile and not table_profile.get("error"):
        lines.append("Observed data profile:")
        lines.append(f"  - row_count: {table_profile.get('row_count')}")
        for col in table_profile.get("temporal_columns") or []:
            lines.append(
                f"  - {col.get('name')} window: {col.get('min')} .. {col.get('max')}"
            )
        for col in table_profile.get("numeric_columns") or []:
            lines.append(
                f"  - {col.get('name')} range: min={col.get('min')} "
                f"max={col.get('max')} avg={col.get('avg')}"
            )
        for col in table_profile.get("categorical_columns") or []:
            tops = col.get("top_values") or []
            sample = ", ".join(str(item.get("value")) for item in tops[:8])
            lines.append(
                f"  - {col.get('name')} values (top): {sample} "
                f"(distinct≈{col.get('distinct_count')})"
            )

    if table.sample_rows:
        lines.append("Sample rows:")
        for row in table.sample_rows:
            rendered = ", ".join(f"{k}={v!r}" for k, v in row.items())
            lines.append(f"  - {rendered}")

    return "\n".join(lines)


def _engine_fields(engine_meta: dict[str, Any] | None) -> dict[str, Any]:
    if not engine_meta:
        return {}
    return {
        "db_type": engine_meta.get("db_type"),
        "engine": engine_meta.get("engine"),
        "sql_dialect": engine_meta.get("sql_dialect"),
        "vendor": engine_meta.get("vendor"),
    }


def _schema_name(tables: list[TableInfo]) -> str | None:
    for table in tables:
        if table.schema_name:
            return table.schema_name
    return None


def build_catalog_overview_chunk(
    tables: list[TableInfo],
    *,
    warehouse_header: str | None = None,
    engine_meta: dict[str, Any] | None = None,
    table_profiles: dict[str, dict[str, Any]] | None = None,
) -> tuple[str, dict[str, Any]]:
    """
    Warehouse-wide inventory chunk — retrieves for “summary of db / all tables”.

    Compact: table list + PK/column names (not full sample rows).
    """
    schema = _schema_name(tables)
    ordered = sorted(tables, key=lambda t: t.table_name.lower())
    profiles = table_profiles or {}
    lines: list[str] = []
    if warehouse_header:
        lines.append(warehouse_header)
        lines.append("")
    scope = f" for {schema}" if schema else ""
    lines.extend(
        [
            f"Database catalog / schema inventory{scope} ({len(ordered)} tables).",
            "Use for warehouse overview, summary of the database, listing all tables,",
            "row counts across the schema, and schema inventory questions.",
            "Include EVERY table below when answering overview / all-tables questions.",
            "",
            "Tables:",
        ]
    )
    for table in ordered:
        pks = [c.name for c in table.columns if c.is_primary_key]
        col_names = [c.name for c in table.columns]
        pk_bit = f" PK={','.join(pks)}" if pks else ""
        profile = profiles.get(table.table_name.lower()) or {}
        rows_bit = ""
        if profile.get("row_count") is not None:
            rows_bit = f" rows={profile.get('row_count')}"
        windows = []
        for col in profile.get("temporal_columns") or []:
            windows.append(f"{col.get('name')}[{col.get('min')}..{col.get('max')}]")
        window_bit = f" dates={','.join(windows)}" if windows else ""
        lines.append(
            f"- {table.qualified_name} ({len(col_names)} cols{pk_bit}{rows_bit}"
            f"{window_bit}): "
            + ", ".join(col_names)
        )

    metadata: dict[str, Any] = {
        "chunk_kind": CHUNK_KIND_CATALOG,
        "schema": schema,
        "table": SYNTHETIC_CATALOG_TABLE,
        "qualified_name": (
            f"{schema}.{SYNTHETIC_CATALOG_TABLE}" if schema else SYNTHETIC_CATALOG_TABLE
        ),
        "table_count": len(ordered),
        "foreign_keys": [],
        **_engine_fields(engine_meta),
    }
    return "\n".join(lines), metadata


def build_relationship_graph_chunk(
    tables: list[TableInfo],
    *,
    warehouse_header: str | None = None,
    engine_meta: dict[str, Any] | None = None,
) -> tuple[str, dict[str, Any]]:
    """
    ER / FK graph chunk — retrieves for join paths and “how are tables related”.
    """
    schema = _schema_name(tables)
    edges: list[tuple[str, str, str, str, str]] = []
    for table in tables:
        for fk in table.foreign_keys:
            edges.append(
                (
                    table.schema_name,
                    table.table_name,
                    fk.column,
                    fk.referenced_table,
                    fk.referenced_column,
                )
            )
    edges.sort(key=lambda e: (e[1], e[3], e[2]))

    lines: list[str] = []
    if warehouse_header:
        lines.append(warehouse_header)
        lines.append("")
    scope = f" for {schema}" if schema else ""
    lines.extend(
        [
            f"Schema relationship graph / ER overview{scope} ({len(edges)} foreign keys).",
            "Use for joins, foreign-key navigation, entity-relationship questions,",
            "and multi-table analytics that need related tables.",
            "",
            "Relationships:",
        ]
    )
    if not edges:
        lines.append("- (no foreign keys discovered)")
    else:
        for sch, table, col, ref_table, ref_col in edges:
            lines.append(
                f"- {sch}.{table}.{col} -> {sch}.{ref_table}.{ref_col}"
            )

    # Structured edges for schema linker / tooling (synthetic chunk itself
    # is not a join node; real tables still carry per-table FK metadata).
    fk_meta = [
        {
            "column": col,
            "from_table": table,
            "referenced_table": ref_table,
            "referenced_column": ref_col,
        }
        for _sch, table, col, ref_table, ref_col in edges
    ]

    metadata: dict[str, Any] = {
        "chunk_kind": CHUNK_KIND_RELATIONSHIPS,
        "schema": schema,
        "table": SYNTHETIC_RELATIONSHIPS_TABLE,
        "qualified_name": (
            f"{schema}.{SYNTHETIC_RELATIONSHIPS_TABLE}"
            if schema
            else SYNTHETIC_RELATIONSHIPS_TABLE
        ),
        "edge_count": len(edges),
        "foreign_keys": fk_meta,
        **_engine_fields(engine_meta),
    }
    return "\n".join(lines), metadata


def chunk_tables(
    tables: list[TableInfo],
    *,
    warehouse_header: str | None = None,
    engine_meta: dict[str, Any] | None = None,
    include_overview_chunks: bool = True,
    table_profiles: dict[str, dict[str, Any]] | None = None,
) -> list[tuple[str, dict]]:
    """
    Return (content, metadata) pairs for embedding storage.

    Per-table chunks plus optional catalog + relationship overview chunks.
    """
    profiles = table_profiles or {}
    chunks: list[tuple[str, dict]] = []
    for table in tables:
        content = chunk_table(
            table,
            warehouse_header=warehouse_header,
            table_profile=profiles.get(table.table_name.lower()),
        )
        metadata: dict[str, Any] = {
            "chunk_kind": CHUNK_KIND_TABLE,
            "schema": table.schema_name,
            "table": table.table_name,
            "qualified_name": table.qualified_name,
            "foreign_keys": [
                {
                    "column": fk.column,
                    "referenced_table": fk.referenced_table,
                    "referenced_column": fk.referenced_column,
                }
                for fk in table.foreign_keys
            ],
            **_engine_fields(engine_meta),
        }
        profile = profiles.get(table.table_name.lower())
        if profile and profile.get("row_count") is not None:
            metadata["row_count"] = profile.get("row_count")
        chunks.append((content, metadata))

    if include_overview_chunks and tables:
        chunks.append(
            build_catalog_overview_chunk(
                tables,
                warehouse_header=warehouse_header,
                engine_meta=engine_meta,
                table_profiles=profiles,
            )
        )
        chunks.append(
            build_relationship_graph_chunk(
                tables,
                warehouse_header=warehouse_header,
                engine_meta=engine_meta,
            )
        )
    return chunks
