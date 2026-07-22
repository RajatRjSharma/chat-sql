"""Chat session model — links conversation to a data source."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.table_schema import fk_table, project_table_args

if TYPE_CHECKING:
    from app.models.data_source import DataSource
    from app.models.message import Message
    from app.models.query_history import QueryHistory
    from app.models.user import User


class ChatSession(Base):
    """A single conversational analytics session."""

    __tablename__ = "chat_sessions"
    __table_args__ = project_table_args()

    session_id: Mapped[uuid.UUID] = mapped_column(
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
    data_source_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(fk_table("data_sources.id"), ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    context_cache: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
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

    owner: Mapped["User"] = relationship(back_populates="chat_sessions")
    data_source: Mapped[Optional["DataSource"]] = relationship(back_populates="sessions")
    messages: Mapped[list["Message"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
    )
    query_history: Mapped[list["QueryHistory"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
    )
