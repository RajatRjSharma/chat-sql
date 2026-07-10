"""Project DB table schema resolution for ORM models and migrations."""

from __future__ import annotations

from functools import lru_cache

from app.config import get_settings
from app.core.schema import resolve_optional_schema


@lru_cache
def project_table_schema() -> str | None:
    """Configured schema, or None to use the PostgreSQL connection default."""
    return resolve_optional_schema(get_settings().app_db_schema)


def project_table_args() -> dict:
    schema = project_table_schema()
    return {"schema": schema} if schema else {}


def fk_table(table_column: str) -> str:
    schema = project_table_schema()
    return f"{schema}.{table_column}" if schema else table_column
