"""FK neighborhood expansion for Text-to-SQL schema linking."""

from __future__ import annotations

import re
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Any

from app.services.schema_chunker import is_synthetic_table

_TABLE_LINE_RE = re.compile(r"^Table:\s*(\S+)\s*$", re.MULTILINE)
# Matches: customer_id -> sales.customers.customer_id  (or bare customers.customer_id)
_FK_LINE_RE = re.compile(
    r"^\s*-\s*(\w+)\s*->\s*(?:(\w+)\.)?(\w+)\.(\w+)\s*$",
    re.MULTILINE,
)
_ALLOWLIST_MISS_RE = re.compile(
    r"Table\s+'([^']+)'\s+is not in the allowed table set",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class SchemaChunk:
    """One indexed schema chunk with optional linker metadata."""

    content: str
    table: str
    schema_name: str | None = None
    metadata: dict[str, Any] | None = None


def parse_table_from_chunk(content: str) -> str | None:
    """Return bare table name from a `Table: schema.name` line."""
    match = _TABLE_LINE_RE.search(content or "")
    if not match:
        return None
    qualified = match.group(1)
    if "." in qualified:
        return qualified.split(".", 1)[1]
    return qualified


def parse_schema_from_chunk(content: str) -> str | None:
    match = _TABLE_LINE_RE.search(content or "")
    if not match:
        return None
    qualified = match.group(1)
    if "." in qualified:
        return qualified.split(".", 1)[0]
    return None


def parse_fk_edges_from_chunk(content: str, *, table: str | None = None) -> list[tuple[str, str]]:
    """
    Return undirected (table_a, table_b) edges from FK lines in chunk text.

    Prefer caller-supplied `table`; otherwise parse from the Table: line.
    """
    source = table or parse_table_from_chunk(content)
    if not source:
        return []
    edges: list[tuple[str, str]] = []
    for match in _FK_LINE_RE.finditer(content or ""):
        referenced = match.group(3)
        if referenced and referenced != source:
            edges.append((source, referenced))
    return edges


def parse_fk_edges_from_metadata(
    table: str,
    metadata: dict[str, Any] | None,
) -> list[tuple[str, str]]:
    """Edges from structured foreign_keys metadata when present."""
    if not metadata:
        return []
    fks = metadata.get("foreign_keys")
    if not isinstance(fks, list):
        return []
    edges: list[tuple[str, str]] = []
    for item in fks:
        if not isinstance(item, dict):
            continue
        referenced = item.get("referenced_table")
        from_table = item.get("from_table")
        source = from_table if isinstance(from_table, str) and from_table else table
        if (
            isinstance(referenced, str)
            and referenced
            and source
            and referenced != source
        ):
            edges.append((source, referenced))
    return edges


def parse_allowlist_miss_tables(error: str | None) -> list[str]:
    """Extract table names from SqlValidationError allowlist messages."""
    if not error:
        return []
    return [m.group(1) for m in _ALLOWLIST_MISS_RE.finditer(error)]


def chunk_from_content(
    content: str,
    metadata: dict[str, Any] | None = None,
) -> SchemaChunk | None:
    meta = metadata or {}
    table = meta.get("table") if isinstance(meta.get("table"), str) else None
    schema_name = meta.get("schema") if isinstance(meta.get("schema"), str) else None
    if not table:
        table = parse_table_from_chunk(content)
    if not schema_name:
        schema_name = parse_schema_from_chunk(content)
    if not table:
        return None
    return SchemaChunk(
        content=content,
        table=table,
        schema_name=schema_name,
        metadata=meta or None,
    )


class SchemaLinker:
    """Expand cosine seed tables through the FK graph (schema linking)."""

    @staticmethod
    def build_graph(catalog: list[SchemaChunk]) -> dict[str, set[str]]:
        """Undirected adjacency: table -> neighboring tables."""
        adjacency: dict[str, set[str]] = defaultdict(set)
        for chunk in catalog:
            edges = parse_fk_edges_from_metadata(chunk.table, chunk.metadata)
            if not edges:
                edges = parse_fk_edges_from_chunk(chunk.content, table=chunk.table)
            for a, b in edges:
                if is_synthetic_table(a) or is_synthetic_table(b):
                    continue
                adjacency[a].add(b)
                adjacency[b].add(a)
            if not is_synthetic_table(chunk.table):
                adjacency.setdefault(chunk.table, set())
        return adjacency

    @staticmethod
    def expand(
        seeds: list[SchemaChunk],
        catalog: list[SchemaChunk],
        *,
        hops: int = 1,
        max_tables: int = 15,
    ) -> list[SchemaChunk]:
        """
        BFS from seed tables over the FK graph.

        Seeds are kept in retrieval order first; neighbors follow by BFS order.
        Stops at `max_tables` **real** tables. Synthetic overview chunks
        (catalog / ER) are preserved when present in seeds but do not consume
        the real-table budget.
        """
        if not seeds:
            return []

        by_table: dict[str, SchemaChunk] = {}
        for chunk in catalog:
            by_table.setdefault(chunk.table, chunk)
        for chunk in seeds:
            by_table[chunk.table] = chunk

        overview_seeds = [c for c in seeds if is_synthetic_table(c.table)]
        real_seeds = [c for c in seeds if not is_synthetic_table(c.table)]
        seed_tables = [c.table for c in real_seeds]

        if hops <= 0 or not real_seeds:
            real_capped = SchemaLinker._cap_chunks(
                real_seeds, by_table, seed_tables, max_tables
            )
            return SchemaLinker._with_overview(overview_seeds, real_capped)

        adjacency = SchemaLinker.build_graph(list(by_table.values()))
        selected: list[str] = []
        seen: set[str] = set()
        queue: deque[tuple[str, int]] = deque()

        for table in seed_tables:
            if table in seen:
                continue
            seen.add(table)
            selected.append(table)
            queue.append((table, 0))

        while queue and len(selected) < max_tables:
            current, depth = queue.popleft()
            if depth >= hops:
                continue
            for neighbor in sorted(adjacency.get(current, ())):
                if neighbor in seen:
                    continue
                if neighbor not in by_table or is_synthetic_table(neighbor):
                    continue
                seen.add(neighbor)
                selected.append(neighbor)
                queue.append((neighbor, depth + 1))
                if len(selected) >= max_tables:
                    break

        real_chunks = [by_table[name] for name in selected if name in by_table]
        return SchemaLinker._with_overview(overview_seeds, real_chunks)

    @staticmethod
    def _with_overview(
        overview_seeds: list[SchemaChunk],
        real_chunks: list[SchemaChunk],
    ) -> list[SchemaChunk]:
        """Keep overview seed content without displacing real tables."""
        if not overview_seeds:
            return real_chunks
        seen = {c.table for c in real_chunks}
        extras = [c for c in overview_seeds if c.table not in seen]
        return extras + real_chunks

    @staticmethod
    def _cap_chunks(
        seeds: list[SchemaChunk],
        by_table: dict[str, SchemaChunk],
        seed_tables: list[str],
        max_tables: int,
    ) -> list[SchemaChunk]:
        out: list[SchemaChunk] = []
        seen: set[str] = set()
        for name in seed_tables:
            if name in seen or name not in by_table or is_synthetic_table(name):
                continue
            seen.add(name)
            out.append(by_table[name])
            if len(out) >= max_tables:
                break
        return out

    @staticmethod
    def merge_chunks(
        existing: list[SchemaChunk],
        extra: list[SchemaChunk],
        *,
        max_tables: int,
    ) -> list[SchemaChunk]:
        """Union chunks preserving existing order, then extras, capped on real tables."""
        by_table: dict[str, SchemaChunk] = {}
        order: list[str] = []
        for chunk in existing + extra:
            if chunk.table not in by_table:
                order.append(chunk.table)
            by_table[chunk.table] = chunk

        overview = [by_table[n] for n in order if is_synthetic_table(n)]
        real = [by_table[n] for n in order if not is_synthetic_table(n)][:max_tables]
        return overview + real
