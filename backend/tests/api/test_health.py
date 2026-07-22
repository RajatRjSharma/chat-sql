"""Tests for health check API endpoints."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from app.core.exceptions import AIProviderError
from app.main import APP_NAME, APP_VERSION
from tests.conftest import DEMO_SOURCE_ID


class TestHealthEndpoint:
    def test_health_returns_ok(self, client: TestClient) -> None:
        response = client.get("/health")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok"
        assert body["app"] == APP_NAME
        assert body["version"] == APP_VERSION


class TestHealthAiEndpoint:
    def test_health_ai_ok(self, client: TestClient) -> None:
        mock = MagicMock()
        mock.complete.return_value = "ok"
        with patch("app.main.get_ai_client", return_value=mock):
            response = client.get("/health/ai")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok"
        assert body["sample"] == "ok"

    def test_health_ai_provider_error_returns_503(self, client: TestClient) -> None:
        mock = MagicMock()
        mock.complete.side_effect = AIProviderError("rate limited")
        with patch("app.main.get_ai_client", return_value=mock):
            response = client.get("/health/ai")
        assert response.status_code == 503
        body = response.json()
        assert body["status"] == "error"
        assert "rate limited" in body["detail"]

    def test_health_ai_unexpected_error_returns_503(self, client: TestClient) -> None:
        mock = MagicMock()
        mock.complete.side_effect = RuntimeError("network down")
        with patch("app.main.get_ai_client", return_value=mock):
            response = client.get("/health/ai")
        assert response.status_code == 503
        assert response.json()["status"] == "error"


class TestHealthDbEndpoint:
    def _patch_engine_connect(self, mock_cm: AsyncMock):
        mock_engine = MagicMock()
        mock_engine.connect.return_value = mock_cm
        return patch("app.main.engine", mock_engine)

    def test_health_db_success_with_default_schema(self, client: TestClient) -> None:
        mock_conn = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = "public"
        mock_conn.execute = AsyncMock(return_value=mock_result)

        mock_cm = AsyncMock()
        mock_cm.__aenter__.return_value = mock_conn
        mock_cm.__aexit__.return_value = False

        with self._patch_engine_connect(mock_cm):
            with patch("app.main.settings.app_db_schema", None):
                response = client.get("/health/db")

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok"
        assert body["database"] == "bi_app"
        assert body["schema"] == "public"

    def test_health_db_success_with_configured_schema(self, client: TestClient) -> None:
        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock(return_value=MagicMock())

        mock_cm = AsyncMock()
        mock_cm.__aenter__.return_value = mock_conn
        mock_cm.__aexit__.return_value = False

        with self._patch_engine_connect(mock_cm):
            with patch("app.main.settings.app_db_schema", "analytics"):
                response = client.get("/health/db")

        assert response.status_code == 200
        assert response.json()["schema"] == "analytics"

    def test_health_db_failure_returns_503(self, client: TestClient) -> None:
        mock_engine = MagicMock()
        mock_engine.connect.side_effect = RuntimeError("db down")

        with patch("app.main.engine", mock_engine):
            response = client.get("/health/db")

        assert response.status_code == 503
        body = response.json()
        assert body["status"] == "error"
        assert body["database"] == "bi_app"
        assert "db down" in body["detail"]


class TestHealthWarehouseEndpoint:
    def test_health_warehouse_requires_data_source_id(self, client: TestClient) -> None:
        response = client.get("/health/warehouse")
        assert response.status_code == 422

    def test_health_warehouse_not_found_returns_404(self, client: TestClient) -> None:
        with patch(
            "app.main.DataSourceService.get_active",
            side_effect=ValueError("Data source not found"),
        ):
            response = client.get(f"/health/warehouse?data_source_id={DEMO_SOURCE_ID}")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_health_warehouse_success(self, client: TestClient) -> None:
        mock_info = MagicMock()
        mock_info.name = "Demo Sales Warehouse"
        mock_info.database = "bi_warehouse"
        mock_info.schema_name = "sales"
        mock_info.host = "localhost"
        mock_info.connection_url = (
            "postgresql://bi_readonly:readonly_pass@localhost:5433/bi_warehouse"
        )

        mock_cursor = MagicMock()
        mock_cursor.fetchone.side_effect = [(1,), (3,)]
        mock_conn = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_conn.__enter__.return_value = mock_conn

        with patch("app.main.DataSourceService.get_active", return_value=MagicMock()):
            with patch(
                "app.main.DataSourceService.connection_info_from_record",
                return_value=mock_info,
            ):
                with patch("app.main.connect_warehouse", return_value=mock_conn):
                    response = client.get(
                        f"/health/warehouse?data_source_id={DEMO_SOURCE_ID}"
                    )

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok"
        assert body["schema"] == "sales"
        assert body["table_count"] == 3
        assert body["data_source_id"] == str(DEMO_SOURCE_ID)

    def test_health_warehouse_connection_error_returns_503(self, client: TestClient) -> None:
        mock_info = MagicMock()
        mock_info.host = "localhost"
        mock_info.connection_url = "postgresql://bad"

        with patch("app.main.DataSourceService.get_active", return_value=MagicMock()):
            with patch(
                "app.main.DataSourceService.connection_info_from_record",
                return_value=mock_info,
            ):
                with patch(
                    "app.main.connect_warehouse",
                    side_effect=RuntimeError("refused"),
                ):
                    response = client.get(
                        f"/health/warehouse?data_source_id={DEMO_SOURCE_ID}"
                    )

        assert response.status_code == 503
        body = response.json()
        assert body["status"] == "error"
        assert body["data_source_id"] == str(DEMO_SOURCE_ID)
        assert "refused" not in body["detail"]
        assert body["detail"] == "Something went wrong. Please try again."
