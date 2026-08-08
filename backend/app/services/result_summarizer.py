"""Summarize query results for the end user."""

from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation
from typing import Any

from app.providers.ai import AIClient, get_ai_client
from app.services.scope_guard import EMPTY_RESULT_MESSAGE
from app.services.source_metadata import format_metadata_for_llm

_SYSTEM = """\
You are a concise business analyst for a warehouse BI assistant.

Rules:
1. Summarize ONLY using numbers and labels present in the provided rows/columns.
2. Never use outside world knowledge. Never invent facts, heights, scores, or metrics
   that are not in the result rows.
3. Do not claim the warehouse "confirmed" anything that is not in the rows.
4. 2–4 clear sentences. Mention key numbers from the data.
5. You may briefly name the warehouse engine/schema from metadata (e.g. "in the
   <schema> schema") without dumping connection details.
6. If row_count is 0, say no matching rows were returned — do not guess an answer.
7. rows_preview may be only a subset. Use full_result_numeric_extrema for any
   minimum/maximum/range claim; it is computed over ALL returned rows.
8. If rows contain multiple categorical dimensions, describe an extremum as the
   highest/lowest COMBINATION (cell). Do not call it a dimension's overall total
   unless the SQL result is grouped only at that dimension's level.
9. Double-check number formatting. Never transpose digits or produce malformed
   currency/grouping (for example "$1,6403").
"""


def _number(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return number if number.is_finite() else None


def _numeric_extrema(
    rows: list[dict[str, Any]],
    columns: list[str],
) -> dict[str, dict[str, dict[str, Any]]]:
    """Min/max row snapshots for every fully numeric result column."""
    extrema: dict[str, dict[str, dict[str, Any]]] = {}
    for column in columns:
        values: list[tuple[Decimal, dict[str, Any]]] = []
        numeric = True
        for row in rows:
            raw = row.get(column)
            if raw is None or raw == "":
                continue
            parsed = _number(raw)
            if parsed is None:
                numeric = False
                break
            values.append((parsed, row))
        if not numeric or not values:
            continue
        minimum = min(values, key=lambda item: item[0])
        maximum = max(values, key=lambda item: item[0])
        extrema[column] = {
            "min": {"value": minimum[1].get(column), "row": minimum[1]},
            "max": {"value": maximum[1].get(column), "row": maximum[1]},
        }
    return extrema


class ResultSummarizer:
    @staticmethod
    def summarize(
        *,
        question: str,
        sql: str,
        columns: list[str],
        rows: list[dict[str, Any]],
        source_metadata: dict[str, Any] | None = None,
        client: AIClient | None = None,
    ) -> str:
        if not rows:
            return EMPTY_RESULT_MESSAGE

        ai = client or get_ai_client()
        preview = rows[:20]
        payload = {
            "question": question,
            "sql": sql,
            "columns": columns,
            "row_count": len(rows),
            "rows_preview": preview,
            "full_result_numeric_extrema": _numeric_extrema(rows, columns),
            "warehouse": {
                "engine": (source_metadata or {}).get("engine"),
                "database": (source_metadata or {}).get("database"),
                "schema_name": (source_metadata or {}).get("schema_name"),
                "tables_in_context": (source_metadata or {}).get("tables_in_context"),
            },
        }
        messages = [
            {"role": "system", "content": _SYSTEM},
            {
                "role": "user",
                "content": (
                    "Warehouse context:\n"
                    f"{format_metadata_for_llm(source_metadata)}\n\n"
                    "Summarize these analytics results for an executive. "
                    "Use only the JSON rows below:\n"
                    f"{json.dumps(payload, default=str)}"
                ),
            },
        ]
        return ai.complete(messages, temperature=0.0, max_tokens=512)
