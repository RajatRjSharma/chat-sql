#!/usr/bin/env python3
"""Inspect a warehouse database using CLI credentials or a saved data source."""

from __future__ import annotations

import argparse
import asyncio
import sys
import uuid

import psycopg2
from psycopg2 import sql

import scripts._bootstrap  # noqa: F401
from app.database import AsyncSessionLocal
from app.services.data_source_service import DataSourceService
from app.warehouse import WarehouseConnectionInfo, WarehouseCredentials, qualify_table, read_connection_schema
from scripts._credentials_cli import build_warehouse_credentials_parser, credentials_from_args


def _print_header(title: str) -> None:
    print(f"\n{'=' * 60}")
    print(title)
    print("=" * 60)


async def _load_from_project_db(data_source_id: uuid.UUID) -> WarehouseConnectionInfo:
    async with AsyncSessionLocal() as session:
        data_source = await DataSourceService.get_active(session, data_source_id)
        return DataSourceService.connection_info_from_record(data_source)


def check_warehouse(info: WarehouseConnectionInfo) -> None:
    _print_header("Warehouse connection (user-provided credentials)")
    print(f"  Name:     {info.name}")
    print(f"  Host:     {info.host}:{info.port}")
    print(f"  Database: {info.database}")
    print(f"  Schema:   {info.schema_name or '(postgresql default)'}")
    print(f"  Read-only: {info.is_readonly}")

    with psycopg2.connect(info.connection_url) as conn:
        with conn.cursor() as cur:
            schema = read_connection_schema(cur, info.schema_name)

            _print_header("Tables in schema")
            cur.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = %s
                ORDER BY table_name
                """,
                (schema,),
            )
            tables = [row[0] for row in cur.fetchall()]
            for table in tables:
                print(f"  • {qualify_table(schema, table)}")

            _print_header("Row counts")
            for table in tables:
                query = sql.SQL("SELECT COUNT(*) FROM {}").format(
                    sql.Identifier(*qualify_table(schema, table).split(".")),
                )
                cur.execute(query)
                count = cur.fetchone()[0]
                print(f"  {qualify_table(schema, table)}: {count} rows")

            if tables:
                _print_header("Analytics sample query (sales by region)")
                sample_query = sql.SQL(
                    """
                    SELECT c.region,
                           SUM(o.amount) AS total_sales,
                           COUNT(*) AS order_count
                    FROM {orders} o
                    JOIN {customers} c ON o.customer_id = c.customer_id
                    WHERE o.status = 'completed'
                    GROUP BY c.region
                    ORDER BY total_sales DESC
                    """
                ).format(
                    orders=sql.Identifier(*qualify_table(schema, "orders").split(".")),
                    customers=sql.Identifier(*qualify_table(schema, "customers").split(".")),
                )
                cur.execute(sample_query)
                for region, total_sales, order_count in cur.fetchall():
                    print(f"  {region:8} | sales={total_sales:>12} | orders={order_count}")

    print("\n✓ Warehouse demo check passed.")


async def main() -> None:
    parser = build_warehouse_credentials_parser(
        "Inspect warehouse DB using user-provided credentials",
    )
    parser.add_argument(
        "--data-source-id",
        type=uuid.UUID,
        default=None,
        help="Load credentials from app.data_sources instead of CLI flags",
    )
    args = parser.parse_args()

    if args.data_source_id:
        info = await _load_from_project_db(args.data_source_id)
    else:
        credentials = credentials_from_args(args)
        info = WarehouseConnectionInfo.from_credentials(credentials)

    check_warehouse(info)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as exc:
        print(f"\n✗ Warehouse demo check failed: {exc}", file=sys.stderr)
        sys.exit(1)
