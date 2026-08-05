"""Tests for ChatService allowlist expand-on-retry helpers."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.chat_service import ChatService
from app.services.schema_linker import SchemaChunk


def _chunk(table: str) -> SchemaChunk:
    return SchemaChunk(
        content=f"Table: sales.{table}\nColumns:\n  - id: integer",
        table=table,
        schema_name="sales",
        metadata={"table": table, "schema": "sales"},
    )


class TestNeedsAllowlistExpand:
    def test_true_on_failed_allowlist_error(self) -> None:
        prepared = {}
        final = {
            "status": "failed",
            "sql_error": "Table 'channels' is not in the allowed table set.",
        }
        with patch("app.services.chat_service.settings") as settings:
            settings.rag_expand_on_retry = True
            assert ChatService._needs_allowlist_expand(prepared, final) is True

    def test_false_when_ok(self) -> None:
        with patch("app.services.chat_service.settings") as settings:
            settings.rag_expand_on_retry = True
            assert (
                ChatService._needs_allowlist_expand(
                    {},
                    {"status": "ok", "sql_error": None},
                )
                is False
            )

    def test_false_when_already_expanded(self) -> None:
        with patch("app.services.chat_service.settings") as settings:
            settings.rag_expand_on_retry = True
            assert (
                ChatService._needs_allowlist_expand(
                    {"_expanded_retry": True},
                    {
                        "status": "failed",
                        "sql_error": "Table 'channels' is not in the allowed table set.",
                    },
                )
                is False
            )

    def test_reads_miss_from_answer(self) -> None:
        with patch("app.services.chat_service.settings") as settings:
            settings.rag_expand_on_retry = True
            assert (
                ChatService._needs_allowlist_expand(
                    {},
                    {
                        "status": "failed",
                        "sql_error": None,
                        "answer": "Failed (Table 'channels' is not in the allowed table set.)",
                    },
                )
                is True
            )


@pytest.mark.asyncio
async def test_maybe_expand_and_retry_rebuilds_once() -> None:
    orders = _chunk("orders")
    channels = _chunk("channels")
    prepared = {
        "ai": MagicMock(),
        "data_source": MagicMock(),
        "data_source_id": "ds",
        "question": "by channel",
        "chat_session": MagicMock(),
        "history": [],
        "info": MagicMock(schema_name="sales", connection_url="postgresql://x"),
        "linked_chunks": [orders],
        "source_metadata": {},
        "context_mode": "rag",
    }
    final = {
        "status": "failed",
        "sql_error": "Table 'channels' is not in the allowed table set.",
        "attempts": 3,
    }

    rebuilt_state = {"status": "ok", "attempts": 1, "answer": "ok", "sql": "SELECT 1"}

    with (
        patch("app.services.chat_service.settings") as settings,
        patch(
            "app.services.chat_service.RagService.fetch_chunks_by_tables",
            new=AsyncMock(return_value=[channels]),
        ),
        patch(
            "app.services.chat_service.RagService.load_catalog",
            new=AsyncMock(return_value=[orders, channels]),
        ),
        patch(
            "app.services.chat_service.run_chat_graph",
            return_value=rebuilt_state,
        ),
        patch(
            "app.services.chat_service.build_source_metadata",
            return_value={"context_mode": "rag_expanded"},
        ),
        patch(
            "app.services.chat_service.initial_chat_state",
            return_value={"attempts": 0},
        ),
        patch(
            "app.services.chat_service.build_chat_graph",
            return_value=MagicMock(),
        ),
    ):
        settings.rag_expand_on_retry = True
        settings.rag_expand_hops = 1
        settings.rag_max_tables = 15
        settings.sql_max_attempts = 3

        out_prepared, out_final = await ChatService._maybe_expand_and_retry(
            MagicMock(),
            prepared=prepared,
            final=final,
        )

    assert out_prepared.get("_expanded_retry") is True
    assert out_final["status"] == "ok"
    assert out_final["attempts"] == 4
    tables = {c.table for c in out_prepared["linked_chunks"]}
    assert "channels" in tables
    assert "orders" in tables
