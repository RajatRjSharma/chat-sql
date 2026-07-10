"""Tests for API request/response schemas."""

from __future__ import annotations

import uuid

import pytest
from pydantic import ValidationError

from app.schemas.data_source import (
    DataSourceSummary,
    WarehouseConnectRequest,
    WarehouseConnectResponse,
)


class TestWarehouseConnectRequest:
    def test_accepts_valid_payload(self) -> None:
        request = WarehouseConnectRequest(
            name="Warehouse",
            host="localhost",
            database="bi_warehouse",
            username="user",
            password="secret",
        )
        assert request.schema_name is None
        assert request.db_type == "postgres"
        assert request.port == 5432
        assert request.is_readonly is True

    def test_empty_schema_name_becomes_none(self) -> None:
        request = WarehouseConnectRequest(
            name="Warehouse",
            host="localhost",
            database="bi_warehouse",
            username="user",
            password="secret",
            schema_name="",
        )
        assert request.schema_name is None

    def test_whitespace_schema_name_becomes_none(self) -> None:
        request = WarehouseConnectRequest(
            name="Warehouse",
            host="localhost",
            database="bi_warehouse",
            username="user",
            password="secret",
            schema_name="   ",
        )
        assert request.schema_name is None

    def test_invalid_schema_name_rejected(self) -> None:
        with pytest.raises(ValidationError):
            WarehouseConnectRequest(
                name="Warehouse",
                host="localhost",
                database="bi_warehouse",
                username="user",
                password="secret",
                schema_name="bad-name",
            )

    @pytest.mark.parametrize("missing_field", ["name", "host", "database", "username", "password"])
    def test_required_fields(self, missing_field: str) -> None:
        payload = {
            "name": "Warehouse",
            "host": "localhost",
            "database": "bi_warehouse",
            "username": "user",
            "password": "secret",
        }
        payload.pop(missing_field)
        with pytest.raises(ValidationError):
            WarehouseConnectRequest.model_validate(payload)

    def test_invalid_db_type_rejected(self) -> None:
        with pytest.raises(ValidationError):
            WarehouseConnectRequest(
                name="Warehouse",
                host="localhost",
                database="bi_warehouse",
                username="user",
                password="secret",
                db_type="mysql",
            )


class TestWarehouseConnectResponse:
    def test_optional_schema_name(self) -> None:
        response = WarehouseConnectResponse(
            data_source_id=uuid.uuid4(),
            name="Warehouse",
            host="localhost",
            port=5432,
            database="bi_warehouse",
            schema_name=None,
        )
        assert response.status == "connected"
        assert response.schema_name is None


class TestDataSourceSummary:
    def test_from_attributes(self, sample_data_source) -> None:
        summary = DataSourceSummary.model_validate(sample_data_source)
        assert summary.id == sample_data_source.id
        assert summary.name == sample_data_source.name
        assert summary.schema_name == "sales"
        assert summary.is_active is True
