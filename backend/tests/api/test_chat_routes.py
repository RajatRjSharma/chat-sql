"""API tests for chat and embed-schema routes."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

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
    def test_get_session_success(self, client: TestClient) -> None:
        session_id = uuid.uuid4()
        chat = MagicMock()
        chat.session_id = session_id
        chat.data_source_id = DEMO_SOURCE_ID
        chat.title = "sales?"
        msg_user = MagicMock(role="user", content="sales?")
        msg_assistant = MagicMock(role="assistant", content="East leads.")
        chat.messages = [msg_user, msg_assistant]

        with patch(
            "app.routes.chat.ChatPersistenceService.get_session_with_messages",
            new=AsyncMock(return_value=chat),
        ):
            response = client.get(f"/api/chat/sessions/{session_id}")

        assert response.status_code == 200
        body = response.json()
        assert body["session_id"] == str(session_id)
        assert len(body["messages"]) == 2
        assert body["messages"][0]["role"] == "user"

    def test_get_session_not_found_returns_404(self, client: TestClient) -> None:
        missing = uuid.uuid4()
        with patch(
            "app.routes.chat.ChatPersistenceService.get_session_with_messages",
            new=AsyncMock(return_value=None),
        ):
            response = client.get(f"/api/chat/sessions/{missing}")
        assert response.status_code == 404
        assert response.json()["detail"] == "Session not found"

    def test_get_session_invalid_uuid_returns_422(self, client: TestClient) -> None:
        response = client.get("/api/chat/sessions/not-a-uuid")
        assert response.status_code == 422
