"""Execute validated SELECT queries on a user warehouse."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from uuid import UUID

import psycopg2
from psycopg2.extras import RealDictCursor

from app.config import settings
from app.core.exceptions import WarehouseQueryError
from app.warehouse import WarehouseConnectionInfo


@dataclass(frozen=True, slots=True)
class QueryResult:
    columns: list[str]
    rows: list[dict[str, Any]]
    row_count: int


def _serialize_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, UUID):
        return str(value)
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            return str(value)
    return value


class WarehouseExecutor:
    """Run read-only SQL against a connected warehouse."""

    @staticmethod
    def execute(
        info: WarehouseConnectionInfo,
        sql: str,
        *,
        max_rows: int | None = None,
    ) -> QueryResult:
        limit = max_rows or settings.warehouse_max_rows
        try:
            with psycopg2.connect(info.connection_url) as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(sql)
                    if cur.description is None:
                        raise WarehouseQueryError("Query did not return a result set.")
                    columns = [col.name for col in cur.description]
                    raw_rows = cur.fetchmany(limit)
                    rows = [
                        {key: _serialize_value(value) for key, value in dict(row).items()}
                        for row in raw_rows
                    ]
                    return QueryResult(columns=columns, rows=rows, row_count=len(rows))
        except WarehouseQueryError:
            raise
        except Exception as exc:
            raise WarehouseQueryError(f"Warehouse query failed: {exc}") from exc
