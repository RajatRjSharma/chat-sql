"""Generate warehouse SQL from a natural-language question."""

from __future__ import annotations

from typing import Any

from app.providers.ai import AIClient, get_ai_client
from app.services.source_metadata import format_metadata_for_llm
from app.services.sql_validator import extract_sql

_SYSTEM_PROMPT = """\
You are a SQL expert generating analytics queries for a read-only BI assistant
that answers ONLY from the user's connected warehouse schema.

Rules:
1. Output ONLY a single SELECT (or UNION of SELECTs). Prefer a markdown ```sql fence.
2. Never use INSERT, UPDATE, DELETE, DROP, ALTER, CREATE, TRUNCATE, GRANT, or multiple statements.
3. Obey the warehouse metadata block — dialect, quoting, and schema rules are authoritative.
4. Prefer fully-qualified table names (schema.table) when the engine supports
   schemas and a schema is set.
5. Use only tables/columns present in the schema context — copy names exactly
   (e.g. `orders`, never invent `order`).
6. Prefer aggregations and clear column aliases for charting (schema-agnostic):
   - 1 dimension + measure → bar/line/pie.
   - 2 dimensions + measure → grouped/stacked/multi-line (or a compact grid).
   - 2 measures for correlation → two numeric columns (optional id/label).
   Keep result sets compact: prefer GROUP BY aggregates; avoid dumping millions of
   raw rows — use LIMIT only when the user explicitly asks for samples/raw rows.
7. String literals must use the dialect's string quotes (PostgreSQL: single quotes).
8. FILTER clauses must be valid for the target dialect when used:
   COUNT(*) FILTER (WHERE status = 'completed') on PostgreSQL —
   never glue FILTER fragments to casts.
9. For broad questions (“highlights”, “overview”, “all tables”, “summary of db”), return ONE
   readable summary query (row counts by table via UNION ALL). When the schema context includes
   a “Complete indexed table inventory”, include EVERY listed table — never a subset.
   Keep it short — avoid nested half-finished expressions.
10. If previous SQL failed validation, fix the error described by the user.
11. Map common BI vocabulary to whatever measure columns exist in this schema
    (e.g. revenue/sales/GMV/volume → amount, total_amount, qty, value, …).
12. If the question cannot be answered from the schema context (general knowledge,
    trivia, unrelated domains), output exactly: UNANSWERABLE
    Do not invent tables, columns, or placeholder SELECTs to force an answer.

Join & measure discipline (industry Text2SQL):
13. Prefer foreign-key / relationship edges documented in the schema context over
    string equality between unrelated columns. Never join a short code/key column
    to a free-text label column of different semantics (e.g. code `N` to name
    `North`) — use the FK path through bridge/dim tables, or match on the same
    semantic field (name-to-name or id-to-id).
14. For “revenue”, “sales”, “GMV”, or similar business totals, prefer the primary
    fact-table measure on the transactional/events table when present (amount,
    total, value, …). Use invoice/payment/billing measures only when the user
    asks about invoices, AR, billing, or payments.
15. For “compare A vs B”, “correlation”, or “X versus Y” across entities, return
    one row per entity with two numeric columns — not a single row of grand
    totals. Cap with LIMIT only if the result would be huge.
16. For “matrix”, “heatmap”, or dense breakdowns across two dimensions, prefer the
    higher-cardinality categorical dims available via FK when multiple paths
    exist, and GROUP BY both dims.
17. On follow-ups (“break that down…”, “only for the top…”), preserve the same join
    paths and grain as the prior successful SQL unless the user explicitly changes
    the metric or dimensions.
"""

_EMPTY_RESULT_HINT = (
    "Previous SQL executed successfully but returned ZERO rows. "
    "That usually means a bad join predicate (code joined to a free-text label), "
    "an over-strict filter, or the wrong measure table. "
    "Rewrite using FK paths from the schema context; do not invent equality "
    "between unrelated code and name columns. Prefer the primary fact measure "
    "for revenue/sales asks."
)

# Public alias for chat-service empty-result retries.
EMPTY_RESULT_SQL_HINT = _EMPTY_RESULT_HINT


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
        prior_sql = (source_metadata or {}).get("prior_successful_sql")

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
        if isinstance(prior_sql, str) and prior_sql.strip():
            user_parts.extend(
                [
                    "",
                    "This question looks like a follow-up. Prior successful SQL "
                    "(preserve join paths and grain unless the user changes them):",
                    prior_sql.strip(),
                ]
            )
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
        messages.extend(SqlGenerator._history_for_prompt(history))
        messages.append({"role": "user", "content": "\n".join(user_parts)})

        raw = ai.complete(messages, temperature=0.0, max_tokens=2048)
        return extract_sql(raw)

    @staticmethod
    def _history_for_prompt(
        history: list[dict[str, str]] | None,
        *,
        limit: int = 5,
    ) -> list[dict[str, str]]:
        """
        Last *limit* chat turns for the SQL prompt.

        Always use a slice (history[-n:]), never history[-n] — indexing a short
        list raises IndexError (production incident on turn 2+).
        """
        if not history or limit <= 0:
            return []
        out: list[dict[str, str]] = []
        for item in history[-limit:]:
            if not isinstance(item, dict):
                continue
            role = item.get("role", "user")
            content = item.get("content", "")
            if role in {"user", "assistant"} and isinstance(content, str) and content.strip():
                out.append({"role": role, "content": content})
        return out
