"""Orchestrate CSV/Excel upload → warehouse table → registered data source."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.schemas.data_source import WarehouseConnectRequest
from app.services.data_source_service import DataSourceService
from app.services.file_parser import FileParser
from app.services.table_loader import TableLoader


class UploadService:
    """High-level entrypoint used by POST /api/data/upload."""

    @staticmethod
    async def upload(
        session: AsyncSession,
        *,
        user_id: uuid.UUID,
        filename: str,
        content: bytes,
        display_name: str | None = None,
    ) -> dict[str, Any]:
        parsed = FileParser.parse(
            filename=filename,
            content=content,
            display_name=display_name,
        )

        # Isolated schema per upload so RAG/chat only see this file's table.
        schema_name = f"u_{uuid.uuid4().hex[:12]}"
        load = TableLoader.load(schema_name=schema_name, parsed=parsed)

        source_name = parsed.display_name
        if not source_name.lower().endswith("upload"):
            source_name = f"{source_name} (upload)"

        connected = await DataSourceService.connect(
            session,
            WarehouseConnectRequest(
                name=source_name[:100],
                db_type="postgres",
                host=settings.upload_wh_host,
                port=settings.upload_wh_port,
                database=settings.upload_wh_database,
                schema_name=load.schema_name,
                username=settings.upload_wh_query_user,
                password=settings.upload_wh_query_password.get_secret_value(),
                is_readonly=True,
            ),
            user_id=user_id,
        )

        return {
            "data_source_id": connected.data_source_id,
            "name": connected.name,
            "host": connected.host,
            "port": connected.port,
            "database": connected.database,
            "schema_name": load.schema_name,
            "table_name": load.table_name,
            "rows_loaded": load.rows_loaded,
            "columns": load.columns,
            "file_kind": parsed.file_kind,
            "status": "loaded",
        }
