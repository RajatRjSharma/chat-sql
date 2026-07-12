"""Embed warehouse schema chunks into the project DB (pgvector)."""

from __future__ import annotations

import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import SchemaEmbeddingError
from app.models import SchemaEmbedding
from app.providers.ai import AIClient, get_ai_client
from app.services.data_source_service import DataSourceService
from app.services.schema_chunker import chunk_tables
from app.services.schema_introspection import SchemaIntrospectionService


class SchemaEmbeddingService:
    """Introspect → chunk → embed → persist schema embeddings."""

    @staticmethod
    async def embed_data_source(
        session: AsyncSession,
        data_source_id: uuid.UUID,
        *,
        client: AIClient | None = None,
    ) -> int:
        data_source = await DataSourceService.get_active(session, data_source_id)
        info = DataSourceService.connection_info_from_record(data_source)

        tables = SchemaIntrospectionService.introspect(info)
        if not tables:
            raise SchemaEmbeddingError(
                f"No tables found for data source {data_source_id} "
                f"(schema={info.schema_name or 'default'})."
            )

        chunks = chunk_tables(tables)
        ai = client or get_ai_client()
        vectors = ai.embed([content for content, _ in chunks])
        if len(vectors) != len(chunks):
            raise SchemaEmbeddingError("Embedding count does not match chunk count.")

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
        await session.flush()
        return len(chunks)

    @staticmethod
    async def count_embeddings(session: AsyncSession, data_source_id: uuid.UUID) -> int:
        result = await session.execute(
            select(SchemaEmbedding.id).where(SchemaEmbedding.data_source_id == data_source_id)
        )
        return len(result.scalars().all())
