"""Unit tests for UploadService orchestration."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.schemas.data_source import WarehouseConnectResponse
from app.services.file_parser import ParsedColumn, ParsedTable
from app.services.table_loader import LoadResult
from app.services.upload_service import UploadService


@pytest.mark.asyncio
async def test_upload_service_registers_readonly_source() -> None:
    parsed = ParsedTable(
        table_name="sales",
        display_name="Sales",
        columns=[
            ParsedColumn(name="region", pg_type="TEXT"),
            ParsedColumn(name="amount", pg_type="BIGINT"),
        ],
        rows=[{"region": "East", "amount": 10}],
        file_kind="csv",
    )
    load = LoadResult(
        schema_name="u_abcdef123456",
        table_name="sales",
        rows_loaded=1,
        columns=["region", "amount"],
    )
    connected = WarehouseConnectResponse(
        data_source_id=uuid.uuid4(),
        name="Sales (upload)",
        host="localhost",
        port=5433,
        database="bi_warehouse",
        schema_name="u_abcdef123456",
        status="connected",
    )
    session = MagicMock()

    with (
        patch(
            "app.services.upload_service.FileParser.parse",
            return_value=parsed,
        ),
        patch(
            "app.services.upload_service.TableLoader.load",
            return_value=load,
        ),
        patch(
            "app.services.upload_service.DataSourceService.connect",
            new=AsyncMock(return_value=connected),
        ) as connect_mock,
    ):
        result = await UploadService.upload(
            session,
            user_id=uuid.uuid4(),
            filename="sales.csv",
            content=b"region,amount\nEast,10\n",
        )

    assert result["status"] == "loaded"
    assert result["table_name"] == "sales"
    assert result["rows_loaded"] == 1
    assert result["schema_name"] == "u_abcdef123456"
    request = connect_mock.await_args.args[1]
    assert request.is_readonly is True
    assert request.schema_name == "u_abcdef123456"
    assert request.username == "bi_readonly"
