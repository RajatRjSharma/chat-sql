"""Load parsed tables into the warehouse under an isolated schema."""

from __future__ import annotations

from dataclasses import dataclass

import psycopg2
from psycopg2 import sql
from psycopg2.extras import execute_values

from app.config import settings
from app.core.db_url import build_postgres_url
from app.core.exceptions import UploadError
from app.core.schema import validate_schema_identifier
from app.services.file_parser import ParsedTable


@dataclass(frozen=True, slots=True)
class LoadResult:
    schema_name: str
    table_name: str
    rows_loaded: int
    columns: list[str]


class TableLoader:
    """CREATE SCHEMA/TABLE + bulk insert + grant SELECT to the query role."""

    @staticmethod
    def writer_url() -> str:
        # psycopg2 expects postgresql:// (no SQLAlchemy driver suffix)
        return build_postgres_url(
            host=settings.upload_wh_host,
            port=settings.upload_wh_port,
            database=settings.upload_wh_database,
            username=settings.upload_wh_user,
            password=settings.upload_wh_password.get_secret_value(),
            driver=None,
        )

    @staticmethod
    def load(*, schema_name: str, parsed: ParsedTable) -> LoadResult:
        schema = validate_schema_identifier(schema_name)
        table = validate_schema_identifier(parsed.table_name)
        query_user = validate_schema_identifier(settings.upload_wh_query_user)

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
        grant_usage = sql.SQL("GRANT USAGE ON SCHEMA {} TO {}").format(
            sql.Identifier(schema), sql.Identifier(query_user)
        )
        grant_select = sql.SQL(
            "GRANT SELECT ON ALL TABLES IN SCHEMA {} TO {}"
        ).format(sql.Identifier(schema), sql.Identifier(query_user))
        default_privs = sql.SQL(
            "ALTER DEFAULT PRIVILEGES IN SCHEMA {} GRANT SELECT ON TABLES TO {}"
        ).format(sql.Identifier(schema), sql.Identifier(query_user))

        insert_sql = sql.SQL("INSERT INTO {}.{} ({}) VALUES %s").format(
            sql.Identifier(schema),
            sql.Identifier(table),
            col_idents,
        )

        values = [
            tuple(row.get(col.name) for col in parsed.columns) for row in parsed.rows
        ]

        try:
            with psycopg2.connect(TableLoader.writer_url()) as conn:
                conn.autocommit = False
                with conn.cursor() as cur:
                    cur.execute(create_schema)
                    cur.execute(drop_table)
                    cur.execute(create_table)
                    if values:
                        execute_values(cur, insert_sql.as_string(cur), values, page_size=1000)
                    cur.execute(grant_usage)
                    cur.execute(grant_select)
                    cur.execute(default_privs)
                conn.commit()
        except UploadError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise UploadError(f"Could not load data into warehouse: {exc}") from exc

        return LoadResult(
            schema_name=schema,
            table_name=table,
            rows_loaded=len(values),
            columns=[c.name for c in parsed.columns],
        )
