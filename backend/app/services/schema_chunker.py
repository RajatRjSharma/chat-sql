"""Convert introspected tables into RAG text chunks."""

from __future__ import annotations

from app.services.schema_introspection import TableInfo


def chunk_table(table: TableInfo) -> str:
    """Build a single searchable text chunk for one warehouse table."""
    lines = [
        f"Table: {table.qualified_name}",
        "Columns:",
    ]
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

    if table.sample_rows:
        lines.append("Sample rows:")
        for row in table.sample_rows:
            rendered = ", ".join(f"{k}={v!r}" for k, v in row.items())
            lines.append(f"  - {rendered}")

    return "\n".join(lines)


def chunk_tables(tables: list[TableInfo]) -> list[tuple[str, dict]]:
    """
    Return (content, metadata) pairs for embedding storage.
    metadata includes schema, table, and qualified_name.
    """
    chunks: list[tuple[str, dict]] = []
    for table in tables:
        content = chunk_table(table)
        metadata = {
            "schema": table.schema_name,
            "table": table.table_name,
            "qualified_name": table.qualified_name,
        }
        chunks.append((content, metadata))
    return chunks
