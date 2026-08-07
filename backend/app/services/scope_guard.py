"""Warehouse-scope guard — layered relevance gate for Text2SQL chat.

Industry-style pipeline:
1. Deterministic schema overlap → answerable (high recall on short/typo asks)
2. Ultra-vague with no schema signal → ask for clarification (not a hard refuse)
3. LLM classifier only for remaining cases (unsure → answerable)
4. SQL generator may still emit UNANSWERABLE as defense in depth
"""

from __future__ import annotations

import re
from typing import Literal

from app.providers.ai import AIClient, get_ai_client
from app.services.follow_up import looks_like_follow_up
from app.services.nl_normalize import nouns_match

ScopeDecision = Literal["answerable", "out_of_scope", "needs_clarification"]

_SCOPE_DECISION_RE = re.compile(
    r"\b(ANSWERABLE|OUT_OF_SCOPE|NEEDS_CLARIFICATION)\b",
    re.IGNORECASE,
)

OUT_OF_SCOPE_MESSAGE = (
    "That question isn't something I can answer from your connected warehouse. "
    "I only analyze tables and metrics in this data source — ask about fields "
    "and measures that exist in your schema."
)

PLANNING_FAILED_MESSAGE = (
    "I couldn't build a reliable query for that from the tables currently in context. "
    "Try naming the metric and dimensions explicitly (for example the measure, the "
    "grouping column, and any filter) and I'll query your warehouse again."
)

EMPTY_RESULT_MESSAGE = (
    "I queried your connected warehouse, but that question returned no matching rows. "
    "This often means a join or filter did not match (for example joining a code "
    "column to a free-text label). Try rephrasing with clearer dimensions, a different "
    "metric, or a broader time range — I can only report data that exists here."
)

_UNANSWERABLE_RE = re.compile(
    r"^\s*(?:```\w*\s*)?UNANSWERABLE\b",
    re.IGNORECASE,
)
_WORD_RE = re.compile(r"[a-z0-9_]+", re.IGNORECASE)
_TABLE_LINE_RE = re.compile(r"^Table:\s*(?P<name>\S+)", re.MULTILINE | re.IGNORECASE)
_COLUMN_LINE_RE = re.compile(r"^\s*-\s*(?P<name>[A-Za-z_][\w]*)\s*:", re.MULTILINE)

# Filler words ignored for overlap / vagueness checks.
_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "the",
        "is",
        "are",
        "was",
        "were",
        "what",
        "whats",
        "what's",
        "which",
        "who",
        "whom",
        "whose",
        "where",
        "when",
        "why",
        "how",
        "do",
        "does",
        "did",
        "can",
        "could",
        "would",
        "should",
        "me",
        "my",
        "i",
        "we",
        "you",
        "your",
        "please",
        "just",
        "give",
        "show",
        "tell",
        "get",
        "quick",
        "about",
        "of",
        "for",
        "to",
        "in",
        "on",
        "at",
        "from",
        "with",
        "and",
        "or",
        "this",
        "that",
        "these",
        "those",
        "some",
        "any",
        "all",
        "full",
        "info",
        "information",
        "detail",
        "details",
        "describe",
        "explanation",
    }
)

# Alone (or nearly alone) these mean "clarify which entity", not refuse.
_VAGUE_ONLY = frozenset(
    {
        "summary",
        "summarize",
        "summarise",
        "overview",
        "stats",
        "statistics",
        "report",
        "insights",
        "insight",
        "hello",
        "hi",
        "hey",
        "help",
        "thanks",
        "thank",
    }
)

# Unambiguous warehouse / aggregation cues. Strong enough to skip the scope
# classifier entirely, so keep general-English words out of this set.
_WAREHOUSE_INTENT_HINTS = frozenset(
    {
        "count",
        "counts",
        "sum",
        "total",
        "totals",
        "avg",
        "average",
        "mean",
        "amount",
        "amounts",
        "range",
        "ranging",
        "min",
        "max",
        "top",
        "bottom",
        "trend",
        "trends",
        "breakdown",
        "compare",
        "group",
        "grouped",
        "aggregate",
        "aggregates",
        "distribution",
        "tables",
        "schema",
        "database",
        "db",
        "warehouse",
        "metric",
        "metrics",
        "measure",
        "measures",
        "rows",
        "columns",
        "join",
        "joins",
        # Time / grain refinements (common follow-up language).
        "month",
        "months",
        "monthly",
        "year",
        "years",
        "yearly",
        "quarter",
        "quarters",
        "week",
        "weeks",
        "weekly",
        "day",
        "days",
        "daily",
        "date",
        "dates",
    }
)

# Softer BI vocabulary that also occurs in ordinary English ("cost of a Tesla",
# "Messi vs Ronaldo"). Good enough to justify a deeper-linking retry after a
# failed turn, but not to bypass the scope classifier.
_SOFT_ANALYTICS_HINTS = frozenset(
    {
        "median",
        "percentile",
        "percentiles",
        "percentage",
        "percent",
        "share",
        "rank",
        "ranking",
        "versus",
        "vs",
        "yoy",
        "mom",
        "correlation",
        "correlate",
        "heatmap",
        "plot",
        "chart",
        "graph",
        "filter",
        "filters",
        "kpi",
        "kpis",
        "highlights",
        "revenue",
        "sales",
        "gmv",
        "bookings",
        "margin",
        "profit",
        "cost",
    }
)

_ANALYTICS_HINTS = _WAREHOUSE_INTENT_HINTS | _SOFT_ANALYTICS_HINTS

_SYSTEM = """\
You gate questions for a read-only warehouse analytics assistant (Text2SQL / BI copilot).

You receive SCHEMA CONTEXT (tables/columns in the user's database) and a USER QUESTION.
Decide whether the question belongs to this warehouse.

Reply with exactly one token on the first line:
ANSWERABLE
or
OUT_OF_SCOPE
or
NEEDS_CLARIFICATION

Rules (follow in order):
1. ANSWERABLE — the question could plausibly be answered with SELECT analytics over the listed
   schema (counts, sums, filters, trends, joins, table summaries, schema overviews).
   Short, typo-prone, or shorthand asks that still refer to warehouse entities
   present in SCHEMA CONTEXT (table/column names or clear analytics intent) are ANSWERABLE.
   Follow-ups about prior warehouse answers stay ANSWERABLE when they stay on that data.
2. NEEDS_CLARIFICATION — the user asks for a summary/overview with no table, metric, or
   domain cue at all (e.g. only "summary" or "help"). Prefer this over OUT_OF_SCOPE.
3. OUT_OF_SCOPE — ONLY when the question clearly needs knowledge outside the warehouse:
   general trivia, world facts, celebrities, buildings, weather, sports scores, coding help,
   or topics the schema cannot support at all.
4. When unsure between ANSWERABLE and OUT_OF_SCOPE, choose ANSWERABLE.
5. Do not explain. Do not output SQL.
"""


def clarification_message(
    *,
    schema_context: str = "",
    allowed_tables: list[str] | None = None,
) -> str:
    """Ask the user to narrow an ambiguous ask; list known tables when available."""
    names = _table_display_names(schema_context, allowed_tables)
    if names:
        listed = ", ".join(names[:8])
        more = "…" if len(names) > 8 else ""
        return (
            "I can summarize metrics from your connected warehouse, but that request is "
            f"too broad. Try naming a table or measure — for example: {listed}{more}."
        )
    return (
        "I can summarize metrics from your connected warehouse, but that request is "
        "too broad. Try naming a table or measure from your schema."
    )


class ScopeGuard:
    """Layered relevance gate + SQL-model refuse marker detection."""

    @staticmethod
    def assess(
        *,
        question: str,
        schema_context: str,
        allowed_tables: list[str] | None = None,
        history: list[dict[str, str]] | None = None,
        client: AIClient | None = None,
    ) -> ScopeDecision:
        q = (question or "").strip()
        if not q:
            return "needs_clarification"

        schema_ids = ScopeGuard.extract_schema_identifiers(schema_context, allowed_tables)

        # 0) Conversational refinements of a prior BI turn stay in the SQL path.
        # Without this, "Break that down by month" has no schema tokens and the
        # scope LLM often wrongly returns OUT_OF_SCOPE.
        if looks_like_follow_up(q, history, schema_tokens=schema_ids):
            return "answerable"

        # 1) Deterministic: schema / analytics signal → stay in the SQL path.
        if _has_overlap(q, schema_ids):
            return "answerable"
        if ScopeGuard.has_warehouse_intent(q):
            return "answerable"

        # 2) Ultra-vague with no schema cue → clarify (do not hard-refuse).
        if ScopeGuard.is_vague_only(q):
            return "needs_clarification"

        # 3) LLM only when still ambiguous.
        ai = client or get_ai_client()
        context = (schema_context or "").strip() or "No schema context available."
        messages = [
            {"role": "system", "content": _SYSTEM},
            {
                "role": "user",
                "content": (
                    "SCHEMA CONTEXT:\n"
                    f"{context}\n\n"
                    f"USER QUESTION:\n{q}"
                ),
            },
        ]
        raw = ai.complete(messages, temperature=0.0, max_tokens=16)
        return ScopeGuard.parse_decision(raw)

    @staticmethod
    def parse_decision(raw: str) -> ScopeDecision:
        text = (raw or "").strip()
        if not text:
            return "answerable"

        token_map = {
            "ANSWERABLE": "answerable",
            "OUT_OF_SCOPE": "out_of_scope",
            "NEEDS_CLARIFICATION": "needs_clarification",
        }
        # Whole-label match on the first line so "OUTPUT" / "OUTLIER" / "NEED MORE"
        # are not mistaken for a decision, while "Out of scope." still resolves.
        first = re.sub(r"[^A-Z]+", "_", text.splitlines()[0].upper()).strip("_")
        for label, decision in token_map.items():
            if first == label or first.startswith(f"{label}_"):
                return decision  # type: ignore[return-value]

        match = _SCOPE_DECISION_RE.search(text)
        if match:
            return token_map[match.group(1).upper()]  # type: ignore[return-value]
        return "answerable"

    @staticmethod
    def is_unanswerable_marker(sql_or_text: str | None) -> bool:
        if not sql_or_text:
            return False
        return bool(_UNANSWERABLE_RE.match(sql_or_text.strip()))

    @staticmethod
    def extract_schema_identifiers(
        schema_context: str,
        allowed_tables: list[str] | None = None,
    ) -> set[str]:
        ids: set[str] = set()
        for table in allowed_tables or []:
            ids.update(_identifier_parts(table))
        for match in _TABLE_LINE_RE.finditer(schema_context or ""):
            ids.update(_identifier_parts(match.group("name")))
        for match in _COLUMN_LINE_RE.finditer(schema_context or ""):
            ids.add(match.group("name").lower())
        return {item for item in ids if len(item) >= 2}

    @staticmethod
    def has_schema_overlap(
        question: str,
        schema_context: str,
        allowed_tables: list[str] | None = None,
    ) -> bool:
        schema_ids = ScopeGuard.extract_schema_identifiers(schema_context, allowed_tables)
        return _has_overlap(question, schema_ids)

    @staticmethod
    def has_analytics_intent(question: str) -> bool:
        """Broad BI vocabulary — drives retry decisions after a failed turn."""
        return ScopeGuard._matches_hints(question, _ANALYTICS_HINTS)

    @staticmethod
    def has_warehouse_intent(question: str) -> bool:
        """Narrow, unambiguous cues — safe to answer without the scope LLM."""
        return ScopeGuard._matches_hints(question, _WAREHOUSE_INTENT_HINTS)

    @staticmethod
    def _matches_hints(question: str, hints: frozenset[str]) -> bool:
        q = (question or "").strip().lower()
        # Multi-word cues that tokenize into stop-ish fragments ("break" + "down").
        if "break down" in q or "break that down" in q or "break it down" in q:
            return True
        tokens = _content_tokens(question)
        if not tokens:
            return False
        # "summary of full db", "table info", "orders count", etc.
        return any(token in hints for token in tokens)

    @staticmethod
    def is_vague_only(question: str) -> bool:
        tokens = _content_tokens(question)
        if not tokens:
            return True
        token_set = set(tokens)
        if len(token_set) <= 2 and token_set <= _VAGUE_ONLY:
            return True
        # Single analytics word with no entity is still too broad ("summary").
        if len(token_set) == 1 and next(iter(token_set)) in _VAGUE_ONLY:
            return True
        return False


def _identifier_parts(name: str) -> set[str]:
    cleaned = (name or "").strip().strip("`\"[]")
    if not cleaned:
        return set()
    parts = {cleaned.lower()}
    for piece in re.split(r"[.\s]+", cleaned):
        piece = piece.strip().lower()
        if piece:
            parts.add(piece)
    return parts


def _content_tokens(text: str) -> list[str]:
    tokens = [m.group(0).lower() for m in _WORD_RE.finditer(text or "")]
    return [t for t in tokens if t not in _STOPWORDS and len(t) >= 2]


def _has_overlap(question: str, schema_ids: set[str]) -> bool:
    if not schema_ids:
        return False
    for token in _content_tokens(question):
        for schema_id in schema_ids:
            if _tokens_match(token, schema_id):
                return True
    return False


def _tokens_match(question_token: str, schema_token: str) -> bool:
    q = question_token.lower()
    s = schema_token.lower()
    if nouns_match(q, s):
        return True
    # Prefer meaningful prefix overlap for compound names.
    if len(q) >= 4 and (q in s or s in q):
        return True
    return False


def _table_display_names(
    schema_context: str,
    allowed_tables: list[str] | None,
) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for table in allowed_tables or []:
        short = table.split(".")[-1]
        key = short.lower()
        if key not in seen:
            seen.add(key)
            names.append(short)
    for match in _TABLE_LINE_RE.finditer(schema_context or ""):
        short = match.group("name").split(".")[-1]
        key = short.lower()
        if key not in seen:
            seen.add(key)
            names.append(short)
    return names
