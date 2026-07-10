"""API tests for chat and embed-schema routes."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

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

    def test_embed_schema_not_found(self, client: TestClient) -> None:
        with patch(
            "app.routes.data.SchemaEmbeddingService.embed_data_source",
            new=AsyncMock(side_effect=ValueError("Data source not found")),
        ):
            response = client.post(
                "/api/data/embed-schema",
                json={"data_source_id": str(uuid.uuid4())},
            )
        assert response.status_code == 404


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

    def test_chat_not_found(self, client: TestClient) -> None:
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

    def test_chat_validation_error(self, client: TestClient) -> None:
        response = client.post(
            "/api/chat",
            json={"data_source_id": str(DEMO_SOURCE_ID), "question": ""},
        )
        assert response.status_code == 422
