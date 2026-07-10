"""Tests for PostgreSQL schema helpers."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.core.schema import (
    POSTGRES_DEFAULT_SCHEMA,
    qualify_table,
    read_connection_schema,
    resolve_optional_schema,
    validate_optional_schema,
    validate_schema_identifier,
)


class TestValidateSchemaIdentifier:
    def test_accepts_valid_names(self) -> None:
        assert validate_schema_identifier("public") == "public"
        assert validate_schema_identifier("sales") == "sales"
        assert validate_schema_identifier("_private") == "_private"
        assert validate_schema_identifier("Schema1") == "Schema1"

    @pytest.mark.parametrize("value", ["", "1bad", "has-dash", "has space", "bad;drop"])
    def test_rejects_invalid_names(self, value: str) -> None:
        with pytest.raises(ValueError, match="Invalid schema name"):
            validate_schema_identifier(value)


class TestResolveOptionalSchema:
    def test_none_returns_none(self) -> None:
        assert resolve_optional_schema(None) is None

    @pytest.mark.parametrize("value", ["", "   ", "\t"])
    def test_blank_returns_none(self, value: str) -> None:
        assert resolve_optional_schema(value) is None

    def test_strips_and_returns_value(self) -> None:
        assert resolve_optional_schema("  sales  ") == "sales"


class TestValidateOptionalSchema:
    def test_empty_returns_none(self) -> None:
        assert validate_optional_schema("") is None
        assert validate_optional_schema(None) is None

    def test_validates_when_provided(self) -> None:
        assert validate_optional_schema("sales") == "sales"

    def test_invalid_raises(self) -> None:
        with pytest.raises(ValueError):
            validate_optional_schema("bad-name")


class TestQualifyTable:
    def test_without_schema_returns_table_only(self) -> None:
        assert qualify_table(None, "orders") == "orders"

    def test_with_schema_returns_qualified_name(self) -> None:
        assert qualify_table("sales", "orders") == "sales.orders"

    def test_invalid_schema_raises(self) -> None:
        with pytest.raises(ValueError):
            qualify_table("bad-name", "orders")


class TestReadConnectionSchema:
    def test_returns_explicit_schema(self) -> None:
        cursor = MagicMock()
        assert read_connection_schema(cursor, "sales") == "sales"
        cursor.execute.assert_not_called()

    def test_queries_current_schema_when_not_provided(self) -> None:
        cursor = MagicMock()
        cursor.fetchone.return_value = (POSTGRES_DEFAULT_SCHEMA,)
        assert read_connection_schema(cursor, None) == POSTGRES_DEFAULT_SCHEMA
        cursor.execute.assert_called_once_with("SELECT current_schema()")
