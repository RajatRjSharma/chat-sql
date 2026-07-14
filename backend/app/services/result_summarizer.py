"""Summarize query results for the end user."""

from __future__ import annotations

import json
from typing import Any

from app.providers.ai import AIClient, get_ai_client
from app.services.source_metadata import format_metadata_for_llm

_SYSTEM = """\
You are a concise business analyst. Summarize SQL query results in 2-4 clear sentences.
Mention key numbers. Do not invent data not present in the rows.
When warehouse metadata is provided, you may briefly ground the answer
(e.g. "in the PostgreSQL sales schema") without dumping connection details.
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
                    "Summarize these analytics results for an executive:\n"
                    f"{json.dumps(payload, default=str)}"
                ),
            },
        ]
        return ai.complete(messages, temperature=0.2, max_tokens=512)
