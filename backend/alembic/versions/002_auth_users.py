"""Add users, email OTPs, and ownership columns on sources/sessions."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.models.table_schema import project_table_schema

revision: str = "002_auth_users"
down_revision: Union[str, None] = "001_init_app_schema"
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
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("username", sa.String(length=64), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False, server_default="analyst"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "email_verified",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("email", name="uq_users_email"),
        sa.UniqueConstraint("username", name="uq_users_username"),
        **schema_kw,
    )
    op.create_index("ix_users_email", "users", ["email"], **schema_kw)
    op.create_index("ix_users_username", "users", ["username"], **schema_kw)

    op.create_table(
        "email_otps",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "purpose",
            sa.String(length=32),
            nullable=False,
            server_default="verify_email",
        ),
        sa.Column("code_hash", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], [_fk("users.id")], ondelete="CASCADE"),
        **schema_kw,
    )
    op.create_index("ix_email_otps_user_id", "email_otps", ["user_id"], **schema_kw)

    # Ownership — wipe pre-auth orphan rows so NOT NULL is safe for local demos.
    op.execute(sa.text(f'DELETE FROM {_fk("messages")}'))
    op.execute(sa.text(f'DELETE FROM {_fk("query_history")}'))
    op.execute(sa.text(f'DELETE FROM {_fk("schema_embeddings")}'))
    op.execute(sa.text(f'DELETE FROM {_fk("chat_sessions")}'))
    op.execute(sa.text(f'DELETE FROM {_fk("data_sources")}'))

    op.add_column(
        "data_sources",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        **schema_kw,
    )
    op.create_foreign_key(
        "fk_data_sources_user_id",
        "data_sources",
        "users",
        ["user_id"],
        ["id"],
        source_schema=schema_kw.get("schema"),
        referent_schema=schema_kw.get("schema"),
        ondelete="CASCADE",
    )
    op.create_index("ix_data_sources_user_id", "data_sources", ["user_id"], **schema_kw)

    op.add_column(
        "chat_sessions",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        **schema_kw,
    )
    op.create_foreign_key(
        "fk_chat_sessions_user_id",
        "chat_sessions",
        "users",
        ["user_id"],
        ["id"],
        source_schema=schema_kw.get("schema"),
        referent_schema=schema_kw.get("schema"),
        ondelete="CASCADE",
    )
    op.create_index("ix_chat_sessions_user_id", "chat_sessions", ["user_id"], **schema_kw)


def downgrade() -> None:
    schema_kw = _schema_kw()
    op.drop_index("ix_chat_sessions_user_id", table_name="chat_sessions", **schema_kw)
    op.drop_constraint(
        "fk_chat_sessions_user_id", "chat_sessions", type_="foreignkey", **schema_kw
    )
    op.drop_column("chat_sessions", "user_id", **schema_kw)

    op.drop_index("ix_data_sources_user_id", table_name="data_sources", **schema_kw)
    op.drop_constraint(
        "fk_data_sources_user_id", "data_sources", type_="foreignkey", **schema_kw
    )
    op.drop_column("data_sources", "user_id", **schema_kw)

    op.drop_index("ix_email_otps_user_id", table_name="email_otps", **schema_kw)
    op.drop_table("email_otps", **schema_kw)
    op.drop_index("ix_users_username", table_name="users", **schema_kw)
    op.drop_index("ix_users_email", table_name="users", **schema_kw)
    op.drop_table("users", **schema_kw)
