"""Summarize query results for the end user."""

from __future__ import annotations

import json
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
"""


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
