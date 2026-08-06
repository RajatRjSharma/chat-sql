"""Tests for SQL generator and summarizer (mocked AI client)."""

from __future__ import annotations

from unittest.mock import MagicMock

from app.services.result_summarizer import ResultSummarizer
from app.services.sql_generator import SqlGenerator


class TestSqlGenerator:
    def test_generate_extracts_sql(self) -> None:
        client = MagicMock()
        client.complete.return_value = "```sql\nSELECT 1 AS x\n```"
        sql = SqlGenerator.generate(
            question="test",
            schema_context="Table: sales.orders",
            schema_name="sales",
            source_metadata={
                "engine": "PostgreSQL",
                "db_type": "postgres",
                "sql_dialect": "postgres",
                "vendor": "PostgreSQL Global Development Group",
                "database": "bi_warehouse",
                "schema_name": "sales",
                "host": "localhost",
                "port": 5433,
                "is_readonly": True,
                "access_mode": "read_only_select",
                "identifier_quoting": "double_quote",
                "dialect_notes": "ok",
                "embedding_model": "embed",
                "embedding_dimensions": 8,
            },
            client=client,
        )
        assert sql == "SELECT 1 AS x"
        client.complete.assert_called_once()
        messages = client.complete.call_args[0][0]
        system_msg = messages[0]["content"]
        assert "foreign-key" in system_msg.lower() or "FK" in system_msg
        assert "revenue" in system_msg.lower()
        user_msg = messages[-1]["content"]
        assert "PostgreSQL" in user_msg
        assert "postgres" in user_msg

    def test_includes_prior_sql_and_empty_hint(self) -> None:
        client = MagicMock()
        client.complete.return_value = "SELECT 2"
        SqlGenerator.generate(
            question="revenue by region",
            schema_context="Table: sales.orders",
            previous_sql="SELECT 1",
            previous_error="zero rows",
            source_metadata={
                "engine": "PostgreSQL",
                "sql_dialect": "postgres",
                "prior_successful_sql": "SELECT amount FROM sales.orders",
            },
            client=client,
        )
        user_msg = client.complete.call_args[0][0][-1]["content"]
        assert "Prior successful SQL" in user_msg
        assert "Previous SQL failed" in user_msg
        assert "zero rows" in user_msg


class TestResultSummarizer:
    def test_summarize(self) -> None:
        client = MagicMock()
        client.complete.return_value = "East is highest."
        answer = ResultSummarizer.summarize(
            question="sales?",
            sql="SELECT 1",
            columns=["region"],
            rows=[{"region": "East"}],
            client=client,
        )
        assert answer == "East is highest."
