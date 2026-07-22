"""Warehouse / analytics database connection configuration."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.table_schema import fk_table, project_table_args

if TYPE_CHECKING:
    from app.models.message import Message
    from app.models.query_history import QueryHistory
    from app.models.schema_embedding import SchemaEmbedding
    from app.models.session import ChatSession
    from app.models.user import User


class DataSource(Base):
    """
    Registry of analytics database connections.
    Demo warehouse and future user-provided DBs are stored here.
    Credentials should be encrypted at rest in production.
    """

    __tablename__ = "data_sources"
    __table_args__ = project_table_args()

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(fk_table("users.id"), ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    db_type: Mapped[str] = mapped_column(String(50), nullable=False, default="postgres")
    host: Mapped[str] = mapped_column(String(255), nullable=False)
    port: Mapped[int] = mapped_column(Integer, nullable=False, default=5432)
    database: Mapped[str] = mapped_column(String(100), nullable=False)
    schema_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    username: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    # Encrypted at rest; nullable when credentials are supplied out of band.
    password_encrypted: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_readonly: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    extra_config: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    owner: Mapped["User"] = relationship(back_populates="data_sources")
    sessions: Mapped[list["ChatSession"]] = relationship(back_populates="data_source")
    schema_embeddings: Mapped[list["SchemaEmbedding"]] = relationship(
        back_populates="data_source",
    )
