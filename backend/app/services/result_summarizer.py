"""Summarize query results for the end user via OpenRouter."""

from __future__ import annotations

import json
from typing import Any

from app.providers.openrouter import OpenRouterClient, get_openrouter_client

_SYSTEM = """\
You are a concise business analyst. Summarize SQL query results in 2-4 clear sentences.
Mention key numbers. Do not invent data not present in the rows.
"""


class ResultSummarizer:
    @staticmethod
    def summarize(
        *,
        question: str,
        sql: str,
        columns: list[str],
        rows: list[dict[str, Any]],
        client: OpenRouterClient | None = None,
    ) -> str:
        openrouter = client or get_openrouter_client()
        preview = rows[:20]
        payload = {
            "question": question,
            "sql": sql,
            "columns": columns,
            "row_count": len(rows),
            "rows_preview": preview,
        }
        messages = [
            {"role": "system", "content": _SYSTEM},
            {
                "role": "user",
                "content": (
                    "Summarize these analytics results for an executive:\n"
                    f"{json.dumps(payload, default=str)}"
                ),
            },
        ]
        return openrouter.complete(messages, temperature=0.2, max_tokens=512)
