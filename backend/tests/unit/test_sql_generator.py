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
            client=client,
        )
        assert sql == "SELECT 1 AS x"
        client.complete.assert_called_once()


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
