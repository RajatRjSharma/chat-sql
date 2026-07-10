"""Schema embedding model for RAG over warehouse metadata."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.config import settings
from app.models.base import Base
from app.models.table_schema import fk_table, project_table_args

if TYPE_CHECKING:
    from app.models.data_source import DataSource


class SchemaEmbedding(Base):
    """Vector index of warehouse schema chunks for schema-aware RAG."""

    __tablename__ = "schema_embeddings"
    __table_args__ = project_table_args()

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    data_source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(fk_table("data_sources.id"), ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[Optional[list[float]]] = mapped_column(
        Vector(settings.embedding_dimensions),
        nullable=True,
    )
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        default=dict,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    data_source: Mapped["DataSource"] = relationship(back_populates="schema_embeddings")
