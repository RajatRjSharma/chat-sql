"""Serialize SchemaChunk for LangGraph state (JSON-friendly dicts)."""

from __future__ import annotations

from typing import Any

from app.services.schema_linker import SchemaChunk


def chunk_to_dict(chunk: SchemaChunk) -> dict[str, Any]:
    return {
        "content": chunk.content,
        "table": chunk.table,
        "schema_name": chunk.schema_name,
        "metadata": chunk.metadata,
    }


def chunk_from_dict(payload: dict[str, Any]) -> SchemaChunk:
    return SchemaChunk(
        content=str(payload.get("content") or ""),
        table=str(payload.get("table") or ""),
        schema_name=payload.get("schema_name"),
        metadata=payload.get("metadata")
        if isinstance(payload.get("metadata"), dict)
        else None,
    )


def chunks_to_dicts(chunks: list[SchemaChunk]) -> list[dict[str, Any]]:
    return [chunk_to_dict(c) for c in chunks]


def chunks_from_dicts(payloads: list[dict[str, Any]] | None) -> list[SchemaChunk]:
    if not payloads:
        return []
    return [chunk_from_dict(p) for p in payloads if isinstance(p, dict)]
