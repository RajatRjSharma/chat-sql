"""Build PostgreSQL connection URLs from discrete credentials."""

from __future__ import annotations

from urllib.parse import quote_plus, urlunparse


def build_postgres_url(
    *,
    host: str,
    port: int,
    database: str,
    username: str,
    password: str,
    driver: str | None = "asyncpg",
) -> str:
    """Construct a PostgreSQL SQLAlchemy URL from connection parts."""
    user = quote_plus(username)
    pwd = quote_plus(password)
    netloc = f"{user}:{pwd}@{host}:{port}"
    scheme = f"postgresql+{driver}" if driver else "postgresql"
    return urlunparse((scheme, netloc, f"/{database}", "", "", ""))


def to_sync_url(async_url: str) -> str:
    """Convert asyncpg URL to sync psycopg2 URL for Alembic."""
    return async_url.replace("postgresql+asyncpg", "postgresql")
