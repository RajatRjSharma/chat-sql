"""Warehouse schema introspection via information_schema."""

from __future__ import annotations

from dataclasses import dataclass, field

import psycopg2
from psycopg2.extensions import connection as PgConnection

from app.core.exceptions import SchemaEmbeddingError
from app.core.schema import read_connection_schema
from app.warehouse import WarehouseConnectionInfo


@dataclass(frozen=True, slots=True)
class ColumnInfo:
    name: str
    data_type: str
    is_nullable: bool
    is_primary_key: bool = False


@dataclass(frozen=True, slots=True)
class ForeignKeyInfo:
    column: str
    referenced_table: str
    referenced_column: str


@dataclass(frozen=True, slots=True)
class TableInfo:
    schema_name: str
    table_name: str
    columns: list[ColumnInfo] = field(default_factory=list)
    foreign_keys: list[ForeignKeyInfo] = field(default_factory=list)
    sample_rows: list[dict[str, object]] = field(default_factory=list)

    @property
    def qualified_name(self) -> str:
        return f"{self.schema_name}.{self.table_name}"


class SchemaIntrospectionService:
    """Read table/column/FK metadata from a connected warehouse."""

    @staticmethod
    def introspect(
        info: WarehouseConnectionInfo,
        *,
        sample_limit: int = 3,
    ) -> list[TableInfo]:
        try:
            with psycopg2.connect(info.connection_url) as conn:
                schema = read_connection_schema(conn.cursor(), info.schema_name)
                tables = SchemaIntrospectionService._list_tables(conn, schema)
                result: list[TableInfo] = []
                for table_name in tables:
                    columns = SchemaIntrospectionService._list_columns(conn, schema, table_name)
                    fks = SchemaIntrospectionService._list_foreign_keys(conn, schema, table_name)
                    samples = SchemaIntrospectionService._sample_rows(
                        conn, schema, table_name, columns, limit=sample_limit
                    )
                    result.append(
                        TableInfo(
                            schema_name=schema,
                            table_name=table_name,
                            columns=columns,
                            foreign_keys=fks,
                            sample_rows=samples,
                        )
                    )
                return result
        except SchemaEmbeddingError:
            raise
        except Exception as exc:
            raise SchemaEmbeddingError(f"Schema introspection failed: {exc}") from exc

    @staticmethod
    def _list_tables(conn: PgConnection, schema: str) -> list[str]:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = %s
                  AND table_type = 'BASE TABLE'
                ORDER BY table_name
                """,
                (schema,),
            )
            return [row[0] for row in cur.fetchall()]

    @staticmethod
    def _list_columns(conn: PgConnection, schema: str, table: str) -> list[ColumnInfo]:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    c.column_name,
                    c.data_type,
                    c.is_nullable,
                    CASE WHEN tc.constraint_type = 'PRIMARY KEY' THEN true ELSE false END AS is_pk
                FROM information_schema.columns c
                LEFT JOIN information_schema.key_column_usage kcu
                    ON c.table_schema = kcu.table_schema
                   AND c.table_name = kcu.table_name
                   AND c.column_name = kcu.column_name
                LEFT JOIN information_schema.table_constraints tc
                    ON kcu.constraint_name = tc.constraint_name
                   AND kcu.table_schema = tc.table_schema
                   AND tc.constraint_type = 'PRIMARY KEY'
                WHERE c.table_schema = %s
                  AND c.table_name = %s
                ORDER BY c.ordinal_position
                """,
                (schema, table),
            )
            return [
                ColumnInfo(
                    name=row[0],
                    data_type=row[1],
                    is_nullable=row[2] == "YES",
                    is_primary_key=bool(row[3]),
                )
                for row in cur.fetchall()
            ]

    @staticmethod
    def _list_foreign_keys(
        conn: PgConnection, schema: str, table: str
    ) -> list[ForeignKeyInfo]:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    kcu.column_name,
                    ccu.table_name AS referenced_table,
                    ccu.column_name AS referenced_column
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu
                    ON tc.constraint_name = kcu.constraint_name
                   AND tc.table_schema = kcu.table_schema
                JOIN information_schema.constraint_column_usage ccu
                    ON ccu.constraint_name = tc.constraint_name
                   AND ccu.table_schema = tc.table_schema
                WHERE tc.constraint_type = 'FOREIGN KEY'
                  AND tc.table_schema = %s
                  AND tc.table_name = %s
                ORDER BY kcu.ordinal_position
                """,
                (schema, table),
            )
            return [
                ForeignKeyInfo(
                    column=row[0],
                    referenced_table=row[1],
                    referenced_column=row[2],
                )
                for row in cur.fetchall()
            ]

    @staticmethod
    def _sample_rows(
        conn: PgConnection,
        schema: str,
        table: str,
        columns: list[ColumnInfo],
        *,
        limit: int,
    ) -> list[dict[str, object]]:
        if not columns or limit <= 0:
            return []
        from psycopg2 import sql

        query = sql.SQL("SELECT * FROM {}.{} LIMIT %s").format(
            sql.Identifier(schema),
            sql.Identifier(table),
        )
        with conn.cursor() as cur:
            cur.execute(query, (limit,))
            rows = cur.fetchall()
            names = [col.name for col in columns]
            return [dict(zip(names, row, strict=False)) for row in rows]
