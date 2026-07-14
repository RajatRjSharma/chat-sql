"""Unit tests for schema-aware suggested questions."""

from __future__ import annotations

from app.services.suggestion_service import (
    build_questions_from_tables,
    parse_schema_chunk,
)


SAMPLE_CHUNK = """
Table: sales.orders
Columns:
  - order_id: integer
  - region: text
  - amount: numeric
  - category: varchar
"""


class TestParseSchemaChunk:
    def test_parses_table_and_columns(self) -> None:
        parsed = parse_schema_chunk(SAMPLE_CHUNK)
        assert parsed is not None
        assert parsed["table"] == "orders"
        names = {c["name"] for c in parsed["columns"]}
        assert names == {"order_id", "region", "amount", "category"}

    def test_returns_none_without_table_line(self) -> None:
        assert parse_schema_chunk("- amount: numeric") is None


class TestBuildQuestionsFromTables:
    def test_builds_metric_by_dimension(self) -> None:
        tables = [parse_schema_chunk(SAMPLE_CHUNK)]
        assert tables[0] is not None
        questions = build_questions_from_tables(tables, limit=6)
        texts = [q["question"] for q in questions]
        assert any("orders" in t.lower() for t in texts)
        assert any("amount" in t.lower() and "region" in t.lower() for t in texts)
        assert all(q["source"] in ("schema", "history", "fallback") for q in questions)

    def test_prefers_history_titles(self) -> None:
        tables = [parse_schema_chunk(SAMPLE_CHUNK)]
        assert tables[0] is not None
        questions = build_questions_from_tables(
            tables,
            history_titles=["What were total sales by region?"],
            limit=4,
        )
        assert questions[0]["source"] == "history"
        assert "sales by region" in questions[0]["question"].lower()

    def test_fallback_when_no_tables(self) -> None:
        questions = build_questions_from_tables([], limit=4)
        assert len(questions) >= 1
        assert all(q["source"] == "fallback" for q in questions)

    def test_respects_limit_and_dedupes(self) -> None:
        tables = [parse_schema_chunk(SAMPLE_CHUNK)]
        assert tables[0] is not None
        questions = build_questions_from_tables(
            tables,
            history_titles=[
                "Give me a quick summary of the orders table.",
                "Give me a quick summary of the orders table.",
            ],
            limit=3,
        )
        assert len(questions) <= 3
        normalized = [" ".join(q["question"].lower().split()) for q in questions]
        assert len(normalized) == len(set(normalized))
