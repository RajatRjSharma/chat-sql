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
        with patch("app.graph.retry_policy.settings") as settings:
            settings.rag_expand_on_retry = True
            assert ChatService._needs_allowlist_expand(prepared, final) is True

    def test_false_when_ok(self) -> None:
        with patch("app.graph.retry_policy.settings") as settings:
            settings.rag_expand_on_retry = True
            assert (
                ChatService._needs_allowlist_expand(
                    {},
                    {"status": "ok", "sql_error": None},
                )
                is False
            )

    def test_unanswerable_analytics_triggers_expand(self) -> None:
        prepared = {
            "linked_chunks": [_chunk("orders")],
            "question": "Total revenue by region and channel",
            "context_mode": "rag",
        }
        final = {
            "scope": "out_of_scope",
            "attempts": 1,
            "status": "ok",
            "answer": "That question isn't something I can answer",
        }
        with patch("app.graph.retry_policy.settings") as settings:
            settings.rag_expand_on_retry = True
            assert ChatService._needs_unanswerable_expand(prepared, final) is True

    def test_unanswerable_skips_trivia(self) -> None:
        prepared = {
            "linked_chunks": [_chunk("orders")],
            "question": "height of Burj Khalifa",
            "context_mode": "rag",
        }
        final = {"scope": "out_of_scope", "attempts": 1, "status": "ok"}
        with patch("app.graph.retry_policy.settings") as settings:
            settings.rag_expand_on_retry = True
            assert ChatService._needs_unanswerable_expand(prepared, final) is False

    def test_false_when_already_expanded(self) -> None:
        with patch("app.graph.retry_policy.settings") as settings:
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
        with patch("app.graph.retry_policy.settings") as settings:
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


class TestPriorTurnTables:
    """Follow-ups must keep the tables the previous turn actually joined."""

    _PRIOR_SQL = (
        "SELECT SUM(il.amount) FROM sales.invoice_lines AS il "
        "JOIN sales.orders AS o ON il.invoice_id = o.order_id "
        "JOIN sales.channels AS c ON o.channel_id = c.channel_id"
    )

    @pytest.mark.asyncio
    async def test_reseeds_missing_prior_tables(self) -> None:
        seed_rows = [_chunk("orders")]
        with (
            patch(
                "app.graph.prep_nodes.RagService.fetch_chunks_by_tables",
                new=AsyncMock(return_value=[_chunk("invoice_lines"), _chunk("channels")]),
            ) as fetch,
            patch("app.graph.prep_nodes.settings") as settings,
        ):
            settings.rag_max_tables = 15
            out = await ChatService._with_prior_turn_tables(
                MagicMock(),
                data_source_id="ds",
                seed_rows=seed_rows,
                prior_sql=self._PRIOR_SQL,
            )
        assert fetch.await_count == 1
        assert {c.table for c in out} == {"orders", "invoice_lines", "channels"}

    @pytest.mark.asyncio
    async def test_no_prior_sql_is_passthrough(self) -> None:
        seed_rows = [_chunk("orders")]
        with patch(
            "app.graph.prep_nodes.RagService.fetch_chunks_by_tables",
            new=AsyncMock(return_value=[]),
        ) as fetch:
            out = await ChatService._with_prior_turn_tables(
                MagicMock(),
                data_source_id="ds",
                seed_rows=seed_rows,
                prior_sql=None,
            )
        fetch.assert_not_awaited()
        assert out == seed_rows

    @pytest.mark.asyncio
    async def test_skips_fetch_when_all_present(self) -> None:
        seed_rows = [_chunk("invoice_lines"), _chunk("orders"), _chunk("channels")]
        with patch(
            "app.graph.prep_nodes.RagService.fetch_chunks_by_tables",
            new=AsyncMock(return_value=[]),
        ) as fetch:
            out = await ChatService._with_prior_turn_tables(
                MagicMock(),
                data_source_id="ds",
                seed_rows=seed_rows,
                prior_sql=self._PRIOR_SQL,
            )
        fetch.assert_not_awaited()
        assert out == seed_rows


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
        patch("app.graph.retry_policy.settings") as settings,
        patch("app.graph.prep_nodes.settings") as prep_settings,
        patch(
            "app.graph.prep_nodes.RagService.fetch_chunks_by_tables",
            new=AsyncMock(return_value=[channels]),
        ),
        patch(
            "app.graph.prep_nodes.RagService.load_catalog",
            new=AsyncMock(return_value=[orders, channels]),
        ),
        patch(
            "app.graph.chat_graph.run_chat_graph",
            return_value=rebuilt_state,
        ),
        patch(
            "app.services.chat_service.build_source_metadata",
            return_value={"context_mode": "rag_expanded"},
        ),
        patch(
            "app.graph.prep_nodes.build_source_metadata",
            return_value={"context_mode": "rag_expanded"},
        ),
        patch(
            "app.graph.chat_graph.initial_chat_state",
            return_value={"attempts": 0},
        ),
        patch(
            "app.services.chat_service.initial_chat_state",
            return_value={"attempts": 0},
        ),
        patch(
            "app.services.chat_service.build_chat_graph",
            return_value=MagicMock(),
        ),
        patch(
            "app.graph.chat_graph.build_chat_graph",
            return_value=MagicMock(),
        ),
    ):
        settings.rag_expand_on_retry = True
        settings.rag_expand_hops = 1
        settings.rag_max_tables = 15
        settings.sql_max_attempts = 3
        prep_settings.rag_expand_on_retry = True
        prep_settings.rag_expand_hops = 1
        prep_settings.rag_max_tables = 15

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


class TestNeedsEmptyResultRetry:
    def test_true_on_empty_analytics_result(self) -> None:
        prepared = {"question": "total revenue by region and channel"}
        final = {
            "status": "ok",
            "sql": "SELECT 1",
            "rows": [],
            "scope": "answerable",
        }
        assert ChatService._needs_empty_result_retry(prepared, final) is True

    def test_false_when_rows_present(self) -> None:
        prepared = {"question": "total revenue by region"}
        final = {
            "status": "ok",
            "sql": "SELECT 1",
            "rows": [{"x": 1}],
            "scope": "answerable",
        }
        assert ChatService._needs_empty_result_retry(prepared, final) is False

    def test_false_when_already_retried(self) -> None:
        prepared = {
            "question": "total revenue by region",
            "_empty_sql_retry": True,
        }
        final = {"status": "ok", "sql": "SELECT 1", "rows": [], "scope": "answerable"}
        assert ChatService._needs_empty_result_retry(prepared, final) is False

    def test_false_for_trivia(self) -> None:
        prepared = {"question": "what is the weather in Delhi"}
        final = {"status": "ok", "sql": "SELECT 1", "rows": [], "scope": "answerable"}
        assert ChatService._needs_empty_result_retry(prepared, final) is False


@pytest.mark.asyncio
async def test_maybe_empty_result_retry_reruns_graph() -> None:
    graph = MagicMock()
    prepared = {
        "question": "total revenue by region and channel",
        "graph": graph,
        "state": {
            "question": "total revenue by region and channel",
            "attempts": 0,
        },
    }
    final = {
        "status": "ok",
        "sql": "SELECT bad_join",
        "rows": [],
        "attempts": 1,
        "scope": "answerable",
    }
    with patch(
        "app.graph.chat_graph.run_chat_graph",
        return_value={
            "status": "ok",
            "sql": "SELECT fixed",
            "rows": [{"region": "North", "revenue": 10}],
            "attempts": 2,
        },
    ) as run_mock:
        out_prepared, out_final = await ChatService._maybe_empty_result_retry(
            prepared=prepared,
            final=final,
        )

    assert out_prepared.get("_empty_sql_retry") is True
    assert out_final["rows"] == [{"region": "North", "revenue": 10}]
    assert out_final["attempts"] == 3
    call_state = run_mock.call_args[0][1]
    assert call_state["sql"] == "SELECT bad_join"
    assert "ZERO rows" in (call_state.get("sql_error") or "")


@pytest.mark.asyncio
async def test_maybe_empty_result_retry_keeps_first_when_retry_worse() -> None:
    prepared = {
        "question": "total revenue by region",
        "graph": MagicMock(),
        "state": {"question": "total revenue by region", "attempts": 0},
    }
    final = {
        "status": "ok",
        "sql": "SELECT empty",
        "rows": [],
        "answer": "no matching rows",
        "attempts": 1,
        "scope": "answerable",
    }
    with patch(
        "app.graph.chat_graph.run_chat_graph",
        return_value={
            "status": "failed",
            "sql": "SELECT worse",
            "rows": None,
            "answer": "could not complete",
            "attempts": 3,
        },
    ):
        out_prepared, out_final = await ChatService._maybe_empty_result_retry(
            prepared=prepared,
            final=final,
        )

    assert out_prepared.get("_empty_sql_retry") is True
    assert out_final["status"] == "ok"
    assert out_final["rows"] == []
    assert out_final["answer"] == "no matching rows"
    assert out_final["attempts"] == 4


class TestEmptyRetryImproves:
    def test_rows_win(self) -> None:
        assert (
            ChatService._empty_retry_improves(
                {"status": "ok", "rows": []},
                {"status": "ok", "rows": [{"a": 1}]},
            )
            is True
        )

    def test_failed_does_not_win(self) -> None:
        assert (
            ChatService._empty_retry_improves(
                {"status": "ok", "rows": []},
                {"status": "failed", "rows": [{"a": 1}]},
            )
            is False
        )

    def test_still_empty_does_not_win(self) -> None:
        assert (
            ChatService._empty_retry_improves(
                {"status": "ok", "rows": []},
                {"status": "ok", "rows": []},
            )
            is False
        )
