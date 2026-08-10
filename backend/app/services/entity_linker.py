"""Small-token LLM entity linker for analytics / follow-up asks.

Extracts tables, measures, dimensions, filters, and time grain as compact JSON
to drive RAG force-includes. Vocabulary is derived from the connected warehouse
catalog (schema_vocab) — not a fixed retail word list.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

from app.config import settings
from app.core.exceptions import AIProviderError
from app.providers.ai import AIClient, get_ai_client
from app.services.catalog_overview import (
    link_tables_for_question,
    tables_mentioned_in_question,
)
from app.services.nl_normalize import nouns_match
from app.services.nlp_json import extract_json_object
from app.services.schema_vocab import (
    catalog_dimension_columns,
    catalog_measure_columns,
    measure_ask_tokens,
)

logger = logging.getLogger(__name__)

_QUOTED_RE = re.compile(r"[\"']([^\"']{1,64})[\"']")
_FILTER_PREP_RE = re.compile(
    r"\b(?:for|from|in|only|where|filter(?:ed)?\s+to)\s+(?:the\s+)?([A-Za-z][\w\s-]{0,40})",
    re.IGNORECASE,
)

_SYSTEM = """\
Extract warehouse entities for Text2SQL schema linking.

Return ONLY compact JSON (no markdown):
{"tables":[],"measures":[],"dimensions":[],"filters":[],"time_grain":null}

Rules:
1. tables: only names from the provided table list (exact or clear stem match).
2. measures: metrics implied by the question; prefer names from measure_columns.
3. dimensions: grouping attributes; prefer names from dimension_columns.
4. filters: literal values or labels mentioned in the question (codes, names,
   quoted strings) — do NOT invent domain-specific defaults.
5. time_grain: one of month|week|day|quarter|year or null.
6. Prefer empty arrays over guesses. Max 8 tables, 6 measures, 6 dimensions, 6 filters.
"""


@dataclass(frozen=True, slots=True)
class EntityLinkResult:
    tables: tuple[str, ...] = ()
    measures: tuple[str, ...] = ()
    dimensions: tuple[str, ...] = ()
    filters: tuple[str, ...] = ()
    time_grain: str | None = None
    source: str = "fallback"
    retrieval_query_extra: str = ""

    def to_metadata(self) -> dict[str, Any]:
        return {
            "linked_tables": list(self.tables),
            "linked_measures": list(self.measures),
            "linked_dimensions": list(self.dimensions),
            "linked_filters": list(self.filters),
            "time_grain": self.time_grain,
            "entity_source": self.source,
        }


class EntityLinker:
    """Compact JSON entity extraction with schema-derived fallback."""

    @staticmethod
    def fallback(
        question: str,
        *,
        table_names: list[str],
        catalog_chunks: list[Any] | None = None,
    ) -> EntityLinkResult:
        names = [n for n in table_names if n]
        chunks = list(catalog_chunks or [])
        mentioned = tables_mentioned_in_question(question, names)
        concept: list[str] = []
        if chunks:
            concept = link_tables_for_question(question, chunks)
        force = list(dict.fromkeys([*mentioned, *concept]))

        measure_cols = catalog_measure_columns(chunks) if chunks else []
        dim_cols = catalog_dimension_columns(chunks) if chunks else []
        measures = _measures_from_question(question, measure_cols)
        dimensions = _dimensions_from_question(
            question, dim_cols, table_names=names
        )
        filters = _filters_from_question(question)
        grain = _time_grain_from_question(question)
        extra = " ".join(
            part
            for part in (
                " ".join(force),
                " ".join(measures),
                " ".join(dimensions),
                " ".join(filters),
                grain or "",
            )
            if part
        ).strip()
        return EntityLinkResult(
            tables=tuple(force),
            measures=tuple(measures),
            dimensions=tuple(dimensions),
            filters=tuple(filters),
            time_grain=grain,
            source="fallback",
            retrieval_query_extra=extra,
        )

    @staticmethod
    def parse(
        raw: str,
        *,
        table_names: list[str],
    ) -> EntityLinkResult | None:
        payload = extract_json_object(raw)
        if not payload:
            return None
        resolved_tables = _resolve_tables(payload.get("tables") or [], table_names)
        measures = _string_list(payload.get("measures"), limit=6)
        dimensions = _string_list(payload.get("dimensions"), limit=6)
        filters = _string_list(payload.get("filters"), limit=6)
        grain_raw = payload.get("time_grain")
        grain = None
        if isinstance(grain_raw, str) and grain_raw.strip().lower() in {
            "month",
            "week",
            "day",
            "quarter",
            "year",
        }:
            grain = grain_raw.strip().lower()
        extra = " ".join(
            part
            for part in (
                " ".join(resolved_tables),
                " ".join(measures),
                " ".join(dimensions),
                " ".join(filters),
                grain or "",
            )
            if part
        ).strip()
        return EntityLinkResult(
            tables=tuple(resolved_tables),
            measures=tuple(measures),
            dimensions=tuple(dimensions),
            filters=tuple(filters),
            time_grain=grain,
            source="llm",
            retrieval_query_extra=extra,
        )

    @staticmethod
    def link(
        question: str,
        *,
        table_names: list[str],
        catalog_chunks: list[Any] | None = None,
        client: AIClient | None = None,
    ) -> EntityLinkResult:
        q = (question or "").strip()
        names = sorted({n for n in table_names if n})
        chunks = list(catalog_chunks or [])
        if not q or not names:
            return EntityLinker.fallback(
                q, table_names=names, catalog_chunks=chunks
            )

        measure_cols = catalog_measure_columns(chunks)[:40]
        dim_cols = catalog_dimension_columns(chunks)[:40]
        name_block = ", ".join(names[:80])
        user_block = (
            f"tables: {name_block}\n"
            f"measure_columns: {', '.join(measure_cols) or '(none typed)'}\n"
            f"dimension_columns: {', '.join(dim_cols) or '(none typed)'}\n"
            f"question: {q}"
        )
        ai = client or get_ai_client()
        if not settings.nlp_prefer_llm:
            return EntityLinker.fallback(
                q, table_names=names, catalog_chunks=chunks
            )
        try:
            raw = ai.complete(
                [
                    {"role": "system", "content": _SYSTEM},
                    {"role": "user", "content": user_block},
                ],
                temperature=0.0,
                max_tokens=settings.nlp_entity_max_tokens,
                preferred_model=settings.effective_llm_router_model,
            )
            parsed = EntityLinker.parse(raw, table_names=names)
            if parsed is None:
                logger.info("EntityLinker invalid JSON; using fallback")
                return EntityLinker.fallback(
                    q, table_names=names, catalog_chunks=chunks
                )
            fb = EntityLinker.fallback(
                q, table_names=names, catalog_chunks=chunks
            )
            merged_tables = list(dict.fromkeys([*parsed.tables, *fb.tables]))[:8]
            merged_measures = list(
                dict.fromkeys([*parsed.measures, *fb.measures])
            )[:6]
            merged_dims = list(
                dict.fromkeys([*parsed.dimensions, *fb.dimensions])
            )[:6]
            merged_filters = list(
                dict.fromkeys([*parsed.filters, *fb.filters])
            )[:6]
            grain = parsed.time_grain or fb.time_grain
            extra = " ".join(
                part
                for part in (
                    " ".join(merged_tables),
                    " ".join(merged_measures),
                    " ".join(merged_dims),
                    " ".join(merged_filters),
                    grain or "",
                )
                if part
            ).strip()
            return EntityLinkResult(
                tables=tuple(merged_tables),
                measures=tuple(merged_measures),
                dimensions=tuple(merged_dims),
                filters=tuple(merged_filters),
                time_grain=grain,
                source="llm",
                retrieval_query_extra=extra,
            )
        except AIProviderError as exc:
            logger.warning("EntityLinker LLM failed (%s); using fallback", exc)
            return EntityLinker.fallback(
                q, table_names=names, catalog_chunks=chunks
            )


def _string_list(value: Any, *, limit: int) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        text = str(item or "").strip()
        if text and text not in out:
            out.append(text)
        if len(out) >= limit:
            break
    return out


def _resolve_tables(candidates: list[Any], catalog_names: list[str]) -> list[str]:
    if not candidates or not catalog_names:
        return []
    by_lower = {n.lower(): n for n in catalog_names}
    resolved: list[str] = []
    for raw in candidates:
        token = str(raw or "").strip()
        if not token:
            continue
        bare = token.split(".")[-1]
        hit = by_lower.get(bare.lower())
        if hit:
            if hit not in resolved:
                resolved.append(hit)
            continue
        for name in catalog_names:
            if nouns_match(bare, name) or nouns_match(bare, name.split("_")[0]):
                if name not in resolved:
                    resolved.append(name)
                break
        if len(resolved) >= 8:
            break
    return resolved


def _measures_from_question(question: str, measure_cols: list[str]) -> list[str]:
    q = (question or "").lower()
    found: list[str] = []
    ask = measure_ask_tokens()
    for token in ask:
        if re.search(rf"\b{re.escape(token)}\b", q):
            found.append(token)
    for col in measure_cols:
        if re.search(rf"\b{re.escape(col.lower())}\b", q) and col not in found:
            found.append(col)
    return found[:6]


def _dimensions_from_question(
    question: str,
    dim_cols: list[str],
    *,
    table_names: list[str] | None = None,
) -> list[str]:
    q = (question or "").lower()
    found: list[str] = []
    # Structural time grains always allowed.
    for token in ("month", "year", "week", "day", "quarter"):
        if re.search(rf"\b{re.escape(token)}\b", q):
            found.append(token)
    for col in dim_cols:
        col_l = col.lower()
        if re.search(rf"\b{re.escape(col_l)}\b", q) and col_l not in found:
            found.append(col_l)
    # Table stems used as dimensions ("by channel" → channels table).
    for name in table_names or []:
        bare = name.lower()
        for match in re.finditer(r"[a-z0-9_]+", q):
            token = match.group(0)
            if token in found or token in measure_ask_tokens():
                continue
            if nouns_match(token, bare) or nouns_match(token, bare.split("_")[0]):
                found.append(token)
                break
    return found[:6]


def _filters_from_question(question: str) -> list[str]:
    """Literal filters from quotes / for|in|from phrases — no domain word lists."""
    q = question or ""
    found: list[str] = []
    for match in _QUOTED_RE.finditer(q):
        text = match.group(1).strip()
        if text and text not in found:
            found.append(text)
    for match in _FILTER_PREP_RE.finditer(q):
        text = match.group(1).strip(" .,;:!?")
        # Keep short label phrases (1–3 tokens), drop long clauses.
        parts = text.split()
        if not parts or len(parts) > 3:
            continue
        # Skip pure analytics glue words.
        if parts[0].lower() in {
            "the",
            "a",
            "an",
            "this",
            "that",
            "each",
            "every",
            "all",
            "monthly",
            "weekly",
            "daily",
            "total",
            "sum",
        }:
            continue
        label = " ".join(parts)
        if label and label not in found:
            found.append(label)
    return found[:6]


def _time_grain_from_question(question: str) -> str | None:
    q = (question or "").lower()
    for grain, pattern in (
        ("month", r"\bmonth(?:ly|s)?\b"),
        ("week", r"\bweek(?:ly|s)?\b"),
        ("day", r"\bdaily\b|\bby\s+day\b"),
        ("quarter", r"\bquarter(?:ly)?\b"),
        ("year", r"\byear(?:ly|s)?\b|\bannual\b"),
    ):
        if re.search(pattern, q):
            return grain
    return None
