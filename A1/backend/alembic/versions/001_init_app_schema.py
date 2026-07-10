"""Initial project database schema."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

from app.models.table_schema import project_table_schema

revision: str = "001_init_app_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

EMBEDDING_DIMENSIONS = 2048


def _schema_kw() -> dict:
    schema = project_table_schema()
    return {"schema": schema} if schema else {}


def _fk(table_column: str) -> str:
    schema = project_table_schema()
    return f"{schema}.{table_column}" if schema else table_column


def upgrade() -> None:
    schema = project_table_schema()
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    if schema:
        op.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')

    schema_kw = _schema_kw()

    op.create_table(
        "data_sources",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("db_type", sa.String(length=50), nullable=False, server_default="postgres"),
        sa.Column("host", sa.String(length=255), nullable=False),
        sa.Column("port", sa.Integer(), nullable=False, server_default="5432"),
        sa.Column("database", sa.String(length=100), nullable=False),
        sa.Column("schema_name", sa.String(length=100), nullable=True),
        sa.Column("username", sa.String(length=100), nullable=True),
        sa.Column("password_encrypted", sa.Text(), nullable=True),
        sa.Column("is_readonly", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("extra_config", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        **schema_kw,
    )

    op.create_table(
        "chat_sessions",
        sa.Column("session_id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("data_source_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("context_cache", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["data_source_id"], [_fk("data_sources.id")], ondelete="SET NULL"),
        **schema_kw,
    )
    op.create_index("ix_chat_sessions_data_source_id", "chat_sessions", ["data_source_id"], **schema_kw)

    op.create_table(
        "messages",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], [_fk("chat_sessions.session_id")], ondelete="CASCADE"),
        **schema_kw,
    )
    op.create_index("ix_messages_session_id", "messages", ["session_id"], **schema_kw)

    op.create_table(
        "query_history",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("sql_query", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], [_fk("chat_sessions.session_id")], ondelete="CASCADE"),
        **schema_kw,
    )
    op.create_index("ix_query_history_session_id", "query_history", ["session_id"], **schema_kw)

    op.create_table(
        "schema_embeddings",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("data_source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(EMBEDDING_DIMENSIONS), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["data_source_id"], [_fk("data_sources.id")], ondelete="CASCADE"),
        **schema_kw,
    )
    op.create_index("ix_schema_embeddings_data_source_id", "schema_embeddings", ["data_source_id"], **schema_kw)


def downgrade() -> None:
    schema_kw = _schema_kw()
    op.drop_table("schema_embeddings", **schema_kw)
    op.drop_table("query_history", **schema_kw)
    op.drop_table("messages", **schema_kw)
    op.drop_table("chat_sessions", **schema_kw)
    op.drop_table("data_sources", **schema_kw)

    schema = project_table_schema()
    if schema:
        op.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
