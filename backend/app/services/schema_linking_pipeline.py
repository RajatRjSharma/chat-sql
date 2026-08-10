"""Shared schema-linking pipeline used by chat prepare and offline eval.

Keeps mention / column / synonym linking + FK expand in one place so eval
cannot drift from production behavior.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.services.catalog_overview import (
    is_catalog_overview_question,
    link_tables_for_question,
    suggested_expand_hops,
    tables_mentioned_in_question,
)
from app.services.schema_chunker import is_synthetic_table
from app.services.schema_linker import SchemaChunk, SchemaLinker


@dataclass(frozen=True, slots=True)
class LinkingResult:
    """Output of one linking pass over RAG seeds + catalog."""

    linked_chunks: list[SchemaChunk]
    context_mode: str
    force_tables: tuple[str, ...]
    hops_used: int
    overview: bool


def apply_schema_linking(
    question: str,
    seed_rows: list[SchemaChunk],
    catalog: list[SchemaChunk],
    *,
    default_hops: int = 1,
    max_tables: int = 15,
    overview: bool | None = None,
    extra_force_tables: list[str] | None = None,
) -> LinkingResult:
    """
    Mirror of ChatService prepare linking (without DB / introspection fallback).

    1. Catalog-overview questions → full catalog, names-only mode upstream
    2. Else: force-include mentioned + column/synonym + extra_force tables into seeds
    3. FK-neighborhood expand (deeper hops when ≥2 forced tables)

    ``overview`` / ``extra_force_tables`` let IntentRouter + EntityLinker drive
    linking without relying solely on regex detectors.
    """
    is_overview = (
        bool(overview)
        if overview is not None
        else is_catalog_overview_question(question)
    )
    seeds = list(seed_rows)

    if is_overview and catalog:
        return LinkingResult(
            linked_chunks=list(catalog),
            context_mode="catalog_overview",
            force_tables=(),
            hops_used=0,
            overview=True,
        )

    if not seeds:
        return LinkingResult(
            linked_chunks=[],
            context_mode="empty",
            force_tables=(),
            hops_used=0,
            overview=False,
        )

    if not catalog:
        return LinkingResult(
            linked_chunks=seeds[:max_tables],
            context_mode="rag",
            force_tables=(),
            hops_used=0,
            overview=False,
        )

    catalog_names = [c.table for c in catalog]
    mentioned = tables_mentioned_in_question(question, catalog_names)
    concept_linked = link_tables_for_question(question, catalog)
    extra = [t for t in (extra_force_tables or []) if t]
    force_names = list(dict.fromkeys([*extra, *mentioned, *concept_linked]))

    context_mode = "rag"
    if force_names:
        by_table = {c.table.lower(): c for c in catalog}
        seed_by = {c.table.lower(): c for c in seeds}
        for name in force_names:
            chunk = by_table.get(name.lower())
            if chunk and name.lower() not in seed_by:
                seeds = [*seeds, chunk]
                seed_by[name.lower()] = chunk
        context_mode = "rag_mentioned"

    hops = suggested_expand_hops(len(force_names), default_hops)
    expanded = SchemaLinker.expand(
        seeds,
        catalog,
        hops=hops,
        max_tables=max_tables,
    )
    seed_names = {c.table for c in seeds}
    if any(c.table not in seed_names for c in expanded):
        context_mode = (
            "rag_expanded"
            if context_mode != "rag_mentioned"
            else "rag_mentioned_expanded"
        )

    # Drop synthetic overview chunks from analytics allowlist path callers
    # still filter; keep them here if they were seeds (prepare filters later).
    return LinkingResult(
        linked_chunks=expanded,
        context_mode=context_mode,
        force_tables=tuple(force_names),
        hops_used=hops,
        overview=False,
    )


def real_tables(chunks: list[SchemaChunk]) -> list[str]:
    """Bare table names excluding synthetic overview placeholders."""
    return sorted(
        {
            c.table
            for c in chunks
            if c.table and not is_synthetic_table(c.table)
        }
    )
