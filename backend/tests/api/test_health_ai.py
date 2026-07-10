"""Tests for health/ai endpoint."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.core.exceptions import OpenRouterError


class TestHealthAi:
    def test_health_ai_ok(self, client: TestClient) -> None:
        mock = MagicMock()
        mock.complete.return_value = "ok"
        with patch("app.main.get_openrouter_client", return_value=mock):
            response = client.get("/health/ai")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    def test_health_ai_error(self, client: TestClient) -> None:
        mock = MagicMock()
        mock.complete.side_effect = OpenRouterError("down")
        with patch("app.main.get_openrouter_client", return_value=mock):
            response = client.get("/health/ai")
        assert response.status_code == 200
        assert response.json()["status"] == "error"
