"""Shared pytest fixtures."""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncGenerator, Generator
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

# Set required env before app imports load Settings.
os.environ.setdefault("APP_ENV", "local")
os.environ.setdefault("APP_DB_HOST", "localhost")
os.environ.setdefault("APP_DB_PORT", "5432")
os.environ.setdefault("APP_DB_NAME", "bi_app")
os.environ.setdefault("APP_DB_USER", "postgres")
os.environ.setdefault("APP_DB_PASSWORD", "postgres")
os.environ.setdefault("APP_DB_SCHEMA", "")
os.environ.setdefault("CREDENTIALS_SECRET", "test-credentials-secret")
os.environ.setdefault("AI_API_KEY", "test-ai-key")
os.environ.setdefault("UPLOAD_WH_HOST", "localhost")
os.environ.setdefault("UPLOAD_WH_PORT", "5433")
os.environ.setdefault("UPLOAD_WH_DATABASE", "bi_warehouse")
os.environ.setdefault("UPLOAD_WH_USER", "bi_uploader")
os.environ.setdefault("UPLOAD_WH_PASSWORD", "uploader_pass")
os.environ.setdefault("UPLOAD_WH_QUERY_USER", "bi_readonly")
os.environ.setdefault("UPLOAD_WH_QUERY_PASSWORD", "readonly_pass")
os.environ.setdefault("UPLOAD_MAX_BYTES", "10485760")
os.environ.setdefault("UPLOAD_MAX_ROWS", "50000")

from app.database import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models.data_source import DataSource  # noqa: E402
from app.schemas.data_source import WarehouseConnectRequest, WarehouseConnectResponse  # noqa: E402

WAREHOUSE_CONNECT_PAYLOAD = {
    "name": "Demo Sales Warehouse",
    "db_type": "postgres",
    "host": "localhost",
    "port": 5433,
    "database": "bi_warehouse",
    "schema_name": "sales",
    "username": "bi_readonly",
    "password": "readonly_pass",
    "is_readonly": True,
}

DEMO_SOURCE_ID = uuid.UUID("00000000-0000-4000-8000-000000000001")


@pytest.fixture
def warehouse_connect_request() -> WarehouseConnectRequest:
    return WarehouseConnectRequest.model_validate(WAREHOUSE_CONNECT_PAYLOAD)


@pytest.fixture
def warehouse_connect_response() -> WarehouseConnectResponse:
    return WarehouseConnectResponse(
        data_source_id=DEMO_SOURCE_ID,
        name="Demo Sales Warehouse",
        host="localhost",
        port=5433,
        database="bi_warehouse",
        schema_name="sales",
        status="connected",
    )


@pytest.fixture
def sample_data_source() -> DataSource:
    from app.security import encrypt_credential

    return DataSource(
        id=DEMO_SOURCE_ID,
        name="Demo Sales Warehouse",
        db_type="postgres",
        host="localhost",
        port=5433,
        database="bi_warehouse",
        schema_name="sales",
        username="bi_readonly",
        password_encrypted=encrypt_credential("readonly_pass"),
        is_readonly=True,
        is_active=True,
        extra_config={},
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def mock_db_session() -> AsyncMock:
    session = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    return session


@pytest.fixture
def client(mock_db_session: AsyncMock) -> Generator[TestClient, None, None]:
    async def override_get_db() -> AsyncGenerator[AsyncMock, None]:
        yield mock_db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
