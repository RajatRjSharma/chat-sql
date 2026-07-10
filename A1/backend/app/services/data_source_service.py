"""Business logic for user-provided analytics database connections."""

from __future__ import annotations

import uuid

import psycopg2
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import DataSource
from app.schemas.data_source import WarehouseConnectRequest, WarehouseConnectResponse
from app.security import encrypt_credential
from app.core.schema import read_connection_schema
from app.warehouse import WarehouseConnectionInfo, WarehouseCredentials


class DataSourceService:
    """Manage warehouse connections supplied by users."""

    @staticmethod
    def test_connection(credentials: WarehouseCredentials) -> None:
        """Verify warehouse connectivity and schema access."""
        info = WarehouseConnectionInfo.from_credentials(credentials)
        with psycopg2.connect(info.connection_url) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
                schema = read_connection_schema(cur, info.schema_name)
                cur.execute(
                    """
                    SELECT COUNT(*)
                    FROM information_schema.tables
                    WHERE table_schema = %s
                    """,
                    (schema,),
                )
                cur.fetchone()

    @staticmethod
    async def connect(
        session: AsyncSession,
        request: WarehouseConnectRequest,
        *,
        data_source_id: uuid.UUID | None = None,
    ) -> WarehouseConnectResponse:
        credentials = WarehouseCredentials.from_request(request)
        DataSourceService.test_connection(credentials)

        record_id = data_source_id or uuid.uuid4()
        existing = await session.get(DataSource, record_id)

        data_source = existing or DataSource(id=record_id)
        data_source.name = credentials.name
        data_source.db_type = credentials.db_type
        data_source.host = credentials.host
        data_source.port = credentials.port
        data_source.database = credentials.database
        data_source.schema_name = credentials.schema_name
        data_source.username = credentials.username
        data_source.password_encrypted = encrypt_credential(credentials.password)
        data_source.is_readonly = credentials.is_readonly
        data_source.is_active = True

        session.add(data_source)
        await session.flush()

        return WarehouseConnectResponse(
            data_source_id=data_source.id,
            name=data_source.name,
            host=data_source.host,
            port=data_source.port,
            database=data_source.database,
            schema_name=data_source.schema_name,
            status="connected",
        )

    @staticmethod
    async def get_active(session: AsyncSession, data_source_id: uuid.UUID) -> DataSource:
        data_source = await session.get(DataSource, data_source_id)
        if data_source is None or not data_source.is_active:
            raise ValueError(f"Data source not found: {data_source_id}")
        return data_source

    @staticmethod
    async def list_active(session: AsyncSession) -> list[DataSource]:
        result = await session.execute(
            select(DataSource).where(DataSource.is_active.is_(True)).order_by(DataSource.created_at)
        )
        return list(result.scalars().all())

    @staticmethod
    def connection_info_from_record(data_source: DataSource) -> WarehouseConnectionInfo:
        credentials = WarehouseCredentials.from_data_source_decrypted(data_source)
        return WarehouseConnectionInfo.from_credentials(credentials)
