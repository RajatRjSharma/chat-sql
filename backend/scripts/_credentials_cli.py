"""Shared CLI helpers for warehouse credentials used by development scripts."""

from __future__ import annotations

import argparse

from app.schemas.data_source import WarehouseConnectRequest
from app.warehouse import WarehouseCredentials


def build_warehouse_credentials_parser(description: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--name", default="Demo Sales Warehouse", help="Display name")
    parser.add_argument("--host", default="localhost", help="Warehouse DB host")
    parser.add_argument("--port", type=int, default=5433, help="Warehouse DB port")
    parser.add_argument("--database", default="bi_warehouse", help="Warehouse database name")
    parser.add_argument(
        "--schema",
        default="",
        help="Schema to query (optional — PostgreSQL default if empty)",
    )
    parser.add_argument("--username", default="bi_readonly", help="Read-only DB user")
    parser.add_argument("--password", default="readonly_pass", help="DB password")
    parser.add_argument(
        "--admin-username",
        default="postgres",
        help="Admin user (seed scripts only — not stored)",
    )
    parser.add_argument(
        "--admin-password",
        default="postgres",
        help="Admin password (seed scripts only — not stored)",
    )
    return parser


def credentials_from_args(args: argparse.Namespace) -> WarehouseCredentials:
    request = WarehouseConnectRequest(
        name=args.name,
        host=args.host,
        port=args.port,
        database=args.database,
        schema_name=args.schema or None,
        username=args.username,
        password=args.password,
        is_readonly=True,
    )
    return WarehouseCredentials.from_request(request)


def admin_connection_url(args: argparse.Namespace) -> str:
    from urllib.parse import quote_plus

    user = quote_plus(args.admin_username)
    password = quote_plus(args.admin_password)
    return f"postgresql://{user}:{password}@{args.host}:{args.port}/{args.database}"
