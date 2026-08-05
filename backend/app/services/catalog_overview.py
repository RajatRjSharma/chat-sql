"""Detect warehouse-wide / catalog overview questions and format inventory."""

from __future__ import annotations

import re

# Broad “what’s in the DB?” asks — not join-specific analytics.
_OVERVIEW_RE = re.compile(
    r"""(?ix)
    \b(
        (summary|overview|highlights)\s+of\s+(the\s+)?(db|database|schema|warehouse|data)
      | (all|list|show|how\s+many)\s+tables
      | tables?\s+in\s+(the\s+)?(db|database|schema|warehouse)
      | (what|which)\s+tables\s+(are\s+there|exist|do\s+(i|we)\s+have|are\s+available)
      | schema\s+(summary|overview|inventory)
      | inventory\s+of\s+(tables|the\s+schema)
      | give\s+me\s+(a\s+)?(summary|overview)\s+of\s+(the\s+)?(db|database|schema|warehouse)
      | (count|row\s+counts?)\s+(for\s+)?(all\s+)?tables
    )\b
    """
)


def is_catalog_overview_question(question: str) -> bool:
    """True when the user wants a warehouse-wide inventory / summary."""
    q = (question or "").strip()
    if not q:
        return False
    return bool(_OVERVIEW_RE.search(q))


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
