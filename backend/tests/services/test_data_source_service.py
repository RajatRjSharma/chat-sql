"""Tests for data source business logic."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

from app.models.data_source import DataSource
from app.schemas.data_source import WarehouseConnectRequest
from app.services.data_source_service import DataSourceService
from app.warehouse.credentials import WarehouseConnectionInfo, WarehouseCredentials

from tests.conftest import DEMO_SOURCE_ID


class TestDataSourceServiceGetActive:
    async def test_returns_active_source(self, mock_db_session, sample_data_source) -> None:
        mock_db_session.get.return_value = sample_data_source
        result = await DataSourceService.get_active(mock_db_session, DEMO_SOURCE_ID)
        assert result == sample_data_source

    async def test_raises_when_not_found(self, mock_db_session) -> None:
        mock_db_session.get.return_value = None
        with pytest.raises(ValueError, match="Data source not found"):
            await DataSourceService.get_active(mock_db_session, uuid.uuid4())

    async def test_raises_when_inactive(self, mock_db_session, sample_data_source) -> None:
        sample_data_source.is_active = False
        mock_db_session.get.return_value = sample_data_source
        with pytest.raises(ValueError, match="Data source not found"):
            await DataSourceService.get_active(mock_db_session, DEMO_SOURCE_ID)


class TestDataSourceServiceDeactivate:
    async def test_deactivate_sets_inactive(self, mock_db_session, sample_data_source) -> None:
        mock_db_session.get.return_value = sample_data_source
        await DataSourceService.deactivate(
            mock_db_session,
            DEMO_SOURCE_ID,
            user_id=sample_data_source.user_id,
        )
        assert sample_data_source.is_active is False
        mock_db_session.add.assert_called_once_with(sample_data_source)
        mock_db_session.flush.assert_awaited()


class TestDataSourceServiceListActive:
    async def test_returns_active_sources(self, mock_db_session, sample_data_source) -> None:
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [sample_data_source]
        mock_db_session.execute.return_value = mock_result

        sources = await DataSourceService.list_active(
            mock_db_session, user_id=sample_data_source.user_id
        )
        assert sources == [sample_data_source]


class TestDataSourceServiceConnect:
    async def test_connect_persists_encrypted_credentials(
        self,
        mock_db_session,
        warehouse_connect_request: WarehouseConnectRequest,
    ) -> None:
        mock_db_session.get.return_value = None

        with patch.object(DataSourceService, "test_connection") as mock_test:
            response = await DataSourceService.connect(
                mock_db_session,
                warehouse_connect_request,
                user_id=uuid.UUID("00000000-0000-4000-8000-0000000000aa"),
            )

        mock_test.assert_called_once()
        mock_db_session.add.assert_called_once()
        mock_db_session.flush.assert_awaited_once()
        assert response.name == "Demo Sales Warehouse"
        assert response.schema_name == "sales"
        assert response.status == "connected"

        saved: DataSource = mock_db_session.add.call_args.args[0]
        assert saved.password_encrypted != "readonly_pass"
        assert saved.username == "bi_readonly"

    async def test_connect_updates_existing_record(
        self,
        mock_db_session,
        warehouse_connect_request: WarehouseConnectRequest,
        sample_data_source,
    ) -> None:
        mock_db_session.get.return_value = sample_data_source

        with patch.object(DataSourceService, "test_connection"):
            response = await DataSourceService.connect(
                mock_db_session,
                warehouse_connect_request,
                user_id=sample_data_source.user_id,
                data_source_id=DEMO_SOURCE_ID,
            )

        assert response.data_source_id == DEMO_SOURCE_ID
        mock_db_session.add.assert_called_once_with(sample_data_source)


class TestDataSourceServiceTestConnection:
    def test_test_connection_queries_information_schema(
        self,
        warehouse_connect_request: WarehouseConnectRequest,
    ) -> None:
        creds = WarehouseCredentials.from_request(warehouse_connect_request)
        mock_cursor = MagicMock()
        mock_cursor.fetchone.side_effect = [(1,), (3,)]
        mock_conn = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

        with patch(
            "app.services.data_source_service.connect_warehouse", return_value=mock_conn
        ):
            mock_conn.__enter__.return_value = mock_conn
            DataSourceService.test_connection(creds)

        mock_cursor.execute.assert_any_call("SELECT 1")
        assert mock_cursor.execute.call_count >= 2


class TestDataSourceServiceConnectionInfo:
    def test_connection_info_from_record(self, sample_data_source) -> None:
        info = DataSourceService.connection_info_from_record(sample_data_source)
        assert isinstance(info, WarehouseConnectionInfo)
        assert info.database == "bi_warehouse"
        assert info.schema_name == "sales"
        assert "bi_readonly" in info.connection_url
