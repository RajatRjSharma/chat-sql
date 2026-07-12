"""Generate warehouse SQL from a natural-language question."""

from __future__ import annotations

from app.providers.ai import AIClient, get_ai_client
from app.services.sql_validator import extract_sql

_SYSTEM_PROMPT = """\
You are a PostgreSQL expert generating analytics SQL for a read-only BI assistant.

Rules:
1. Output ONLY a single SELECT (or UNION of SELECTs). No markdown unless wrapping SQL in a fence.
2. Never use INSERT, UPDATE, DELETE, DROP, ALTER, CREATE, TRUNCATE, GRANT, or multiple statements.
3. Prefer fully-qualified table names (schema.table) when a schema is provided.
4. Use only tables/columns present in the schema context.
5. Prefer aggregations and clear column aliases for charting.
6. If previous SQL failed validation, fix the error described by the user.
"""


class SqlGenerator:
    """NL → SQL using schema context and optional retry feedback."""

    @staticmethod
    def generate(
        *,
        question: str,
        schema_context: str,
        schema_name: str | None = None,
        history: list[dict[str, str]] | None = None,
        previous_sql: str | None = None,
        previous_error: str | None = None,
        client: AIClient | None = None,
    ) -> str:
        ai = client or get_ai_client()
        schema_hint = schema_name or "the connection default schema"

        user_parts = [
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
                    "Generate a corrected SELECT query.",
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
