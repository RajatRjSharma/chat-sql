"""Embed warehouse schema chunks into the project DB (pgvector)."""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.core.exceptions import SchemaEmbeddingError, SchemaIndexInProgressError
from app.models import SchemaEmbedding
from app.providers.ai import AIClient, get_ai_client
from app.services.data_profiler import DataProfiler, table_profile_lookup
from app.services.data_source_service import DataSourceService
from app.services.schema_chunker import chunk_tables
from app.services.schema_introspection import SchemaIntrospectionService
from app.services.source_metadata import build_source_metadata

# Per-process guard against overlapping rebuilds for the same source.
_indexing_lock = asyncio.Lock()
_indexing_sources: set[uuid.UUID] = set()


@dataclass(frozen=True, slots=True)
class SchemaEmbedResult:
    """Outcome of a schema index rebuild."""

    chunks_embedded: int
    tables_indexed: int
    previous_chunks: int
    indexed_at: datetime


class SchemaEmbeddingService:
    """Introspect → chunk → embed → persist schema embeddings."""

    @staticmethod
    async def embed_data_source(
        session: AsyncSession,
        data_source_id: uuid.UUID,
        *,
        user_id: uuid.UUID | None = None,
        client: AIClient | None = None,
    ) -> SchemaEmbedResult:
        async with _indexing_lock:
            if data_source_id in _indexing_sources:
                raise SchemaIndexInProgressError(
                    "Schema index rebuild already in progress for this data source."
                )
            _indexing_sources.add(data_source_id)

        try:
            return await SchemaEmbeddingService._embed_unlocked(
                session,
                data_source_id,
                user_id=user_id,
                client=client,
            )
        finally:
            async with _indexing_lock:
                _indexing_sources.discard(data_source_id)

    @staticmethod
    async def _embed_unlocked(
        session: AsyncSession,
        data_source_id: uuid.UUID,
        *,
        user_id: uuid.UUID | None = None,
        client: AIClient | None = None,
    ) -> SchemaEmbedResult:
        data_source = await DataSourceService.get_active(
            session, data_source_id, user_id=user_id
        )
        info = DataSourceService.connection_info_from_record(data_source)

        previous_chunks = await SchemaEmbeddingService.count_embeddings(
            session, data_source_id
        )

        tables = SchemaIntrospectionService.introspect(info)
        if not tables:
            raise SchemaEmbeddingError(
                f"No tables found for data source {data_source_id} "
                f"(schema={info.schema_name or 'default'})."
            )

        # Row counts / date windows / measure ranges / categorical samples for SQL prompts.
        try:
            data_profile = DataProfiler().profile(info, tables)
        except Exception as exc:  # noqa: BLE001 — indexing must still succeed
            data_profile = {
                "version": 1,
                "error": f"data profile failed: {exc}"[:300],
                "tables": [],
                "temporal_windows": [],
                "table_count": 0,
                "approx_total_rows": 0,
            }

        source_meta = build_source_metadata(
            data_source,
            tables_in_context=[t.table_name for t in tables],
            chunks_retrieved=len(tables),
            context_mode="embedding",
            include_full_data_profile=True,
        )
        # build_source_metadata reads extra_config; inject the fresh profile for chunking.
        source_meta = {**source_meta, "data_profile": data_profile}

        warehouse_header = (
            f"Warehouse: {source_meta['engine']} ({source_meta['db_type']}) | "
            f"Vendor: {source_meta['vendor']} | "
            f"Dialect: {source_meta['sql_dialect']} | "
            f"Database: {source_meta['database']} | "
            f"Schema: {source_meta['schema_name'] or 'default'} | "
            f"Host: {source_meta['host']}:{source_meta['port']} | "
            f"Embedding model: {source_meta['embedding_model']}"
        )

        chunks = chunk_tables(
            tables,
            warehouse_header=warehouse_header,
            engine_meta=source_meta,
            include_overview_chunks=True,
            table_profiles=table_profile_lookup(data_profile),
        )
        # Embed before mutating the index so a provider failure leaves the old
        # vectors intact.
        ai = client or get_ai_client()
        vectors = ai.embed([content for content, _ in chunks])
        if len(vectors) != len(chunks):
            raise SchemaEmbeddingError("Embedding count does not match chunk count.")

        indexed_at = datetime.now(UTC)

        await session.execute(
            delete(SchemaEmbedding).where(SchemaEmbedding.data_source_id == data_source_id)
        )

        for (content, metadata), vector in zip(chunks, vectors, strict=True):
            session.add(
                SchemaEmbedding(
                    data_source_id=data_source_id,
                    content=content,
                    embedding=vector,
                    metadata_=metadata,
                )
            )

        cfg = dict(data_source.extra_config or {})
        cfg["schema_indexed_at"] = indexed_at.isoformat()
        cfg["schema_table_count"] = len(tables)
        cfg["schema_chunk_count"] = len(chunks)
        cfg["data_profile"] = data_profile
        data_source.extra_config = cfg
        flag_modified(data_source, "extra_config")
        session.add(data_source)

        await session.flush()
        return SchemaEmbedResult(
            chunks_embedded=len(chunks),
            tables_indexed=len(tables),
            previous_chunks=previous_chunks,
            indexed_at=indexed_at,
        )

    @staticmethod
    async def count_embeddings(session: AsyncSession, data_source_id: uuid.UUID) -> int:
        result = await session.execute(
            select(func.count())
            .select_from(SchemaEmbedding)
            .where(SchemaEmbedding.data_source_id == data_source_id)
        )
        return int(result.scalar_one())
