"""Add refresh_tokens table for cookie session revoke/rotation."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.models.table_schema import project_table_schema

revision: str = "003_refresh_tokens"
down_revision: Union[str, None] = "002_auth_users"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _schema_kw() -> dict:
    schema = project_table_schema()
    return {"schema": schema} if schema else {}


def _fk(table_column: str) -> str:
    schema = project_table_schema()
    return f"{schema}.{table_column}" if schema else table_column


def upgrade() -> None:
    schema_kw = _schema_kw()
    op.create_table(
        "refresh_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("jti_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("user_agent", sa.String(length=512), nullable=True),
        sa.Column("revoke_reason", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            [_fk("users.id")],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("jti_hash", name="uq_refresh_tokens_jti_hash"),
        **schema_kw,
    )
    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"], **schema_kw)
    op.create_index("ix_refresh_tokens_jti_hash", "refresh_tokens", ["jti_hash"], **schema_kw)


def downgrade() -> None:
    schema_kw = _schema_kw()
    op.drop_index("ix_refresh_tokens_jti_hash", table_name="refresh_tokens", **schema_kw)
    op.drop_index("ix_refresh_tokens_user_id", table_name="refresh_tokens", **schema_kw)
    op.drop_table("refresh_tokens", **schema_kw)
