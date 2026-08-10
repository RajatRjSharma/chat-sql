"""End-to-end expand-on-retry: UNANSWERABLE analytics asks recover with deeper linking."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.chat_service import ChatService
from app.services.scope_guard import OUT_OF_SCOPE_MESSAGE
from tests.eval.catalog_fixture import build_eval_catalog, build_table_chunk
from tests.eval.golden_cases import GOLDEN_CASES


@pytest.mark.asyncio
async def test_unanswerable_revenue_ask_expands_customers() -> None:
    """Simulate thin first pass (orders+channels only) then UNANSWERABLE → retry."""
    case = next(c for c in GOLDEN_CASES if c.id == "revenue_by_region_channel")
    catalog = build_eval_catalog(include_synthetic=False)
    thin = [
        build_table_chunk("orders"),
        build_table_chunk("channels"),
        build_table_chunk("regions"),
    ]
    # First pass deliberately missing customers (the production failure mode).
    assert "customers" not in {c.table for c in thin}

    prepared = {
        "ai": MagicMock(),
        "data_source": MagicMock(),
        "data_source_id": "ds",
        "question": case.question,
        "chat_session": MagicMock(),
        "history": [],
        "info": MagicMock(schema_name="sales", connection_url="postgresql://x"),
        "linked_chunks": thin,
        "source_metadata": {},
        "context_mode": "rag_mentioned",
    }
    final = {
        "scope": "out_of_scope",
        "status": "ok",
        "attempts": 1,
        "answer": OUT_OF_SCOPE_MESSAGE,
        "sql": None,
    }

    rebuilt_state = {
        "status": "ok",
        "scope": "answerable",
        "attempts": 1,
        "answer": "East web leads.",
        "sql": "SELECT 1",
        "columns": ["region", "channel", "revenue"],
        "rows": [{"region": "East", "channel": "web", "revenue": 10}],
    }

    with (
        patch("app.graph.retry_policy.settings") as settings,
        patch("app.graph.prep_nodes.settings") as prep_settings,
        patch(
            "app.graph.prep_nodes.RagService.load_catalog",
            new=AsyncMock(return_value=catalog),
        ),
        patch(
            "app.graph.chat_graph.run_chat_graph",
            return_value=rebuilt_state,
        ),
        patch(
            "app.graph.prep_nodes.build_source_metadata",
            return_value={"context_mode": "rag_expanded"},
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
            "app.graph.chat_graph.initial_chat_state",
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

        assert ChatService._needs_unanswerable_expand(prepared, final) is True
        out_prepared, out_final = await ChatService._maybe_expand_and_retry(
            MagicMock(),
            prepared=prepared,
            final=final,
        )

    assert out_prepared.get("_expanded_retry") is True
    tables = {c.table for c in out_prepared["linked_chunks"]}
    assert "customers" in tables, f"retry must add customers, got {sorted(tables)}"
    assert "orders" in tables
    assert "channels" in tables
    assert out_final["status"] == "ok"
    assert out_final["attempts"] == 2


@pytest.mark.asyncio
async def test_trivia_unanswerable_does_not_expand() -> None:
    prepared = {
        "linked_chunks": [build_table_chunk("orders")],
        "question": "What is the height of the Burj Khalifa?",
        "context_mode": "rag",
    }
    final = {
        "scope": "out_of_scope",
        "attempts": 1,
        "status": "ok",
        "answer": OUT_OF_SCOPE_MESSAGE,
    }
    with patch("app.graph.retry_policy.settings") as settings:
        settings.rag_expand_on_retry = True
        assert ChatService._needs_unanswerable_expand(prepared, final) is False
