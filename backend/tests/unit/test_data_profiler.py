"""Unit tests for warehouse data profiling + LLM formatting."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.services.data_profiler import (
    DataProfiler,
    build_profile_document,
    format_data_profile_for_llm,
    profile_for_tables_in_context,
    table_profile_lookup,
)
from app.services.schema_chunker import chunk_table
from app.services.schema_introspection import ColumnInfo, ForeignKeyInfo, TableInfo
from app.services.source_metadata import build_source_metadata, format_metadata_for_llm
from app.services.sql_generator import EMPTY_RESULT_SQL_HINT, SqlGenerator


def _orders_table() -> TableInfo:
    return TableInfo(
        schema_name="sales",
        table_name="orders",
        columns=[
            ColumnInfo("order_id", "integer", False, True),
            ColumnInfo("amount", "numeric", False),
            ColumnInfo("order_date", "date", False),
            ColumnInfo("status", "text", True),
        ],
        foreign_keys=[
            ForeignKeyInfo("customer_id", "customers", "customer_id"),
        ],
    )


class TestFormatDataProfile:
    def test_empty_profile_message(self) -> None:
        text = format_data_profile_for_llm(None)
        assert "not yet indexed" in text.lower()

    def test_includes_temporal_guidance(self) -> None:
        profile = build_profile_document(
            clock={"current_date": "2026-08-07", "now": "2026-08-07T01:00:00+00:00"},
            tables=[
                {
                    "schema": "sales",
                    "table": "orders",
                    "qualified_name": "sales.orders",
                    "row_count": 100,
                    "temporal_columns": [
                        {
                            "name": "order_date",
                            "data_type": "date",
                            "min": "2024-01-01",
                            "max": "2025-06-23",
                        }
                    ],
                    "numeric_columns": [
                        {
                            "name": "amount",
                            "data_type": "numeric",
                            "min": 10,
                            "max": 500,
                            "avg": 120.5,
                        }
                    ],
                    "categorical_columns": [
                        {
                            "name": "status",
                            "distinct_count": 3,
                            "top_values": [
                                {"value": "completed", "count": 80},
                                {"value": "open", "count": 20},
                            ],
                        }
                    ],
                    "foreign_keys": [],
                }
            ],
        )
        text = format_data_profile_for_llm(profile)
        assert "2024-01-01 .. 2025-06-23" in text
        assert "NOT wall-clock" in text or "not wall-clock" in text.lower()
        assert "amount" in text
        assert "completed" in text


class TestProfileFilter:
    def test_filters_to_context_tables(self) -> None:
        full = {
            "version": 1,
            "tables": [
                {"table": "orders", "qualified_name": "sales.orders", "row_count": 10},
                {"table": "tickets", "qualified_name": "sales.tickets", "row_count": 5},
            ],
            "temporal_windows": [
                {"table": "sales.orders", "column": "order_date", "min": "a", "max": "b"},
                {"table": "sales.tickets", "column": "created_at", "min": "c", "max": "d"},
            ],
            "table_count": 2,
            "approx_total_rows": 15,
        }
        filtered = profile_for_tables_in_context(full, ["orders"])
        assert filtered is not None
        assert filtered["table_count"] == 1
        assert filtered["tables"][0]["table"] == "orders"
        assert len(filtered["temporal_windows"]) == 1
        assert filtered["approx_total_rows"] == 10


class TestSourceMetadataIncludesProfile:
    def test_build_and_format_include_profile(self) -> None:
        profile = {
            "version": 1,
            "profiled_at": "2026-08-07T00:00:00+00:00",
            "warehouse_clock": {"current_date": "2026-08-07", "now": "x"},
            "table_count": 1,
            "approx_total_rows": 100,
            "temporal_windows": [
                {
                    "table": "sales.orders",
                    "column": "order_date",
                    "min": "2024-01-01",
                    "max": "2025-06-01",
                }
            ],
            "tables": [
                {
                    "table": "orders",
                    "qualified_name": "sales.orders",
                    "row_count": 100,
                    "temporal_columns": [
                        {
                            "name": "order_date",
                            "min": "2024-01-01",
                            "max": "2025-06-01",
                        }
                    ],
                    "numeric_columns": [],
                    "categorical_columns": [],
                }
            ],
        }
        source = SimpleNamespace(
            id=uuid.uuid4(),
            name="Demo",
            db_type="postgres",
            host="localhost",
            port=5433,
            database="bi_warehouse",
            schema_name="sales",
            is_readonly=True,
            extra_config={
                "schema_indexed_at": "2026-08-07T00:00:00+00:00",
                "schema_table_count": 50,
                "schema_chunk_count": 52,
                "data_profile": profile,
            },
        )
        meta = build_source_metadata(
            source,  # type: ignore[arg-type]
            tables_in_context=["orders"],
            context_mode="rag",
        )
        assert meta["data_profile"] is not None
        assert meta["data_profile"]["table_count"] == 1
        text = format_metadata_for_llm(meta)
        assert "Data profile" in text
        assert "order_date" in text
        assert "Schema indexed at" in text


class TestChunkIncludesProfile:
    def test_chunk_table_adds_observed_profile(self) -> None:
        text = chunk_table(
            _orders_table(),
            table_profile={
                "row_count": 42,
                "temporal_columns": [
                    {"name": "order_date", "min": "2024-01-01", "max": "2025-01-01"}
                ],
                "numeric_columns": [
                    {"name": "amount", "min": 1, "max": 99, "avg": 40}
                ],
                "categorical_columns": [
                    {
                        "name": "status",
                        "distinct_count": 2,
                        "top_values": [{"value": "open", "count": 10}],
                    }
                ],
            },
        )
        assert "Observed data profile" in text
        assert "row_count: 42" in text
        assert "order_date window" in text


class TestSqlPromptRules:
    def test_system_prompt_mentions_data_profile_windows(self) -> None:
        from app.services import sql_generator as mod

        assert "Data profile" in mod._SYSTEM_PROMPT
        assert "CURRENT_DATE" in EMPTY_RESULT_SQL_HINT


class TestDataProfilerAggregates:
    def test_profile_table_builds_stats(self) -> None:
        profiler = DataProfiler()
        conn = MagicMock()
        cur = MagicMock()
        conn.cursor.return_value.__enter__.return_value = cur
        # aggregates: count, min date, max date, min amt, max amt, avg amt
        cur.fetchone.side_effect = [
            (100, "2024-01-01", "2025-06-01", 10, 500, 120.0),
            (3,),  # distinct status
        ]
        cur.fetchall.return_value = [("completed", 80), ("open", 20)]

        out = profiler._profile_table(conn, _orders_table())
        assert out["row_count"] == 100
        assert out["temporal_columns"][0]["name"] == "order_date"
        assert out["numeric_columns"][0]["name"] == "amount"
        assert out["categorical_columns"][0]["name"] == "status"
        assert table_profile_lookup({"tables": [out]})["orders"]["row_count"] == 100


class TestGenerateIncludesProfileBlock:
    def test_user_message_contains_profile(self) -> None:
        client = MagicMock()
        client.complete.return_value = "SELECT 1"
        profile = {
            "version": 1,
            "profiled_at": "t",
            "warehouse_clock": {"current_date": "2026-08-07", "now": "n"},
            "table_count": 1,
            "approx_total_rows": 1,
            "temporal_windows": [
                {
                    "table": "sales.orders",
                    "column": "order_date",
                    "min": "2024-01-01",
                    "max": "2025-06-01",
                }
            ],
            "tables": [],
        }
        SqlGenerator.generate(
            question="Monthly revenue last 12 months",
            schema_context="Table: sales.orders",
            schema_name="sales",
            source_metadata={
                "engine": "PostgreSQL",
                "db_type": "postgres",
                "sql_dialect": "postgres",
                "database": "bi",
                "schema_name": "sales",
                "host": "localhost",
                "port": 5432,
                "is_readonly": True,
                "access_mode": "read_only_select",
                "identifier_quoting": "double_quote",
                "dialect_notes": "ok",
                "embedding_model": "e",
                "embedding_dimensions": 8,
                "data_profile": profile,
            },
            client=client,
        )
        messages = client.complete.call_args[0][0]
        user = next(m for m in messages if m["role"] == "user")
        assert "Data profile" in user["content"]
        assert "2024-01-01 .. 2025-06-01" in user["content"]
        system = next(m for m in messages if m["role"] == "system")
        assert "last N" in system["content"]
