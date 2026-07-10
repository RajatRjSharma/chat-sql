#!/usr/bin/env python3
"""Seed demo sales data into a user-specified warehouse database."""

from __future__ import annotations

import argparse
import random
import sys
from datetime import date, timedelta
from decimal import Decimal

import psycopg2
from psycopg2.extras import execute_values

import scripts._bootstrap  # noqa: F401
from scripts._credentials_cli import (
    admin_connection_url,
    build_warehouse_credentials_parser,
    credentials_from_args,
)
from app.warehouse import qualify_table

REGIONS = ("North", "South", "East", "West")
CATEGORIES = ("Electronics", "Clothing", "Food", "Home", "Sports")
STATUSES = ("completed", "completed", "completed", "pending", "cancelled")

CUSTOMERS = [
    ("Acme Corp", "North"),
    ("Globex Inc", "South"),
    ("Initech", "East"),
    ("Umbrella LLC", "West"),
    ("Stark Industries", "North"),
    ("Wayne Enterprises", "East"),
    ("Wonka Foods", "South"),
    ("Hooli", "West"),
    ("Pied Piper", "North"),
    ("Massive Dynamic", "East"),
    ("Cyberdyne", "West"),
    ("Soylent Co", "South"),
    ("Gringotts", "North"),
    ("Octan Corp", "East"),
    ("Tyrell Corp", "West"),
    ("Aperture Science", "North"),
    ("Vault-Tec", "South"),
    ("Oscorp", "East"),
    ("LexCorp", "West"),
    ("Dunder Mifflin", "North"),
]

PRODUCTS = [
    ("Laptop Pro", "Electronics", "1299.99"),
    ("Wireless Mouse", "Electronics", "49.99"),
    ("4K Monitor", "Electronics", "399.99"),
    ("Winter Jacket", "Clothing", "129.99"),
    ("Running Shoes", "Sports", "89.99"),
    ("Organic Coffee", "Food", "14.99"),
    ("Desk Lamp", "Home", "39.99"),
    ("Bluetooth Speaker", "Electronics", "79.99"),
    ("Yoga Mat", "Sports", "29.99"),
    ("Ceramic Mug Set", "Home", "24.99"),
    ("Protein Bars (12pk)", "Food", "19.99"),
    ("Denim Jeans", "Clothing", "59.99"),
    ("Gaming Headset", "Electronics", "149.99"),
    ("Tennis Racket", "Sports", "119.99"),
    ("Smart Watch", "Electronics", "249.99"),
]


def _qualified(schema: str | None, table: str) -> str:
    if not table.replace("_", "").isalnum():
        raise ValueError(f"Invalid table name: {table!r}")
    return qualify_table(schema, table)


def seed(args: argparse.Namespace) -> None:
    credentials = credentials_from_args(args)
    schema = credentials.schema_name
    admin_url = admin_connection_url(args)
    random.seed(42)

    customers_table = _qualified(schema, "customers")
    products_table = _qualified(schema, "products")
    orders_table = _qualified(schema, "orders")

    with psycopg2.connect(admin_url) as conn:
        with conn.cursor() as cur:
            cur.execute(f"TRUNCATE {orders_table}, {products_table}, {customers_table} RESTART IDENTITY CASCADE")

            execute_values(
                cur,
                f"INSERT INTO {customers_table} (name, region) VALUES %s",
                CUSTOMERS,
            )
            execute_values(
                cur,
                f"INSERT INTO {products_table} (name, category, price) VALUES %s",
                PRODUCTS,
            )

            cur.execute(f"SELECT customer_id FROM {customers_table}")
            customer_ids = [row[0] for row in cur.fetchall()]
            cur.execute(f"SELECT product_id, price FROM {products_table}")
            product_rows = cur.fetchall()

            start_date = date(2024, 1, 1)
            order_rows: list[tuple[int, int, Decimal, date, str]] = []

            for _ in range(800):
                customer_id = random.choice(customer_ids)
                product_id, price = random.choice(product_rows)
                qty = random.randint(1, 3)
                amount = Decimal(str(price)) * qty
                order_date = start_date + timedelta(days=random.randint(0, 540))
                status = random.choice(STATUSES)
                order_rows.append((customer_id, product_id, amount, order_date, status))

            execute_values(
                cur,
                f"INSERT INTO {orders_table} (customer_id, product_id, amount, order_date, status) VALUES %s",
                order_rows,
            )
        conn.commit()

    print(f"✓ Seeded warehouse: {credentials.host}:{credentials.port}/{credentials.database}.{schema}")
    print(f"  customers={len(CUSTOMERS)} products={len(PRODUCTS)} orders={len(order_rows)}")


if __name__ == "__main__":
    parser = build_warehouse_credentials_parser("Seed demo sales data into a warehouse DB")
    cli_args = parser.parse_args()
    try:
        seed(cli_args)
    except Exception as exc:
        print(f"✗ Seed failed: {exc}", file=sys.stderr)
        sys.exit(1)
