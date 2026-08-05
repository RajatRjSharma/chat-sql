"""Detect warehouse-wide / catalog overview questions and format inventory."""

from __future__ import annotations

import re

from app.services.schema_chunker import is_synthetic_table

# Broad “what’s in the DB?” asks — not join-specific analytics.
_OVERVIEW_RE = re.compile(
    r"""(?ix)
    \b(
        (summary|overview|highlights)\s+of\s+(the\s+)?(db|database|schema|warehouse|data)
      | (all|list|show|how\s+many)\s+(all\s+)?tables
        (\s+(in|across|for)\s+(the\s+)?(db|database|schema|warehouse|catalog))?
      | tables?\s+in\s+(the\s+)?(db|database|schema|warehouse)
      | (what|which)\s+tables\s+(are\s+there|exist|do\s+(i|we)\s+have|are\s+available)
      | schema\s+(summary|overview|inventory)
      | inventory\s+of\s+(tables|the\s+schema)
      | give\s+me\s+(a\s+)?(summary|overview)\s+of\s+(the\s+)?(db|database|schema|warehouse)
      | (count|row\s+counts?)\s+(for\s+)?(all\s+)?tables
        (\s+(in|across)\s+(the\s+)?(db|database|schema|warehouse))?
    )\b
    """
)

# If present, the ask is scoped (joins / filters) — keep column DDL path.
_SCOPED_TABLE_ASK_RE = re.compile(
    r"""(?ix)
    \b(
        related|joining|join|reference|references|referencing
      | that\s+have|having|with\s+amount|with\s+column
    )\b
    """
)

_WORD_RE = re.compile(r"[a-z0-9_]+", re.IGNORECASE)

# Tokens that must never force-include a table via substring mention linking.
_MENTION_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "the",
        "is",
        "are",
        "was",
        "were",
        "what",
        "which",
        "who",
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
        "we",
        "you",
        "your",
        "please",
        "just",
        "give",
        "show",
        "tell",
        "get",
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
        "data",
        "database",
        "schema",
        "warehouse",
        "table",
        "tables",
        "column",
        "columns",
        "row",
        "rows",
        "amount",
        "amounts",
        "range",
        "ranging",
        "total",
        "totals",
        "sum",
        "count",
        "avg",
        "average",
        "min",
        "max",
        "user",
        "users",
        "query",
        "select",
        "sale",  # prefer explicit "sales" / table stem match below
    }
)


def is_catalog_overview_question(question: str) -> bool:
    """True when the user wants a warehouse-wide inventory / summary."""
    q = (question or "").strip()
    if not q:
        return False
    if not _OVERVIEW_RE.search(q):
        return False
    # "show tables related to invoices" must keep per-table DDL.
    if _SCOPED_TABLE_ASK_RE.search(q):
        return False
    return True


def format_catalog_inventory(
    *,
    schema_name: str | None,
    table_names: list[str],
) -> str:
    """Compact name list so the planner can UNION-count every indexed table."""
    names = sorted({n for n in table_names if n})
    if not names:
        return "No indexed tables available."

    prefix = f"{schema_name}." if schema_name else ""
    lines = [
        "Complete indexed table inventory for this warehouse "
        f"({len(names)} tables).",
        "For overview / row-count / 'all tables' / 'summary of db' questions, "
        "include EVERY table below in one query (e.g. UNION ALL of COUNT(*)). "
        "Do not omit any name from this list.",
        "",
    ]
    lines.extend(f"- {prefix}{name}" for name in names)
    return "\n".join(lines)


def _stem(token: str) -> str:
    t = token.lower()
    if len(t) > 4 and t.endswith("ies"):
        return t[:-3] + "y"
    if len(t) > 3 and t.endswith("es"):
        return t[:-2]
    if len(t) > 3 and t.endswith("s"):
        return t[:-1]
    return t


def _tokens_match(question_token: str, table_name: str) -> bool:
    q = question_token.lower()
    s = table_name.lower()
    if q == s:
        return True
    if _stem(q) == _stem(s):
        return True
    # Segment prefix: "invoice" ↔ "invoice_lines" (not "data" ↔ "database").
    segments = s.split("_")
    q_stem = _stem(q)
    if len(q_stem) >= 4 and any(_stem(seg) == q_stem or seg == q for seg in segments):
        return True
    return False


def tables_mentioned_in_question(
    question: str,
    catalog_tables: list[str],
) -> list[str]:
    """
    Schema-linking mention detection: table names (or stems) appearing in the ask.

    Used to force-include DDL chunks when cosine RAG misses an explicitly named table.
    """
    tokens = [
        m.group(0).lower()
        for m in _WORD_RE.finditer(question or "")
        if m.group(0).lower() not in _MENTION_STOPWORDS
    ]
    if not tokens:
        return []

    real = [t for t in catalog_tables if t and not is_synthetic_table(t)]
    # Longer names first so "invoice_lines" wins ordering when both match.
    real_sorted = sorted(real, key=lambda n: len(n), reverse=True)
    matched: list[str] = []
    seen: set[str] = set()
    for table in real_sorted:
        key = table.lower()
        if key in seen:
            continue
        for token in tokens:
            if _tokens_match(token, table):
                seen.add(key)
                matched.append(table)
                break
    return matched
