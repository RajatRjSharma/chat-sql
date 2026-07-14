"""Tests for SQL extraction and validation."""

from __future__ import annotations

import pytest

from app.core.exceptions import SqlValidationError
from app.services.sql_validator import SqlValidator, extract_sql


class TestExtractSql:
    def test_plain_sql(self) -> None:
        assert extract_sql("SELECT 1") == "SELECT 1"

    def test_markdown_fence(self) -> None:
        raw = "```sql\nSELECT * FROM sales.orders\n```"
        assert extract_sql(raw) == "SELECT * FROM sales.orders"

    def test_strips_trailing_semicolon(self) -> None:
        assert extract_sql("SELECT 1;") == "SELECT 1"


class TestSqlValidator:
    def test_accepts_select(self) -> None:
        sql = SqlValidator.validate(
            "SELECT region, SUM(amount) FROM sales.orders GROUP BY region",
            allowed_schema="sales",
            allowed_tables={"orders"},
        )
        assert "SELECT" in sql.upper()

    def test_rejects_insert(self) -> None:
        with pytest.raises(SqlValidationError, match="Only SELECT"):
            SqlValidator.validate("INSERT INTO sales.orders (amount) VALUES (1)")

    def test_rejects_drop(self) -> None:
        with pytest.raises(SqlValidationError):
            SqlValidator.validate("DROP TABLE sales.orders")

    def test_rejects_multiple_statements(self) -> None:
        with pytest.raises(SqlValidationError, match="single"):
            SqlValidator.validate("SELECT 1; SELECT 2")

    def test_rejects_wrong_schema(self) -> None:
        with pytest.raises(SqlValidationError, match="outside allowed schema"):
            SqlValidator.validate(
                "SELECT * FROM public.orders",
                allowed_schema="sales",
                allowed_tables={"orders"},
            )

    def test_rejects_unknown_table(self) -> None:
        with pytest.raises(SqlValidationError, match="not in the allowed"):
            SqlValidator.validate(
                "SELECT * FROM sales.secrets",
                allowed_schema="sales",
                allowed_tables={"orders", "customers"},
            )

    def test_rejects_empty(self) -> None:
        with pytest.raises(SqlValidationError, match="Empty"):
            SqlValidator.validate("   ")

    def test_token_error_becomes_validation_error(self) -> None:
        """Broken quote fragments must retry via SqlValidationError, not crash."""
        with pytest.raises(SqlValidationError, match="not valid for dialect"):
            SqlValidator.validate(
                "'(WHERE status='completed')::text FROM sales.order"
            )

    def test_accepts_filter_where_clause(self) -> None:
        sql = SqlValidator.validate(
            "SELECT COUNT(*) FILTER (WHERE status = 'completed') AS done "
            "FROM sales.orders",
            allowed_schema="sales",
            allowed_tables={"orders"},
        )
        assert "FILTER" in sql.upper()

    def test_accepts_union(self) -> None:
        sql = SqlValidator.validate(
            "SELECT 1 AS x UNION SELECT 2 AS x",
            allowed_schema=None,
            allowed_tables=None,
        )
        assert "UNION" in sql.upper()
