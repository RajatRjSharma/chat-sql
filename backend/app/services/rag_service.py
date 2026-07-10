"""Retrieve relevant schema chunks via pgvector similarity search."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import SchemaEmbedding
from app.providers.openrouter import OpenRouterClient, get_openrouter_client


class RagService:
    """Schema-aware RAG over stored warehouse metadata embeddings."""

    @staticmethod
    async def retrieve(
        session: AsyncSession,
        data_source_id: uuid.UUID,
        question: str,
        *,
        top_k: int | None = None,
        client: OpenRouterClient | None = None,
    ) -> list[str]:
        k = top_k or settings.rag_top_k
        openrouter = client or get_openrouter_client()
        query_vector = openrouter.embed_one(question)

        # Cosine distance via pgvector: smaller = more similar
        stmt = (
            select(SchemaEmbedding.content)
            .where(SchemaEmbedding.data_source_id == data_source_id)
            .where(SchemaEmbedding.embedding.is_not(None))
            .order_by(SchemaEmbedding.embedding.cosine_distance(query_vector))
            .limit(k)
        )
        result = await session.execute(stmt)
        chunks = list(result.scalars().all())

        if chunks:
            return chunks

        # Fallback: return any stored chunks if vector search yields nothing
        fallback = await session.execute(
            select(SchemaEmbedding.content)
            .where(SchemaEmbedding.data_source_id == data_source_id)
            .limit(k)
        )
        return list(fallback.scalars().all())

    @staticmethod
    def format_context(chunks: list[str]) -> str:
        if not chunks:
            return "No schema context available."
        return "\n\n---\n\n".join(chunks)
