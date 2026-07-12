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
        assert "connection refused" in response.json()["detail"]

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
            "app.routes.data.DataSourceService.list_active",
            new=AsyncMock(return_value=[]),
        ):
            response = client.get("/api/data/sources")

        assert response.status_code == 200
        assert response.json() == []

    def test_list_sources_returns_summaries(self, client: TestClient, sample_data_source) -> None:
        with patch(
            "app.routes.data.DataSourceService.list_active",
            new=AsyncMock(return_value=[sample_data_source]),
        ):
            response = client.get("/api/data/sources")

        assert response.status_code == 200
        body = response.json()
        assert len(body) == 1
        assert body[0]["id"] == str(DEMO_SOURCE_ID)
        assert body[0]["name"] == "Demo Sales Warehouse"
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
