#!/usr/bin/env python3
"""Register a warehouse connection in the project database (CLI equivalent of the connect API)."""

from __future__ import annotations

import argparse
import asyncio
import sys
import uuid

import scripts._bootstrap  # noqa: F401
from app.database import AsyncSessionLocal
from app.schemas.data_source import WarehouseConnectRequest
from app.services.data_source_service import DataSourceService
from scripts._credentials_cli import build_warehouse_credentials_parser

DEMO_SOURCE_ID = uuid.UUID("00000000-0000-4000-8000-000000000001")


def _request_from_args(args: argparse.Namespace) -> WarehouseConnectRequest:
    return WarehouseConnectRequest(
        name=args.name,
        host=args.host,
        port=args.port,
        database=args.database,
        schema_name=args.schema or None,
        username=args.username,
        password=args.password,
        is_readonly=True,
    )


async def seed_data_source(args: argparse.Namespace) -> uuid.UUID:
    request = _request_from_args(args)
    user_id = uuid.UUID(args.user_id)

    async with AsyncSessionLocal() as session:
        response = await DataSourceService.connect(
            session,
            request,
            user_id=user_id,
            data_source_id=DEMO_SOURCE_ID,
        )
        await session.commit()
        print(f"✓ Registered data source: {response.name} ({response.data_source_id})")
        location = (
            f"{response.host}:{response.port}/{response.database}"
            if response.schema_name is None
            else f"{response.host}:{response.port}/{response.database}.{response.schema_name}"
        )
        print(f"  {location}")
        return response.data_source_id


async def main() -> None:
    parser = build_warehouse_credentials_parser(
        "Register user warehouse credentials in app.data_sources",
    )
    parser.add_argument(
        "--user-id",
        required=True,
        help="Owner user UUID (register via /api/auth first)",
    )
    args = parser.parse_args()
    await seed_data_source(args)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as exc:
        print(f"✗ App seed failed: {exc}", file=sys.stderr)
        sys.exit(1)
