"""Business logic for user-provided analytics database connections."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.schema import read_connection_schema
from app.models import ChatSession, DataSource, SchemaEmbedding
from app.schemas.data_source import WarehouseConnectRequest, WarehouseConnectResponse
from app.security import encrypt_credential
from app.security.ssrf import assert_safe_warehouse_host
from app.services.table_loader import TableLoader
from app.warehouse import WarehouseConnectionInfo, WarehouseCredentials
from app.warehouse.connect import connect_warehouse

logger = logging.getLogger(__name__)


class DataSourceService:
    """Manage warehouse connections supplied by users."""

    @staticmethod
    def test_connection(credentials: WarehouseCredentials) -> None:
        """Verify warehouse connectivity and schema access."""
        assert_safe_warehouse_host(credentials.host)
        info = WarehouseConnectionInfo.from_credentials(credentials)
        with connect_warehouse(info.connection_url, host=info.host) as conn:
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
        user_id: uuid.UUID,
        data_source_id: uuid.UUID | None = None,
    ) -> WarehouseConnectResponse:
        credentials = WarehouseCredentials.from_request(request)
        assert_safe_warehouse_host(credentials.host)
        DataSourceService.test_connection(credentials)

        record_id = data_source_id or uuid.uuid4()
        existing = await session.get(DataSource, record_id)
        if existing is not None and existing.user_id != user_id:
            raise ValueError(f"Data source not found: {record_id}")

        data_source = existing or DataSource(id=record_id, user_id=user_id)
        data_source.user_id = user_id
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
    async def get_active(
        session: AsyncSession,
        data_source_id: uuid.UUID,
        *,
        user_id: uuid.UUID | None = None,
    ) -> DataSource:
        data_source = await session.get(DataSource, data_source_id)
        if (
            data_source is None
            or not data_source.is_active
            or (user_id is not None and data_source.user_id != user_id)
        ):
            raise ValueError(f"Data source not found: {data_source_id}")
        return data_source

    @staticmethod
    async def list_active(
        session: AsyncSession,
        *,
        user_id: uuid.UUID,
    ) -> list[DataSource]:
        result = await session.execute(
            select(DataSource)
            .where(DataSource.is_active.is_(True))
            .where(DataSource.user_id == user_id)
            .order_by(DataSource.updated_at.desc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def list_active_summaries(
        session: AsyncSession,
        *,
        user_id: uuid.UUID,
    ) -> list[dict[str, Any]]:
        """Active sources with embedding + session counts for the reconnect UI."""
        chunk_count = (
            select(func.count(SchemaEmbedding.id))
            .where(SchemaEmbedding.data_source_id == DataSource.id)
            .correlate(DataSource)
            .scalar_subquery()
        )
        session_count = (
            select(func.count(ChatSession.session_id))
            .where(ChatSession.data_source_id == DataSource.id)
            .where(ChatSession.user_id == user_id)
            .correlate(DataSource)
            .scalar_subquery()
        )
        result = await session.execute(
            select(
                DataSource,
                chunk_count.label("chunks_embedded"),
                session_count.label("session_count"),
            )
            .where(DataSource.is_active.is_(True))
            .where(DataSource.user_id == user_id)
            .order_by(DataSource.updated_at.desc())
        )
        summaries: list[dict[str, Any]] = []
        for source, chunks_embedded, sessions in result.all():
            extra = source.extra_config or {}
            table_count = extra.get("schema_table_count")
            indexed_at = extra.get("schema_indexed_at")
            summaries.append(
                {
                    "id": source.id,
                    "name": source.name,
                    "host": source.host,
                    "port": source.port,
                    "database": source.database,
                    "schema_name": source.schema_name,
                    "db_type": source.db_type,
                    "is_readonly": source.is_readonly,
                    "is_active": source.is_active,
                    "chunks_embedded": int(chunks_embedded or 0),
                    "tables_indexed": int(table_count) if table_count is not None else None,
                    "schema_indexed_at": indexed_at,
                    "session_count": int(sessions or 0),
                }
            )
        return summaries

    @staticmethod
    async def deactivate(
        session: AsyncSession,
        data_source_id: uuid.UUID,
        *,
        user_id: uuid.UUID,
    ) -> None:
        """
        Soft-delete a data source.

        For CSV/Excel uploads, also best-effort DROP the isolated `u_*`
        schema on the app database. Soft-delete always wins: a failed DROP
        is logged and does not re-activate the source. Warehouse schemas are
        never dropped.
        """
        data_source = await DataSourceService.get_active(
            session, data_source_id, user_id=user_id
        )
        schema_to_drop = (
            data_source.schema_name
            if TableLoader.is_upload_schema(data_source.schema_name)
            else None
        )

        data_source.is_active = False
        session.add(data_source)
        await session.flush()

        if not schema_to_drop:
            return

        try:
            TableLoader.drop_upload_schema(schema_to_drop)
        except Exception:  # noqa: BLE001 — cleanup must not undo soft-delete
            logger.exception(
                "Failed to drop upload schema %s after deactivate",
                schema_to_drop,
            )

    @staticmethod
    def connection_info_from_record(data_source: DataSource) -> WarehouseConnectionInfo:
        credentials = WarehouseCredentials.from_data_source_decrypted(data_source)
        return WarehouseConnectionInfo.from_credentials(credentials)
