"""API tests for chat and embed-schema routes."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.core.exceptions import AIProviderError, ChatPipelineError, SchemaEmbeddingError
from tests.conftest import DEMO_SOURCE_ID


class TestEmbedSchemaRoute:
    def test_embed_schema_success(self, client: TestClient) -> None:
        with patch(
            "app.routes.data.SchemaEmbeddingService.embed_data_source",
            new=AsyncMock(return_value=3),
        ):
            response = client.post(
                "/api/data/embed-schema",
                json={"data_source_id": str(DEMO_SOURCE_ID)},
            )
        assert response.status_code == 200
        body = response.json()
        assert body["chunks_embedded"] == 3
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
        assert "boom" in response.json()["detail"]

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
        assert "AI provider error" in detail
        assert "429" in detail

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
        assert "boom" in response.json()["detail"]

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
