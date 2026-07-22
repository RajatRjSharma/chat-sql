"""Tests for /api/data routes."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.schemas.data_source import WarehouseConnectResponse
from tests.conftest import DEMO_SOURCE_ID, WAREHOUSE_CONNECT_PAYLOAD


class TestConnectWarehouse:
    def test_connect_success(
        self,
        client: TestClient,
        warehouse_connect_response: WarehouseConnectResponse,
    ) -> None:
        with patch(
            "app.routes.data.DataSourceService.connect",
            new=AsyncMock(return_value=warehouse_connect_response),
        ):
            response = client.post("/api/data/connect", json=WAREHOUSE_CONNECT_PAYLOAD)

        assert response.status_code == 200
        body = response.json()
        assert body["data_source_id"] == str(DEMO_SOURCE_ID)
        assert body["status"] == "connected"
        assert body["schema_name"] == "sales"

    def test_connect_validation_error_returns_422(self, client: TestClient) -> None:
        payload = {**WAREHOUSE_CONNECT_PAYLOAD, "port": 0}
        response = client.post("/api/data/connect", json=payload)
        assert response.status_code == 422

    def test_connect_missing_required_field_returns_422(self, client: TestClient) -> None:
        payload = {k: v for k, v in WAREHOUSE_CONNECT_PAYLOAD.items() if k != "password"}
        response = client.post("/api/data/connect", json=payload)
        assert response.status_code == 422

    def test_connect_bad_gateway_on_connection_failure(self, client: TestClient) -> None:
        with patch(
            "app.routes.data.DataSourceService.connect",
            new=AsyncMock(side_effect=RuntimeError("connection refused")),
        ):
            response = client.post("/api/data/connect", json=WAREHOUSE_CONNECT_PAYLOAD)

        assert response.status_code == 502
        assert response.json()["detail"] == (
            "Could not connect to the warehouse. Check host, port, and credentials."
        )
        assert "connection refused" not in response.json()["detail"]

    def test_connect_bad_request_on_value_error(self, client: TestClient) -> None:
        with patch(
            "app.routes.data.DataSourceService.connect",
            new=AsyncMock(side_effect=ValueError("invalid credentials")),
        ):
            response = client.post("/api/data/connect", json=WAREHOUSE_CONNECT_PAYLOAD)

        assert response.status_code == 400
        assert response.json()["detail"] == "invalid credentials"


class TestListDataSources:
    def test_list_sources_empty(self, client: TestClient) -> None:
        with patch(
            "app.routes.data.DataSourceService.list_active_summaries",
            new=AsyncMock(return_value=[]),
        ):
            response = client.get("/api/data/sources")

        assert response.status_code == 200
        assert response.json() == []

    def test_list_sources_returns_summaries(self, client: TestClient) -> None:
        summary = {
            "id": DEMO_SOURCE_ID,
            "name": "Demo Sales Warehouse",
            "host": "localhost",
            "port": 5433,
            "database": "bi_warehouse",
            "schema_name": "sales",
            "db_type": "postgres",
            "is_readonly": True,
            "is_active": True,
            "chunks_embedded": 3,
            "session_count": 2,
        }
        with patch(
            "app.routes.data.DataSourceService.list_active_summaries",
            new=AsyncMock(return_value=[summary]),
        ):
            response = client.get("/api/data/sources")

        assert response.status_code == 200
        body = response.json()
        assert len(body) == 1
        assert body[0]["id"] == str(DEMO_SOURCE_ID)
        assert body[0]["name"] == "Demo Sales Warehouse"
        assert body[0]["chunks_embedded"] == 3
        assert body[0]["session_count"] == 2
        assert "password" not in body[0]


class TestGetDataSource:
    def test_get_source_success(self, client: TestClient, sample_data_source) -> None:
        with patch(
            "app.routes.data.DataSourceService.get_active",
            new=AsyncMock(return_value=sample_data_source),
        ):
            response = client.get(f"/api/data/sources/{DEMO_SOURCE_ID}")

        assert response.status_code == 200
        body = response.json()
        assert body["database"] == "bi_warehouse"
        assert body["schema_name"] == "sales"

    def test_get_source_not_found(self, client: TestClient) -> None:
        missing_id = uuid.uuid4()
        with patch(
            "app.routes.data.DataSourceService.get_active",
            new=AsyncMock(side_effect=ValueError(f"Data source not found: {missing_id}")),
        ):
            response = client.get(f"/api/data/sources/{missing_id}")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()


class TestDeleteDataSource:
    def test_delete_source_success(self, client: TestClient) -> None:
        with patch(
            "app.routes.data.DataSourceService.deactivate",
            new=AsyncMock(return_value=None),
        ):
            response = client.delete(f"/api/data/sources/{DEMO_SOURCE_ID}")

        assert response.status_code == 204

    def test_delete_source_not_found(self, client: TestClient) -> None:
        missing_id = uuid.uuid4()
        with patch(
            "app.routes.data.DataSourceService.deactivate",
            new=AsyncMock(side_effect=ValueError(f"Data source not found: {missing_id}")),
        ):
            response = client.delete(f"/api/data/sources/{missing_id}")

        assert response.status_code == 404


class TestSuggestedQuestionsRoute:
    def test_suggested_questions_success(self, client: TestClient) -> None:
        payload = {
            "data_source_id": DEMO_SOURCE_ID,
            "suggestions": [
                {
                    "question": "What is total amount by region in orders?",
                    "source": "schema",
                    "table": "orders",
                }
            ],
            "schema_tables": ["orders"],
        }
        with patch(
            "app.routes.data.SuggestionService.suggest_for_data_source",
            new=AsyncMock(return_value=payload),
        ):
            response = client.get(
                f"/api/data/sources/{DEMO_SOURCE_ID}/suggested-questions"
            )

        assert response.status_code == 200
        body = response.json()
        assert body["data_source_id"] == str(DEMO_SOURCE_ID)
        assert body["suggestions"][0]["source"] == "schema"
        assert body["schema_tables"] == ["orders"]

    def test_suggested_questions_not_found(self, client: TestClient) -> None:
        missing = uuid.uuid4()
        with patch(
            "app.routes.data.SuggestionService.suggest_for_data_source",
            new=AsyncMock(side_effect=ValueError("Data source not found")),
        ):
            response = client.get(f"/api/data/sources/{missing}/suggested-questions")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_suggested_questions_limit_validation(self, client: TestClient) -> None:
        response = client.get(
            f"/api/data/sources/{DEMO_SOURCE_ID}/suggested-questions?limit=0"
        )
        assert response.status_code == 422


class TestUploadRoute:
    def test_upload_success(self, client: TestClient) -> None:
        payload = {
            "data_source_id": DEMO_SOURCE_ID,
            "name": "sales (upload)",
            "host": "localhost",
            "port": 5433,
            "database": "bi_warehouse",
            "schema_name": "u_abc123def456",
            "table_name": "sales",
            "rows_loaded": 2,
            "columns": ["region", "amount"],
            "file_kind": "csv",
            "status": "loaded",
        }
        with patch(
            "app.routes.data.UploadService.upload",
            new=AsyncMock(return_value=payload),
        ):
            response = client.post(
                "/api/data/upload",
                files={"file": ("sales.csv", b"region,amount\nEast,1\n", "text/csv")},
                data={"name": "sales"},
            )

        assert response.status_code == 200
        body = response.json()
        assert body["data_source_id"] == str(DEMO_SOURCE_ID)
        assert body["table_name"] == "sales"
        assert body["rows_loaded"] == 2
        assert body["file_kind"] == "csv"

    def test_upload_validation_error_returns_400(self, client: TestClient) -> None:
        from app.core.exceptions import UploadError

        with patch(
            "app.routes.data.UploadService.upload",
            new=AsyncMock(side_effect=UploadError("Unsupported file type")),
        ):
            response = client.post(
                "/api/data/upload",
                files={"file": ("notes.txt", b"hello", "text/plain")},
            )

        assert response.status_code == 400
        assert "Unsupported" in response.json()["detail"]

    def test_upload_missing_file_returns_422(self, client: TestClient) -> None:
        response = client.post("/api/data/upload", data={"name": "x"})
        assert response.status_code == 422
