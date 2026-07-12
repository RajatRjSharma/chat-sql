"""Retrieve relevant schema chunks via pgvector similarity search."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import SchemaEmbedding
from app.providers.ai import AIClient, get_ai_client


class RagService:
    """Schema-aware RAG over stored warehouse metadata embeddings."""

    @staticmethod
    async def retrieve(
        session: AsyncSession,
        data_source_id: uuid.UUID,
        question: str,
        *,
        top_k: int | None = None,
        client: AIClient | None = None,
    ) -> list[str]:
        k = top_k or settings.rag_top_k
        ai = client or get_ai_client()
        query_vector = ai.embed_one(question)

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
