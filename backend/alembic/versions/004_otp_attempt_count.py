"""Add OTP attempt_count for brute-force lockout."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.models.table_schema import project_table_schema

revision: str = "004_otp_attempt_count"
down_revision: str | None = "003_refresh_tokens"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _schema_kw() -> dict:
    schema = project_table_schema()
    return {"schema": schema} if schema else {}


def upgrade() -> None:
    op.add_column(
        "email_otps",
        sa.Column(
            "attempt_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        **_schema_kw(),
    )


def downgrade() -> None:
    op.drop_column("email_otps", "attempt_count", **_schema_kw())
