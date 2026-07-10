"""Tests for database URL builders."""

from __future__ import annotations

from app.core.db_url import build_postgres_url, to_sync_url


class TestBuildPostgresUrl:
    def test_builds_async_url(self) -> None:
        url = build_postgres_url(
            host="localhost",
            port=5432,
            database="bi_app",
            username="postgres",
            password="postgres",
            driver="asyncpg",
        )
        assert url == "postgresql+asyncpg://postgres:postgres@localhost:5432/bi_app"

    def test_escapes_special_characters_in_password(self) -> None:
        url = build_postgres_url(
            host="db.local",
            port=5432,
            database="app",
            username="user",
            password="p@ss:w/rd",
            driver="asyncpg",
        )
        assert "p%40ss%3Aw%2Frd" in url

    def test_builds_driverless_url(self) -> None:
        url = build_postgres_url(
            host="localhost",
            port=5433,
            database="bi_warehouse",
            username="bi_readonly",
            password="readonly_pass",
            driver=None,
        )
        assert url.startswith("postgresql://")
        assert "+asyncpg" not in url


class TestToSyncUrl:
    def test_converts_asyncpg_to_psycopg2_scheme(self) -> None:
        async_url = "postgresql+asyncpg://postgres:postgres@localhost:5432/bi_app"
        assert to_sync_url(async_url) == "postgresql://postgres:postgres@localhost:5432/bi_app"
