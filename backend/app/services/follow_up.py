"""Detect conversational follow-ups so prior SQL is only reused when appropriate."""

from __future__ import annotations

import re

# Table references in prior SQL — used to anchor follow-up retrieval.
_SQL_TABLE_RE = re.compile(
    r"\b(?:from|join)\s+([a-z_][\w]*)\s*\.\s*([a-z_][\w]*)|"
    r"\b(?:from|join)\s+([a-z_][\w]*)\b",
    re.IGNORECASE,
)
_SQL_NOISE_TABLES = frozenset({"select", "lateral", "unnest", "values"})
_WORD_RE = re.compile(r"[a-z0-9_]+", re.IGNORECASE)

# Hard refinement / continuation cues (domain-agnostic BI follow-ups).
_HARD_FOLLOW_UP_RE = re.compile(
    r"\b("
    r"break\s+(?:that|it|this)\s+down|"
    r"break\s+down|"
    r"drill\s+down|"
    r"slice\s+by|"
    r"only\s+for|"
    r"just\s+for|"
    r"for\s+\w+\s+only|"
    r"just\s+the\s+top|"
    r"same\s+(?:but|query|breakdown|thing|analysis)|"
    r"do\s+the\s+same|"
    r"filter\s+(?:to|by|on)|"
    r"narrow\s+(?:to|it)|"
    r"restrict\s+to|"
    r"limit\s+to|"
    r"exclude|"
    r"for\s+the\s+top|"
    r"top\s+\w+\s+only|"
    r"and\s+for|"
    r"also\s+show|"
    r"now\s+show|"
    r"now\s+only|"
    r"per\s+month\s+only|"
    r"by\s+month\s+only|"
    r"follow[- ]?up|"
    r"instead\s+(?:of|filter|show|group|by)"
    r")\b",
    re.IGNORECASE,
)

# Soft cues — only follow-ups when paired with BI / refinement vocabulary.
_SOFT_FOLLOW_UP_RE = re.compile(
    r"\b(what\s+about|how\s+about|instead)\b",
    re.IGNORECASE,
)

_ANAPHORA_RE = re.compile(
    r"\b(that|those|these|them|it|previous|above|earlier)\b",
    re.IGNORECASE,
)

# Short, incomplete analytics refinements that omit the prior metric, e.g.
# "get monthly insights from North". Keep this structural and domain-agnostic:
# a time grain + analytical view noun + filter phrase are all required.
_IMPLICIT_REFINEMENT_RE = re.compile(
    r"\b(?:monthly|weekly|daily|quarterly|yearly|annual)\s+"
    r"(?:insights?|breakdown|trends?|analysis|view|numbers?|results?)\b"
    r".*\b(?:for|from|in|only)\s+\w+",
    re.IGNORECASE,
)

# Enough signal that a soft/anaphoric cue is still an analytics refinement.
# Deliberately domain-agnostic: time grains, aggregations, and grouping /
# filtering structure only — never business nouns from any one schema.
_BI_CONTINUATION_RE = re.compile(
    r"\b("
    r"month|months|monthly|year|years|yearly|annual|quarter|quarters|quarterly|"
    r"week|weeks|weekly|day|days|daily|hour|hours|hourly|date|dates|"
    r"ytd|mtd|qtd|"
    r"sum|total|totals|count|avg|average|mean|median|percentile|"
    r"min|max|minimum|maximum|top|bottom|rank|ranking|"
    r"share|percent|percentage|ratio|distribution|"
    r"group|grouped|breakdown|split|filter|filtered|only|exclude|excluding|"
    r"include|including|limit|first|last|"
    r"trend|trends|compare|comparison|versus|vs|growth|change|delta|"
    r"metric|metrics|measure|measures|"
    r"(?:by|per|for|across)\s+\w+"
    r")\b",
    re.IGNORECASE,
)


def looks_like_follow_up(
    question: str,
    history: list[dict[str, str]] | None,
    *,
    schema_tokens: set[str] | frozenset[str] | None = None,
) -> bool:
    """
    True when the user is refining a prior turn rather than starting a new ask.

    Industry pattern: reuse prior SQL / join paths only for clear continuations,
    so unrelated questions in the same session stay unbiased.

    `schema_tokens` (table/column identifiers) lets ambiguous phrasings like
    "what about the West region?" count as refinements when they name warehouse
    entities, without hardcoding any domain's vocabulary. Callers without schema
    context fall back to structural cues only.
    """
    q = (question or "").strip()
    if not q:
        return False
    if not history:
        return False

    if _HARD_FOLLOW_UP_RE.search(q):
        return True

    if len(q.split()) <= 12 and _IMPLICIT_REFINEMENT_RE.search(q):
        return True

    continues_analytics = bool(_BI_CONTINUATION_RE.search(q)) or _mentions_schema(
        q, schema_tokens
    )
    if _SOFT_FOLLOW_UP_RE.search(q) and continues_analytics:
        return True

    # Short anaphoric refinements only when still clearly analytics-shaped.
    words = q.split()
    if len(words) <= 14 and _ANAPHORA_RE.search(q) and continues_analytics:
        return True

    return False


def _mentions_schema(
    question: str,
    schema_tokens: set[str] | frozenset[str] | None,
) -> bool:
    """Question names a warehouse identifier (schema-driven, not domain-coded)."""
    if not schema_tokens:
        return False
    tokens = {
        m.group(0).lower() for m in _WORD_RE.finditer(question) if len(m.group(0)) >= 3
    }
    if not tokens:
        return False
    return any(token in schema_tokens for token in tokens)


def tables_from_sql(sql: str | None) -> list[str]:
    """Bare table names referenced by FROM / JOIN clauses in prior SQL."""
    if not sql:
        return []
    names: list[str] = []
    seen: set[str] = set()
    for match in _SQL_TABLE_RE.finditer(sql):
        name = (match.group(2) or match.group(3) or "").lower()
        if not name or name in _SQL_NOISE_TABLES or name in seen:
            continue
        seen.add(name)
        names.append(name)
    return names


def last_user_question(history: list[dict[str, str]] | None) -> str | None:
    """Most recent user turn — the ask a follow-up is refining."""
    for item in reversed(history or []):
        if not isinstance(item, dict):
            continue
        if item.get("role") != "user":
            continue
        content = item.get("content")
        if isinstance(content, str) and content.strip():
            return content.strip()
    return None


def build_retrieval_query(
    question: str,
    history: list[dict[str, str]] | None,
    *,
    prior_sql: str | None = None,
) -> str:
    """
    Embedding text for RAG seed retrieval.

    Short refinements ("break that down by month") carry no schema tokens, so
    cosine search returns unrelated chunks and the planner loses the prior join
    path. Anchor them with the previous question and its table names.
    """
    q = (question or "").strip()
    if not q or not looks_like_follow_up(q, history):
        return q

    parts: list[str] = []
    prior = last_user_question(history)
    if prior and prior.lower() != q.lower():
        parts.append(prior)
    parts.append(q)
    tables = tables_from_sql(prior_sql)
    if tables:
        parts.append(" ".join(tables))
    return " ".join(parts)


def sanitize_source_metadata_for_client(
    metadata: dict | None,
) -> dict | None:
    """Drop planner-only fields before returning metadata to the UI/API."""
    if not metadata:
        return metadata
    if "prior_successful_sql" not in metadata:
        return metadata
    return {k: v for k, v in metadata.items() if k != "prior_successful_sql"}
