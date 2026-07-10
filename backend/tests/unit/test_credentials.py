"""Tests for warehouse credential models."""

from __future__ import annotations

import uuid

import pytest

from app.schemas.data_source import WarehouseConnectRequest
from app.warehouse.credentials import WarehouseConnectionInfo, WarehouseCredentials


class TestWarehouseCredentials:
    def test_from_request_maps_fields(self, warehouse_connect_request: WarehouseConnectRequest) -> None:
        creds = WarehouseCredentials.from_request(warehouse_connect_request)
        assert creds.name == "Demo Sales Warehouse"
        assert creds.host == "localhost"
        assert creds.port == 5433
        assert creds.database == "bi_warehouse"
        assert creds.schema_name == "sales"
        assert creds.username == "bi_readonly"
        assert creds.password == "readonly_pass"
        assert creds.is_readonly is True

    def test_connection_url_format(self, warehouse_connect_request: WarehouseConnectRequest) -> None:
        creds = WarehouseCredentials.from_request(warehouse_connect_request)
        assert creds.connection_url() == (
            "postgresql://bi_readonly:readonly_pass@localhost:5433/bi_warehouse"
        )

    def test_from_data_source_decrypted_roundtrip(self, sample_data_source) -> None:
        creds = WarehouseCredentials.from_data_source_decrypted(sample_data_source)
        assert creds.password == "readonly_pass"
        assert creds.schema_name == "sales"

    def test_from_data_source_decrypted_missing_username_raises(self, sample_data_source) -> None:
        sample_data_source.username = None
        with pytest.raises(ValueError, match="missing stored credentials"):
            WarehouseCredentials.from_data_source_decrypted(sample_data_source)

    def test_from_data_source_decrypted_missing_password_raises(self, sample_data_source) -> None:
        sample_data_source.password_encrypted = None
        with pytest.raises(ValueError, match="missing stored credentials"):
            WarehouseCredentials.from_data_source_decrypted(sample_data_source)


class TestWarehouseConnectionInfo:
    def test_from_credentials(self, warehouse_connect_request: WarehouseConnectRequest) -> None:
        creds = WarehouseCredentials.from_request(warehouse_connect_request)
        info = WarehouseConnectionInfo.from_credentials(creds)
        assert info.name == creds.name
        assert info.connection_url == creds.connection_url()
        assert info.schema_name == "sales"
        assert info.is_readonly is True
