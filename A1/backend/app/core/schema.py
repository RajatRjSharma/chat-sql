"""Validate and resolve PostgreSQL schema identifiers."""

from __future__ import annotations

import re

_IDENT_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")

# PostgreSQL uses `public` on the default search_path when no schema is set.
POSTGRES_DEFAULT_SCHEMA = "public"


def validate_schema_identifier(value: str) -> str:
    if not _IDENT_RE.match(value):
        raise ValueError(f"Invalid schema name: {value!r}")
    return value


def resolve_optional_schema(value: str | None) -> str | None:
    """Return None when value is empty — use the database connection default."""
    if value is None:
        return None
    stripped = value.strip()
    return stripped if stripped else None


def validate_optional_schema(value: str | None) -> str | None:
    """Validate schema only when the caller provided one."""
    resolved = resolve_optional_schema(value)
    return validate_schema_identifier(resolved) if resolved else None


def qualify_table(schema: str | None, table: str) -> str:
    """Build a table reference; omit schema when using the connection default."""
    if schema:
        validate_schema_identifier(schema)
        return f"{schema}.{table}"
    return table


def read_connection_schema(cursor, schema: str | None) -> str:
    """Resolve the active schema for a live PostgreSQL connection."""
    if schema:
        return schema
    cursor.execute("SELECT current_schema()")
    return cursor.fetchone()[0]
