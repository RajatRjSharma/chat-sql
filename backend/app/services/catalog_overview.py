"""Detect warehouse-wide / catalog overview questions and format inventory.

Also provides schema-linking helpers: table-name mentions, column mentions,
and BI measure synonyms (e.g. revenue → amount) so multi-dim analytics asks
pull the right DDL into context.
"""

from __future__ import annotations

import re
from typing import Any, Protocol

from app.services.nl_normalize import noun_surface_variants, nouns_match
from app.services.schema_chunker import is_synthetic_table

# Broad “what’s in the DB?” asks — not join-specific analytics.
_DET = r"(?:the|this|my|our|a|an)\s+"
_DB_SCOPE = r"(?:full|entire|complete|whole)\s+"
_DB_NOUN = r"(?:db|database|schema|warehouse|catalog|data)"
_OVERVIEW_NOUN = (
    r"(?:summar(?:y|ize|ise)|overview|highlights|description|contents?|"
    r"inventory|catalog)"
)
_OVERVIEW_RE = re.compile(
    rf"""(?ix)
    \b(
        {_OVERVIEW_NOUN}\s+of\s+({_DET})?({_DB_SCOPE})?{_DB_NOUN}
      | summar(?:ize|ise)\s+({_DET})?({_DB_SCOPE})?{_DB_NOUN}
      | describe\s+({_DET})?({_DB_SCOPE})?{_DB_NOUN}
      | {_DB_NOUN}\s+(?:summary|overview|inventory|contents?)
      | what(?:'s|s|\s+is)\s+in\s+({_DET})?({_DB_SCOPE})?{_DB_NOUN}
      | (?:show|list|give)\s+me\s+(?:all\s+)?(?:the\s+)?tables?
      | (?:list|show|how\s+many)\s+(?:all\s+|every\s+|the\s+)?tables?
        (\s+(?:in|across|for)\s+({_DET})?({_DB_SCOPE})?{_DB_NOUN})?
      | (?:all|every)\s+(?:of\s+)?(?:the\s+)?tables?
        (\s+(?:in|across|for)\s+({_DET})?({_DB_SCOPE})?{_DB_NOUN})?
      | tables?\s+in\s+({_DET})?({_DB_SCOPE})?{_DB_NOUN}
      | (what|which)\s+tables\s+(are\s+there|exist|do\s+(i|we)\s+have|are\s+available)
      | schema\s+(summary|overview|inventory)
      | inventory\s+of\s+(tables|the\s+schema)
      | give\s+me\s+(a\s+)?{_OVERVIEW_NOUN}\s+of\s+({_DET})?({_DB_SCOPE})?{_DB_NOUN}
      | (count|row\s+counts?)\s+(for\s+)?(?:all\s+|every\s+)?tables?
        (\s+(?:in|across)\s+({_DET})?({_DB_SCOPE})?{_DB_NOUN})?
    )\b
    """
)

# If present, the ask is scoped (joins / filters) — keep column DDL path.
# Avoid bare "having" (false-positive on "tables having data").
_SCOPED_TABLE_ASK_RE = re.compile(
    r"""(?ix)
    \b(
        related|joining|join|reference|references|referencing
      | linked\s+to|connected\s+to|associated\s+with|containing
      | that\s+have
      | having\s+(?:an?\s+)?(?:amount|column|columns|field|fields)
      | with\s+amount|with\s+column
    )\b
    """
)

_WORD_RE = re.compile(r"[a-z0-9_]+", re.IGNORECASE)
_COLUMN_LINE_RE = re.compile(
    r"^\s*-\s*(?P<name>[A-Za-z_][\w]*)\s*:",
    re.MULTILINE,
)

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
        "by",
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

# Columns that appear on almost every table — never use for column linking.
_COLUMN_LINK_STOPWORDS = frozenset(
    {
        "id",
        "name",
        "title",
        "status",
        "type",
        "code",
        "date",
        "time",
        "created",
        "updated",
        "deleted",
        "active",
        "note",
        "notes",
        "description",
        "value",
        "key",
        "uuid",
        "email",
        "phone",
        "qty",
        "quantity",
        "count",
        "rank",
        "index",
        "flag",
        "year",
        "month",
        "day",
        "week",
    }
)

# BI vocabulary → warehouse measure columns (generic across schemas).
_MEASURE_SYNONYMS: dict[str, tuple[str, ...]] = {
    "revenue": (
        "amount",
        "total_amount",
        "line_amount",
        "unit_price",
        "price",
        "net_amount",
    ),
    "sales": ("amount", "total_amount", "line_amount"),
    "gmv": ("amount", "total_amount", "line_amount"),
    "spend": ("amount", "total_amount"),
    "income": ("amount", "total_amount"),
    "turnover": ("amount", "total_amount"),
    "bookings": ("amount", "total_amount", "booking_amount"),
    "margin": ("margin", "gross_margin", "net_margin", "amount"),
    "profit": ("profit", "net_profit", "gross_profit", "amount"),
    "cost": ("cost", "unit_cost", "total_cost", "amount"),
    "expense": ("expense", "amount", "total_amount"),
    "fee": ("fee", "fees", "amount"),
    "arr": ("arr", "amount", "total_amount"),
    "mrr": ("mrr", "amount", "total_amount"),
}


class _ChunkLike(Protocol):
    table: str
    content: str
    metadata: dict[str, Any] | None


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
    # "all tables have null amounts" is analytics, not an inventory ask.
    if re.search(r"\ball\s+tables?\s+(have|has|with|contain|including)\b", q, re.I):
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


def _question_tokens(question: str) -> list[str]:
    return [
        m.group(0).lower()
        for m in _WORD_RE.finditer(question or "")
        if m.group(0).lower() not in _MENTION_STOPWORDS
    ]


def _exact_or_stem_table_match(question_token: str, table_name: str) -> bool:
    return nouns_match(question_token, table_name)


def _segment_table_match(question_token: str, table_name: str) -> bool:
    """invoice ↔ invoice_lines; not data ↔ database."""
    q = question_token.lower()
    s = table_name.lower()
    segments = s.split("_")
    if len(segments) < 2:
        return False
    if len(q) < 4:
        return False
    return any(nouns_match(q, seg) or seg == q for seg in segments)


def tables_mentioned_in_question(
    question: str,
    catalog_tables: list[str],
) -> list[str]:
    """
    Schema-linking mention detection: table names (or stems) appearing in the ask.

    Prefer exact/stem full-name matches over multi-segment compounds so
    "channel" links `channels` and not only `campaign_channels`.
    """
    tokens = _question_tokens(question)
    if not tokens:
        return []

    real = [t for t in catalog_tables if t and not is_synthetic_table(t)]
    # Shorter names first for exact/stem pass so `channels` beats
    # `campaign_channels` when both stem-match poorly.
    by_len_asc = sorted(real, key=lambda n: (len(n), n.lower()))
    matched: list[str] = []
    seen: set[str] = set()
    claimed_tokens: set[str] = set()

    for table in by_len_asc:
        key = table.lower()
        if key in seen:
            continue
        for token in tokens:
            if _exact_or_stem_table_match(token, table):
                seen.add(key)
                claimed_tokens.add(token)
                matched.append(table)
                break

    # Segment matches only for tokens not already claimed by an exact table.
    by_len_desc = sorted(real, key=lambda n: len(n), reverse=True)
    for table in by_len_desc:
        key = table.lower()
        if key in seen:
            continue
        for token in tokens:
            if token in claimed_tokens:
                continue
            if _segment_table_match(token, table):
                seen.add(key)
                claimed_tokens.add(token)
                matched.append(table)
                break
    return matched


def _column_base(name: str) -> str:
    col = name.lower()
    for suffix in ("_id", "_ids", "_code", "_name", "_key", "_uuid", "_at", "_on"):
        if col.endswith(suffix) and len(col) > len(suffix) + 1:
            return col[: -len(suffix)]
    return col


def _column_matches_token(column: str, token: str) -> bool:
    col = column.lower()
    tok = token.lower()
    if tok in _COLUMN_LINK_STOPWORDS:
        return False
    if any(v in _COLUMN_LINK_STOPWORDS for v in noun_surface_variants(tok)):
        return False
    base = _column_base(col)
    if base in _COLUMN_LINK_STOPWORDS:
        return False
    if nouns_match(tok, col) or nouns_match(tok, base):
        return True
    return False


def parse_columns_from_chunk(content: str) -> list[str]:
    """Column names from a table DDL chunk (`- name: type` lines)."""
    return [m.group("name") for m in _COLUMN_LINE_RE.finditer(content or "")]


# Prefer these table-name hints when linking via measure synonyms only
# (avoid attaching every lookup table that happens to share a column name).
_FACTISH_TABLE_HINTS = (
    "order",
    "invoice",
    "payment",
    "sale",
    "revenue",
    "transaction",
    "ledger",
    "line",
    "event",
    "fact",
    "metric",
    "usage",
    "shipment",
    "booking",
    "ticket",
)


def _is_factish_table(table: str) -> bool:
    t = table.lower()
    return any(hint in t for hint in _FACTISH_TABLE_HINTS)


def tables_matching_columns(
    question: str,
    catalog_chunks: list[_ChunkLike],
) -> list[str]:
    """
    Force-include tables whose columns match question tokens or BI synonyms.

    Example: "revenue by region" → customers (region) + orders (amount via revenue).
    """
    tokens = _question_tokens(question)
    if not tokens:
        return []

    synonym_cols: set[str] = set()
    for token in tokens:
        for col in _MEASURE_SYNONYMS.get(token, ()):
            synonym_cols.add(col)

    matched: list[str] = []
    seen: set[str] = set()
    for chunk in catalog_chunks:
        table = chunk.table
        if not table or is_synthetic_table(table):
            continue
        key = table.lower()
        if key in seen:
            continue
        columns = parse_columns_from_chunk(chunk.content)
        if not columns:
            continue

        dimension_hit = False
        synonym_hit = False
        for col in columns:
            col_l = col.lower()
            if col_l in synonym_cols:
                synonym_hit = True
            for token in tokens:
                if _column_matches_token(col, token):
                    dimension_hit = True
                    break
            if dimension_hit and synonym_hit:
                break

        # Synonym-only hits stay on fact-ish tables (orders/invoices/…).
        if dimension_hit or (synonym_hit and _is_factish_table(table)):
            seen.add(key)
            matched.append(table)
    return matched


def link_tables_for_question(
    question: str,
    catalog_chunks: list[_ChunkLike],
) -> list[str]:
    """Union of table-name mentions and column/synonym matches (deduped)."""
    catalog_names = [c.table for c in catalog_chunks if c.table]
    named = tables_mentioned_in_question(question, catalog_names)
    columnish = tables_matching_columns(question, catalog_chunks)
    out: list[str] = []
    seen: set[str] = set()
    for name in [*named, *columnish]:
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(name)
    return out


def suggested_expand_hops(linked_table_count: int, default_hops: int) -> int:
    """
    Multi-dimension asks need a deeper FK walk (region + channel → customers).

    Industry linking often uses 2 hops when ≥2 seed tables are forced in.
    """
    hops = max(0, int(default_hops))
    if linked_table_count >= 2:
        return max(hops, 2)
    return hops
