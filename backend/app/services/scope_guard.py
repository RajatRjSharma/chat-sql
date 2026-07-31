"""Warehouse-scope guard — refuse questions the schema cannot answer."""

from __future__ import annotations

import re
from typing import Literal

from app.providers.ai import AIClient, get_ai_client

ScopeDecision = Literal["answerable", "out_of_scope"]

OUT_OF_SCOPE_MESSAGE = (
    "That question isn't something I can answer from your connected warehouse. "
    "I only analyze tables and metrics in this data source — ask about fields "
    "and measures that exist in your schema (for example sales, customers, or orders)."
)

EMPTY_RESULT_MESSAGE = (
    "I queried your connected warehouse, but that question returned no matching rows. "
    "Try a different metric, filter, or time range — I can only report data that "
    "actually exists in this warehouse."
)

_UNANSWERABLE_RE = re.compile(
    r"^\s*(?:```\w*\s*)?UNANSWERABLE\b",
    re.IGNORECASE,
)

_SYSTEM = """\
You gate questions for a read-only warehouse analytics assistant.

You receive SCHEMA CONTEXT (tables/columns available in the user's database) and a USER QUESTION.
Decide whether the question can be answered ONLY from that warehouse schema.

Reply with exactly one token on the first line:
ANSWERABLE
or
OUT_OF_SCOPE

Rules:
- ANSWERABLE — the question asks for analytics/facts that could plausibly come from the listed tables/columns (counts, sums, filters, trends, joins within the schema). Follow-ups about prior warehouse answers are ANSWERABLE when they stay on that data.
- OUT_OF_SCOPE — general knowledge, trivia, world facts, celebrities, buildings, weather, sports scores, coding help, or anything the schema clearly cannot support.
- When unsure but the question is clearly not about the warehouse domain in the schema, choose OUT_OF_SCOPE.
- Do not explain. Do not output SQL.
"""


class ScopeGuard:
    """Classify question relevance and detect SQL-model refuse markers."""

    @staticmethod
    def assess(
        *,
        question: str,
        schema_context: str,
        client: AIClient | None = None,
    ) -> ScopeDecision:
        ai = client or get_ai_client()
        context = (schema_context or "").strip() or "No schema context available."
        messages = [
            {"role": "system", "content": _SYSTEM},
            {
                "role": "user",
                "content": (
                    "SCHEMA CONTEXT:\n"
                    f"{context}\n\n"
                    f"USER QUESTION:\n{question.strip()}"
                ),
            },
        ]
        raw = ai.complete(messages, temperature=0.0, max_tokens=16)
        return ScopeGuard.parse_decision(raw)

    @staticmethod
    def parse_decision(raw: str) -> ScopeDecision:
        text = (raw or "").strip().upper()
        first = text.splitlines()[0] if text else ""
        # Prefer explicit OUT_OF_SCOPE; default to answerable so we don't
        # block legitimate analytics if the model is noisy.
        if "OUT_OF_SCOPE" in first or first.startswith("OUT"):
            return "out_of_scope"
        if "ANSWERABLE" in first:
            return "answerable"
        if "OUT_OF_SCOPE" in text:
            return "out_of_scope"
        return "answerable"

    @staticmethod
    def is_unanswerable_marker(sql_or_text: str | None) -> bool:
        if not sql_or_text:
            return False
        return bool(_UNANSWERABLE_RE.match(sql_or_text.strip()))
