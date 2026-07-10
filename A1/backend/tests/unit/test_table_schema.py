"""Tests for ORM table schema resolution."""

from __future__ import annotations

from unittest.mock import patch

from app.models import table_schema


class TestProjectTableSchema:
    def setup_method(self) -> None:
        table_schema.project_table_schema.cache_clear()

    def teardown_method(self) -> None:
        table_schema.project_table_schema.cache_clear()

    def test_empty_schema_uses_postgres_default(self) -> None:
        with patch("app.models.table_schema.get_settings") as mock_settings:
            mock_settings.return_value.app_db_schema = None
            assert table_schema.project_table_schema() is None
            assert table_schema.project_table_args() == {}
            assert table_schema.fk_table("data_sources.id") == "data_sources.id"

    def test_custom_schema_is_applied(self) -> None:
        with patch("app.models.table_schema.get_settings") as mock_settings:
            mock_settings.return_value.app_db_schema = "analytics"
            assert table_schema.project_table_schema() == "analytics"
            assert table_schema.project_table_args() == {"schema": "analytics"}
            assert table_schema.fk_table("data_sources.id") == "analytics.data_sources.id"
