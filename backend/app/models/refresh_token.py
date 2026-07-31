"""Server-side refresh-token registry for rotation and logout revoke."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.table_schema import fk_table, project_table_args

if TYPE_CHECKING:
    from app.models.user import User


class RefreshToken(Base):
    """
    Persisted refresh session keyed by hashed JWT `jti`.
    Logout / rotation marks rows revoked so stolen tokens stop working.
    """

    __tablename__ = "refresh_tokens"
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
    jti_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # Optional note field kept small for debugging revoke reason.
    revoke_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    user: Mapped["User"] = relationship(back_populates="refresh_tokens")
