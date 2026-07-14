"""Generate warehouse SQL from a natural-language question."""

from __future__ import annotations

from typing import Any

from app.providers.ai import AIClient, get_ai_client
from app.services.source_metadata import format_metadata_for_llm
from app.services.sql_validator import extract_sql

_SYSTEM_PROMPT = """\
You are a SQL expert generating analytics queries for a read-only BI assistant.

Rules:
1. Output ONLY a single SELECT (or UNION of SELECTs). Prefer a markdown ```sql fence.
2. Never use INSERT, UPDATE, DELETE, DROP, ALTER, CREATE, TRUNCATE, GRANT, or multiple statements.
3. Obey the warehouse metadata block — dialect, quoting, and schema rules are authoritative.
4. Prefer fully-qualified table names (schema.table) when the engine supports schemas and a schema is set.
5. Use only tables/columns present in the schema context — copy names exactly
   (e.g. `orders`, never invent `order`).
6. Prefer aggregations and clear column aliases for charting.
7. String literals must use the dialect's string quotes (PostgreSQL: single quotes).
8. FILTER clauses must be valid for the target dialect when used:
   COUNT(*) FILTER (WHERE status = 'completed') on PostgreSQL —
   never glue FILTER fragments to casts.
9. For broad questions (“highlights”, “overview”, “all tables”), return ONE readable
   summary query (row counts by table via UNION ALL, or top metrics from the main fact table).
   Keep it short — avoid nested half-finished expressions.
10. If previous SQL failed validation, fix the error described by the user.
"""


class SqlGenerator:
    """NL → SQL using schema context, warehouse metadata, and optional retry feedback."""

    @staticmethod
    def generate(
        *,
        question: str,
        schema_context: str,
        schema_name: str | None = None,
        history: list[dict[str, str]] | None = None,
        previous_sql: str | None = None,
        previous_error: str | None = None,
        source_metadata: dict[str, Any] | None = None,
        client: AIClient | None = None,
    ) -> str:
        ai = client or get_ai_client()
        dialect = (source_metadata or {}).get("sql_dialect") or "postgres"
        schema_hint = schema_name or "the connection default schema"
        engine = (source_metadata or {}).get("engine") or "PostgreSQL"

        user_parts = [
            "Warehouse metadata (authoritative for dialect + identifiers):",
            format_metadata_for_llm(source_metadata),
            "",
            f"Generate {engine} SQL (sqlglot dialect `{dialect}`).",
            f"Target schema: {schema_hint}",
            "Schema context:",
            schema_context,
            "",
            f"Question: {question}",
        ]
        if previous_sql and previous_error:
            user_parts.extend(
                [
                    "",
                    "Previous SQL failed validation/execution:",
                    previous_sql,
                    f"Error: {previous_error}",
                    "Generate a corrected SELECT query for this dialect.",
                ]
            )

        messages: list[dict[str, str]] = [{"role": "system", "content": _SYSTEM_PROMPT}]
        if history:
            for item in history[-5:]:
                role = item.get("role", "user")
                content = item.get("content", "")
                if role in {"user", "assistant"} and content:
                    messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": "\n".join(user_parts)})

        raw = ai.complete(messages, temperature=0.0, max_tokens=1024)
        return extract_sql(raw)
