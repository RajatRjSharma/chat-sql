"""API tests for chat and embed-schema routes."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.core.exceptions import (
    AIProviderError,
    ChatPipelineError,
    SchemaEmbeddingError,
    SchemaIndexInProgressError,
)
from app.services.schema_embedding_service import SchemaEmbedResult
from tests.conftest import DEMO_SOURCE_ID


def _embed_result(*, chunks: int = 3, tables: int = 3, previous: int = 0) -> SchemaEmbedResult:
    return SchemaEmbedResult(
        chunks_embedded=chunks,
        tables_indexed=tables,
        previous_chunks=previous,
        indexed_at=datetime(2026, 8, 5, 12, 0, tzinfo=UTC),
    )


class TestEmbedSchemaRoute:
    @pytest.fixture(autouse=True)
    def _clear_embed_rate_buckets(self) -> None:
        from app.security.rate_limit import _limiter

        _limiter._hits.clear()

    def test_embed_schema_success(self, client: TestClient) -> None:
        with patch(
            "app.routes.data.SchemaEmbeddingService.embed_data_source",
            new=AsyncMock(return_value=_embed_result(chunks=3, tables=3, previous=1)),
        ):
            response = client.post(
                "/api/data/embed-schema",
                json={"data_source_id": str(DEMO_SOURCE_ID)},
            )
        assert response.status_code == 200
        body = response.json()
        assert body["chunks_embedded"] == 3
        assert body["tables_indexed"] == 3
        assert body["previous_chunks"] == 1
        assert body["indexed_at"] is not None
        assert body["status"] == "ok"

    def test_embed_schema_not_found_returns_404(self, client: TestClient) -> None:
        with patch(
            "app.routes.data.SchemaEmbeddingService.embed_data_source",
            new=AsyncMock(side_effect=ValueError("Data source not found")),
        ):
            response = client.post(
                "/api/data/embed-schema",
                json={"data_source_id": str(uuid.uuid4())},
            )
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_embed_schema_in_progress_returns_409(self, client: TestClient) -> None:
        with patch(
            "app.routes.data.SchemaEmbeddingService.embed_data_source",
            new=AsyncMock(
                side_effect=SchemaIndexInProgressError(
                    "Schema index rebuild already in progress for this data source."
                )
            ),
        ):
            response = client.post(
                "/api/data/embed-schema",
                json={"data_source_id": str(DEMO_SOURCE_ID)},
            )
        assert response.status_code == 409
        assert "already in progress" in response.json()["detail"].lower()

    def test_embed_schema_ai_error_returns_502(self, client: TestClient) -> None:
        with patch(
            "app.routes.data.SchemaEmbeddingService.embed_data_source",
            new=AsyncMock(side_effect=AIProviderError("rate limited")),
        ):
            response = client.post(
                "/api/data/embed-schema",
                json={"data_source_id": str(DEMO_SOURCE_ID)},
            )
        assert response.status_code == 502
        assert "rate limited" in response.json()["detail"]

    def test_embed_schema_embedding_error_returns_502(self, client: TestClient) -> None:
        with patch(
            "app.routes.data.SchemaEmbeddingService.embed_data_source",
            new=AsyncMock(side_effect=SchemaEmbeddingError("no tables")),
        ):
            response = client.post(
                "/api/data/embed-schema",
                json={"data_source_id": str(DEMO_SOURCE_ID)},
            )
        assert response.status_code == 502
        assert response.json()["detail"] == "no tables"

    def test_embed_schema_unexpected_error_returns_502(self, client: TestClient) -> None:
        with patch(
            "app.routes.data.SchemaEmbeddingService.embed_data_source",
            new=AsyncMock(side_effect=RuntimeError("boom")),
        ):
            response = client.post(
                "/api/data/embed-schema",
                json={"data_source_id": str(DEMO_SOURCE_ID)},
            )
        assert response.status_code == 502
        assert response.json()["detail"] == "Schema embedding failed. Please try again."
        assert "boom" not in response.json()["detail"]

    def test_embed_schema_validation_error_returns_422(self, client: TestClient) -> None:
        response = client.post("/api/data/embed-schema", json={})
        assert response.status_code == 422


class TestChatRoute:
    def test_chat_success(self, client: TestClient) -> None:
        session_id = uuid.uuid4()
        payload = {
            "session_id": session_id,
            "data_source_id": DEMO_SOURCE_ID,
            "question": "sales by region",
            "answer": "East leads.",
            "sql": "SELECT 1",
            "columns": ["region"],
            "rows": [{"region": "East"}],
            "status": "ok",
            "attempts": 1,
        }
        with patch(
            "app.routes.chat.ChatService.ask",
            new=AsyncMock(return_value=payload),
        ):
            response = client.post(
                "/api/chat",
                json={
                    "data_source_id": str(DEMO_SOURCE_ID),
                    "question": "sales by region",
                },
            )
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok"
        assert body["answer"] == "East leads."
        assert body["sql"] == "SELECT 1"

    def test_chat_pipeline_failed_status_still_200(self, client: TestClient) -> None:
        """Business failure after retries is a completed response, not an HTTP error."""
        payload = {
            "session_id": uuid.uuid4(),
            "data_source_id": DEMO_SOURCE_ID,
            "question": "unclear",
            "answer": "I couldn't answer that safely.",
            "sql": None,
            "columns": [],
            "rows": [],
            "status": "failed",
            "attempts": 3,
        }
        with patch(
            "app.routes.chat.ChatService.ask",
            new=AsyncMock(return_value=payload),
        ):
            response = client.post(
                "/api/chat",
                json={
                    "data_source_id": str(DEMO_SOURCE_ID),
                    "question": "unclear",
                },
            )
        assert response.status_code == 200
        assert response.json()["status"] == "failed"

    def test_chat_not_found_returns_404(self, client: TestClient) -> None:
        with patch(
            "app.routes.chat.ChatService.ask",
            new=AsyncMock(side_effect=ValueError("Data source not found")),
        ):
            response = client.post(
                "/api/chat",
                json={
                    "data_source_id": str(uuid.uuid4()),
                    "question": "hello",
                },
            )
        assert response.status_code == 404

    def test_chat_ai_error_returns_502(self, client: TestClient) -> None:
        with patch(
            "app.routes.chat.ChatService.ask",
            new=AsyncMock(side_effect=AIProviderError("429 rate limited")),
        ):
            response = client.post(
                "/api/chat",
                json={
                    "data_source_id": str(DEMO_SOURCE_ID),
                    "question": "sales?",
                },
            )
        assert response.status_code == 502
        detail = response.json()["detail"]
        assert detail == "AI provider is temporarily unavailable. Please try again shortly."
        assert "429" not in detail

    def test_chat_pipeline_error_returns_502(self, client: TestClient) -> None:
        with patch(
            "app.routes.chat.ChatService.ask",
            new=AsyncMock(side_effect=ChatPipelineError("graph failed")),
        ):
            response = client.post(
                "/api/chat",
                json={
                    "data_source_id": str(DEMO_SOURCE_ID),
                    "question": "sales?",
                },
            )
        assert response.status_code == 502
        assert response.json()["detail"] == "graph failed"

    def test_chat_schema_embedding_error_returns_502(self, client: TestClient) -> None:
        with patch(
            "app.routes.chat.ChatService.ask",
            new=AsyncMock(side_effect=SchemaEmbeddingError("embed failed")),
        ):
            response = client.post(
                "/api/chat",
                json={
                    "data_source_id": str(DEMO_SOURCE_ID),
                    "question": "sales?",
                },
            )
        assert response.status_code == 502

    def test_chat_unexpected_error_returns_500(self, client: TestClient) -> None:
        with patch(
            "app.routes.chat.ChatService.ask",
            new=AsyncMock(side_effect=RuntimeError("boom")),
        ):
            response = client.post(
                "/api/chat",
                json={
                    "data_source_id": str(DEMO_SOURCE_ID),
                    "question": "sales?",
                },
            )
        assert response.status_code == 500
        assert response.json()["detail"] == "Chat failed. Please try again."
        assert "boom" not in response.json()["detail"]

    def test_chat_validation_error_returns_422(self, client: TestClient) -> None:
        response = client.post(
            "/api/chat",
            json={"data_source_id": str(DEMO_SOURCE_ID), "question": ""},
        )
        assert response.status_code == 422


class TestChatSessionRoute:
    def test_list_sessions_success(self, client: TestClient) -> None:
        session_id = uuid.uuid4()
        rows = [
            {
                "session_id": session_id,
                "data_source_id": DEMO_SOURCE_ID,
                "title": "sales by region",
                "created_at": "2026-07-14T00:00:00Z",
                "updated_at": "2026-07-14T01:00:00Z",
                "message_count": 2,
            }
        ]
        with patch(
            "app.routes.chat.ChatService.list_sessions",
            new=AsyncMock(return_value=rows),
        ):
            response = client.get(
                "/api/chat/sessions",
                params={"data_source_id": str(DEMO_SOURCE_ID)},
            )

        assert response.status_code == 200
        body = response.json()
        assert len(body) == 1
        assert body[0]["session_id"] == str(session_id)
        assert body[0]["title"] == "sales by region"
        assert body[0]["message_count"] == 2

    def test_list_sessions_missing_data_source_returns_422(self, client: TestClient) -> None:
        response = client.get("/api/chat/sessions")
        assert response.status_code == 422

    def test_list_sessions_not_found_returns_404(self, client: TestClient) -> None:
        with patch(
            "app.routes.chat.ChatService.list_sessions",
            new=AsyncMock(side_effect=ValueError("Data source not found")),
        ):
            response = client.get(
                "/api/chat/sessions",
                params={"data_source_id": str(uuid.uuid4())},
            )
        assert response.status_code == 404

    def test_get_session_success(self, client: TestClient) -> None:
        session_id = uuid.uuid4()
        payload = {
            "session_id": session_id,
            "data_source_id": DEMO_SOURCE_ID,
            "title": "sales?",
            "created_at": "2026-07-14T00:00:00Z",
            "updated_at": "2026-07-14T01:00:00Z",
            "messages": [
                {"role": "user", "content": "sales?"},
                {"role": "assistant", "content": "East leads."},
            ],
            "turns": [
                {
                    "question": "sales?",
                    "answer": "East leads.",
                    "sql": "SELECT region, SUM(amount) FROM sales.orders GROUP BY 1",
                    "columns": ["region", "sum"],
                    "rows": [{"region": "East", "sum": 100}],
                    "status": "ok",
                    "attempts": 0,
                }
            ],
        }

        with patch(
            "app.routes.chat.ChatService.get_session_detail",
            new=AsyncMock(return_value=payload),
        ):
            response = client.get(f"/api/chat/sessions/{session_id}")

        assert response.status_code == 200
        body = response.json()
        assert body["session_id"] == str(session_id)
        assert len(body["messages"]) == 2
        assert body["messages"][0]["role"] == "user"
        assert len(body["turns"]) == 1
        assert body["turns"][0]["sql"] is not None
        assert body["turns"][0]["rows"][0]["region"] == "East"

    def test_get_session_not_found_returns_404(self, client: TestClient) -> None:
        missing = uuid.uuid4()
        with patch(
            "app.routes.chat.ChatService.get_session_detail",
            new=AsyncMock(side_effect=ValueError("Session not found")),
        ):
            response = client.get(f"/api/chat/sessions/{missing}")
        assert response.status_code == 404
        assert response.json()["detail"] == "Session not found"

    def test_get_session_invalid_uuid_returns_422(self, client: TestClient) -> None:
        response = client.get("/api/chat/sessions/not-a-uuid")
        assert response.status_code == 422


class TestChatStreamRoute:
    def test_chat_stream_emits_stage_and_result(self, client: TestClient) -> None:
        session_id = uuid.uuid4()
        result_payload = {
            "session_id": session_id,
            "data_source_id": DEMO_SOURCE_ID,
            "question": "sales by region",
            "answer": "East leads.",
            "sql": "SELECT 1",
            "columns": ["region"],
            "rows": [{"region": "East"}],
            "status": "ok",
            "attempts": 1,
        }

        async def fake_stream(*_args, **_kwargs):
            yield {
                "type": "stage",
                "stage": "generate_sql",
                "label": "Generating SQL",
                "attempts": 0,
                "sql": None,
            }
            yield {"type": "result", **result_payload}

        with patch(
            "app.routes.chat.ChatService.ask_stream",
            side_effect=fake_stream,
        ):
            response = client.post(
                "/api/chat/stream",
                json={
                    "data_source_id": str(DEMO_SOURCE_ID),
                    "question": "sales by region",
                },
            )

        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]
        text = response.text
        assert "event: stage" in text
        assert "generate_sql" in text
        assert "event: result" in text
        assert "East leads." in text

    def test_chat_stream_emits_error_event_on_not_found(self, client: TestClient) -> None:
        async def fake_stream(*_args, **_kwargs):
            raise ValueError("Data source not found")
            yield  # pragma: no cover — makes this an async generator

        with patch(
            "app.routes.chat.ChatService.ask_stream",
            side_effect=fake_stream,
        ):
            response = client.post(
                "/api/chat/stream",
                json={
                    "data_source_id": str(DEMO_SOURCE_ID),
                    "question": "sales by region",
                },
            )

        assert response.status_code == 200
        assert "event: error" in response.text
        assert "not found" in response.text.lower()
