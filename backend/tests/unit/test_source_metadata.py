"""Tests for warehouse / AI provenance metadata."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

from app.services.source_metadata import (
    build_source_metadata,
    format_metadata_for_llm,
    resolve_engine_profile,
)


class TestResolveEngineProfile:
    def test_postgres_profile(self) -> None:
        profile = resolve_engine_profile("postgres")
        assert profile["engine"] == "PostgreSQL"
        assert profile["sql_dialect"] == "postgres"
        assert profile["vendor"]

    def test_mysql_profile(self) -> None:
        profile = resolve_engine_profile("mysql")
        assert profile["engine"] == "MySQL"
        assert profile["sql_dialect"] == "mysql"


class TestBuildSourceMetadata:
    def test_builds_safe_payload(self) -> None:
        source = SimpleNamespace(
            id=uuid.uuid4(),
            name="Demo Sales Warehouse",
            db_type="postgres",
            host="localhost",
            port=5433,
            database="bi_warehouse",
            schema_name="sales",
            is_readonly=True,
        )
        meta = build_source_metadata(
            source,  # type: ignore[arg-type]
            tables_in_context=["orders", "customers"],
            chunks_retrieved=3,
            context_mode="rag",
        )
        assert meta["engine"] == "PostgreSQL"
        assert meta["sql_dialect"] == "postgres"
        assert meta["database"] == "bi_warehouse"
        assert "orders" in meta["tables_in_context"]
        assert "embedding_model" in meta
        assert "llm_model" in meta
        assert "password" not in meta
        assert "connection_url" not in str(meta)

        text = format_metadata_for_llm(meta)
        assert "PostgreSQL" in text
        assert "sales" in text
