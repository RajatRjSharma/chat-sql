"""Load parsed tables into the app database under an isolated schema."""

from __future__ import annotations

import re
from dataclasses import dataclass

from psycopg2 import sql
from psycopg2.extras import execute_values

from app.config import settings
from app.core.db_url import build_postgres_url
from app.core.exceptions import UploadError
from app.core.schema import validate_schema_identifier
from app.services.file_parser import ParsedTable
from app.warehouse.connect import connect_warehouse

# Must stay in sync with UploadService (`u_` + uuid4().hex[:12]).
_UPLOAD_SCHEMA_RE = re.compile(r"^u_[a-f0-9]{12}$")


@dataclass(frozen=True, slots=True)
class LoadResult:
    schema_name: str
    table_name: str
    rows_loaded: int
    columns: list[str]


class TableLoader:
    """CREATE SCHEMA/TABLE + bulk insert into the project (app) database."""

    @staticmethod
    def is_upload_schema(schema_name: str | None) -> bool:
        """True only for isolated CSV/Excel upload schemas (never warehouses)."""
        if not schema_name:
            return False
        return _UPLOAD_SCHEMA_RE.fullmatch(schema_name) is not None

    @staticmethod
    def writer_url() -> str:
        # psycopg2 expects postgresql:// (no SQLAlchemy driver suffix)
        return build_postgres_url(
            host=settings.app_db_host,
            port=settings.app_db_port,
            database=settings.app_db_name,
            username=settings.app_db_user,
            password=settings.app_db_password.get_secret_value(),
            driver=None,
        )

    @staticmethod
    def drop_upload_schema(schema_name: str) -> None:
        """
        DROP SCHEMA … CASCADE for an upload schema on the app DB.

        Raises:
            ValueError: name is not a recognised upload schema id.
            UploadError: driver / connectivity failure (message is client-safe).
        """
        if not TableLoader.is_upload_schema(schema_name):
            raise ValueError(f"Refusing to drop non-upload schema: {schema_name!r}")

        schema = validate_schema_identifier(schema_name)
        drop = sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(
            sql.Identifier(schema)
        )
        try:
            with connect_warehouse(
                TableLoader.writer_url(),
                host=settings.app_db_host,
            ) as conn:
                conn.autocommit = True
                with conn.cursor() as cur:
                    cur.execute(drop)
        except UploadError:
            raise
        except Exception as exc:  # noqa: BLE001 — map driver errors to UploadError
            raise UploadError("Could not drop upload schema.") from exc

    @staticmethod
    def load(*, schema_name: str, parsed: ParsedTable) -> LoadResult:
        schema = validate_schema_identifier(schema_name)
        table = validate_schema_identifier(parsed.table_name)

        col_defs = sql.SQL(", ").join(
            sql.SQL("{} {}").format(sql.Identifier(col.name), sql.SQL(col.pg_type))
            for col in parsed.columns
        )
        col_idents = sql.SQL(", ").join(
            sql.Identifier(col.name) for col in parsed.columns
        )

        create_schema = sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(
            sql.Identifier(schema)
        )
        drop_table = sql.SQL("DROP TABLE IF EXISTS {}.{}").format(
            sql.Identifier(schema), sql.Identifier(table)
        )
        create_table = sql.SQL("CREATE TABLE {}.{} ({})").format(
            sql.Identifier(schema),
            sql.Identifier(table),
            col_defs,
        )

        insert_sql = sql.SQL("INSERT INTO {}.{} ({}) VALUES %s").format(
            sql.Identifier(schema),
            sql.Identifier(table),
            col_idents,
        )

        values = [
            tuple(row.get(col.name) for col in parsed.columns) for row in parsed.rows
        ]

        try:
            with connect_warehouse(
                TableLoader.writer_url(),
                host=settings.app_db_host,
            ) as conn:
                conn.autocommit = False
                with conn.cursor() as cur:
                    cur.execute(create_schema)
                    cur.execute(drop_table)
                    cur.execute(create_table)
                    if values:
                        execute_values(
                            cur, insert_sql.as_string(cur), values, page_size=1000
                        )
                conn.commit()
        except UploadError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise UploadError("Could not load data into warehouse.") from exc

        return LoadResult(
            schema_name=schema,
            table_name=table,
            rows_loaded=len(values),
            columns=[c.name for c in parsed.columns],
        )
