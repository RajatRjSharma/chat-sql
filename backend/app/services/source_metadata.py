"""Warehouse / AI provenance metadata for chat + embedding context."""

from __future__ import annotations

from typing import Any

from app.config import settings
from app.models import DataSource

# Catalog of engines we may support. Connect API is postgres-only today;
# metadata stays honest so the LLM (and future dialects) get clear guidance.
_ENGINE_CATALOG: dict[str, dict[str, Any]] = {
    "postgres": {
        "engine": "PostgreSQL",
        "vendor": "PostgreSQL Global Development Group",
        "sql_dialect": "postgres",
        "supports_schemas": True,
        "identifier_quoting": "double_quote",
        "notes": "Use schema.table qualification when schema is set. FILTER / CTEs OK.",
    },
    "mysql": {
        "engine": "MySQL",
        "vendor": "Oracle Corporation",
        "sql_dialect": "mysql",
        "supports_schemas": False,
        "identifier_quoting": "backtick",
        "notes": "Use database.table. Prefer backticks for reserved identifiers.",
    },
    "mariadb": {
        "engine": "MariaDB",
        "vendor": "MariaDB Foundation",
        "sql_dialect": "mysql",
        "supports_schemas": False,
        "identifier_quoting": "backtick",
        "notes": "MySQL-compatible dialect. Prefer backticks for reserved identifiers.",
    },
    "sqlite": {
        "engine": "SQLite",
        "vendor": "SQLite Consortium",
        "sql_dialect": "sqlite",
        "supports_schemas": False,
        "identifier_quoting": "double_quote",
        "notes": "Limited concurrent writes; keep SELECTs simple.",
    },
    "mssql": {
        "engine": "Microsoft SQL Server",
        "vendor": "Microsoft",
        "sql_dialect": "tsql",
        "supports_schemas": True,
        "identifier_quoting": "bracket",
        "notes": "Use [schema].[table]. Prefer TOP / OFFSET-FETCH over LIMIT.",
    },
    "bigquery": {
        "engine": "Google BigQuery",
        "vendor": "Google",
        "sql_dialect": "bigquery",
        "supports_schemas": True,
        "identifier_quoting": "backtick",
        "notes": "Use project.dataset.table when fully qualified.",
    },
}


def resolve_engine_profile(db_type: str) -> dict[str, Any]:
    key = (db_type or "postgres").strip().lower()
    profile = _ENGINE_CATALOG.get(key)
    if profile:
        return {"db_type": key, **profile}
    return {
        "db_type": key,
        "engine": key,
        "vendor": "unknown",
        "sql_dialect": key,
        "supports_schemas": True,
        "identifier_quoting": "double_quote",
        "notes": "Generate standard SQL SELECT for this engine.",
    }


def build_source_metadata(
    data_source: DataSource,
    *,
    tables_in_context: list[str] | None = None,
    chunks_retrieved: int = 0,
    context_mode: str = "rag",
) -> dict[str, Any]:
    """
    Provenance for one answer: warehouse identity + dialect + AI models used.

    Safe for API responses (no passwords / connection URLs).
    """
    profile = resolve_engine_profile(data_source.db_type)
    tables = sorted({t for t in (tables_in_context or []) if t})

    return {
        "source_name": data_source.name,
        "data_source_id": str(data_source.id),
        "db_type": profile["db_type"],
        "engine": profile["engine"],
        "vendor": profile["vendor"],
        "sql_dialect": profile["sql_dialect"],
        "supports_schemas": bool(profile["supports_schemas"]),
        "identifier_quoting": profile["identifier_quoting"],
        "dialect_notes": profile["notes"],
        "host": data_source.host,
        "port": data_source.port,
        "database": data_source.database,
        "schema_name": data_source.schema_name,
        "is_readonly": bool(data_source.is_readonly),
        "access_mode": "read_only_select",
        "tables_in_context": tables,
        "chunks_retrieved": int(chunks_retrieved),
        "context_mode": context_mode,  # rag | introspection_fallback | empty
        "embedding_model": settings.embedding_model,
        "embedding_dimensions": settings.embedding_dimensions,
        "llm_model": settings.llm_model,
        "llm_model_fallback": settings.llm_model_fallback,
        "rag_top_k": settings.rag_top_k,
    }


def format_metadata_for_llm(metadata: dict[str, Any] | None) -> str:
    """Compact block injected into SQL / summary prompts."""
    if not metadata:
        return "Warehouse dialect: PostgreSQL (assume postgres SQL)."

    lines = [
        f"Engine: {metadata.get('engine')} ({metadata.get('db_type')})",
        f"Vendor: {metadata.get('vendor')}",
        f"SQL dialect for generation: {metadata.get('sql_dialect')}",
        f"Database: {metadata.get('database')}",
        f"Schema: {metadata.get('schema_name') or '(connection default)'}",
        f"Host: {metadata.get('host')}:{metadata.get('port')}",
        f"Access: {'read-only' if metadata.get('is_readonly') else 'read-write'} "
        f"({metadata.get('access_mode')})",
        f"Quoting style: {metadata.get('identifier_quoting')}",
        f"Dialect notes: {metadata.get('dialect_notes')}",
    ]
    tables = metadata.get("tables_in_context") or []
    if tables:
        lines.append(f"Tables in retrieved schema context: {', '.join(tables)}")
    lines.append(
        f"Embedding model used for schema RAG: {metadata.get('embedding_model')} "
        f"({metadata.get('embedding_dimensions')} dims)"
    )
    return "\n".join(lines)
