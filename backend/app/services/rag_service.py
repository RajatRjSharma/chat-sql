"""Retrieve relevant schema chunks via pgvector similarity search."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import SchemaEmbedding
from app.providers.ai import AIClient, get_ai_client
from app.services.schema_linker import SchemaChunk, chunk_from_content, parse_table_from_chunk


class RagService:
    """Schema-aware RAG over stored warehouse metadata embeddings."""

    @staticmethod
    async def retrieve_rows(
        session: AsyncSession,
        data_source_id: uuid.UUID,
        question: str,
        *,
        top_k: int | None = None,
        client: AIClient | None = None,
    ) -> list[SchemaChunk]:
        """Cosine top-K seed chunks with metadata for schema linking."""
        k = top_k or settings.rag_top_k
        ai = client or get_ai_client()
        query_vector = ai.embed_one(question)

        stmt = (
            select(SchemaEmbedding.content, SchemaEmbedding.metadata_)
            .where(SchemaEmbedding.data_source_id == data_source_id)
            .where(SchemaEmbedding.embedding.is_not(None))
            .order_by(SchemaEmbedding.embedding.cosine_distance(query_vector))
            .limit(k)
        )
        result = await session.execute(stmt)
        rows = list(result.all())
        if not rows:
            fallback = await session.execute(
                select(SchemaEmbedding.content, SchemaEmbedding.metadata_)
                .where(SchemaEmbedding.data_source_id == data_source_id)
                .limit(k)
            )
            rows = list(fallback.all())

        chunks: list[SchemaChunk] = []
        for content, metadata in rows:
            parsed = chunk_from_content(content, metadata if isinstance(metadata, dict) else {})
            if parsed:
                chunks.append(parsed)
        return chunks

    @staticmethod
    async def retrieve(
        session: AsyncSession,
        data_source_id: uuid.UUID,
        question: str,
        *,
        top_k: int | None = None,
        client: AIClient | None = None,
    ) -> list[str]:
        rows = await RagService.retrieve_rows(
            session,
            data_source_id,
            question,
            top_k=top_k,
            client=client,
        )
        return [row.content for row in rows]

    @staticmethod
    async def load_catalog(
        session: AsyncSession,
        data_source_id: uuid.UUID,
    ) -> list[SchemaChunk]:
        """All indexed chunks for a data source (content + metadata)."""
        result = await session.execute(
            select(SchemaEmbedding.content, SchemaEmbedding.metadata_).where(
                SchemaEmbedding.data_source_id == data_source_id
            )
        )
        chunks: list[SchemaChunk] = []
        for content, metadata in result.all():
            parsed = chunk_from_content(content, metadata if isinstance(metadata, dict) else {})
            if parsed:
                chunks.append(parsed)
        return chunks

    @staticmethod
    async def fetch_chunks_by_tables(
        session: AsyncSession,
        data_source_id: uuid.UUID,
        table_names: list[str],
    ) -> list[SchemaChunk]:
        """Fetch indexed chunks whose bare table name is in `table_names`."""
        wanted = {name.lower() for name in table_names if name}
        if not wanted:
            return []

        catalog = await RagService.load_catalog(session, data_source_id)
        matched: list[SchemaChunk] = []
        for chunk in catalog:
            if chunk.table.lower() in wanted:
                matched.append(chunk)
                continue
            # Fallback when metadata.table missing / mismatched
            parsed = parse_table_from_chunk(chunk.content)
            if parsed and parsed.lower() in wanted:
                matched.append(chunk)
        return matched

    @staticmethod
    def format_context(chunks: list[str]) -> str:
        if not chunks:
            return "No schema context available."
        return "\n\n---\n\n".join(chunks)

    @staticmethod
    def format_chunk_context(chunks: list[SchemaChunk]) -> str:
        return RagService.format_context([c.content for c in chunks])
