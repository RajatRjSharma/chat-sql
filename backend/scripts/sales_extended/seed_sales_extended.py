#!/usr/bin/env python3
"""Seed extended sales demo data into the existing sales schema (Postgres).

Run AFTER 01_extend_sales_schema.sql.

Default: additive (fills dims, updates null FKs, backfills related rows).
Use --reset to truncate extended child tables before re-seeding (keeps
customers / products / orders rows).
"""

from __future__ import annotations

import argparse
import random
import sys
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import psycopg2
from psycopg2.extras import execute_values

import scripts._bootstrap  # noqa: F401
from scripts._credentials_cli import (
    admin_connection_url,
    build_warehouse_credentials_parser,
)

# ---------------------------------------------------------------------------
# Static reference data
# ---------------------------------------------------------------------------

REGIONS = [
    ("N", "North"),
    ("S", "South"),
    ("E", "East"),
    ("W", "West"),
]

TERRITORIES = [
    ("N", "N-NE", "Northeast"),
    ("N", "N-MW", "Midwest"),
    ("S", "S-SE", "Southeast"),
    ("S", "S-SW", "Southwest"),
    ("E", "E-AT", "Atlantic"),
    ("W", "W-PC", "Pacific"),
]

DEPARTMENTS = [
    ("Sales", "CC-100"),
    ("Support", "CC-200"),
    ("Warehouse", "CC-300"),
    ("Marketing", "CC-400"),
    ("Finance", "CC-500"),
]

CHANNELS = [
    ("web", "Web Store"),
    ("retail", "Retail"),
    ("partner", "Partner"),
    ("phone", "Phone Sales"),
    ("marketplace", "Marketplace"),
]

CURRENCIES = [
    ("USD", "US Dollar", "$"),
    ("EUR", "Euro", "€"),
    ("GBP", "British Pound", "£"),
    ("CAD", "Canadian Dollar", "C$"),
]

ORDER_STATUSES = [
    ("pending", "Pending", False),
    ("processing", "Processing", False),
    ("shipped", "Shipped", False),
    ("completed", "Completed", True),
    ("cancelled", "Cancelled", True),
    ("returned", "Returned", True),
]

PAYMENT_METHODS = [
    ("card", "Credit Card"),
    ("ach", "ACH Transfer"),
    ("paypal", "PayPal"),
    ("invoice", "Net-30 Invoice"),
]

CARRIERS = [
    ("ups", "UPS"),
    ("fedex", "FedEx"),
    ("usps", "USPS"),
    ("dhl", "DHL"),
]

SEGMENTS = [
    ("enterprise", "Enterprise"),
    ("smb", "SMB"),
    ("startup", "Startup"),
    ("consumer", "Consumer"),
]

CATEGORY_TREE = [
    (None, "Electronics"),
    (None, "Clothing"),
    (None, "Food"),
    (None, "Home"),
    (None, "Sports"),
    ("Electronics", "Computers"),
    ("Electronics", "Audio"),
    ("Clothing", "Outerwear"),
    ("Sports", "Fitness"),
]

FIRST_NAMES = [
    "Alex", "Jordan", "Sam", "Taylor", "Casey", "Riley", "Morgan", "Quinn",
    "Avery", "Cameron", "Drew", "Jamie", "Parker", "Reese", "Skyler",
]
LAST_NAMES = [
    "Nguyen", "Patel", "Garcia", "Kim", "Smith", "Chen", "Brown", "Davis",
    "Wilson", "Martinez", "Lee", "Anderson", "Thomas", "Jackson", "White",
]

EXTRA_CUSTOMERS = [
    ("Initech West", "West"),
    ("Blue Sun Corp", "South"),
    ("Rekall Inc", "East"),
    ("Nakatomi Trading", "West"),
    ("Buy n Large", "North"),
    ("Monsters Inc", "East"),
    ("Vandelay Industries", "North"),
    ("Prestige Worldwide", "South"),
    ("Sterling Cooper", "East"),
    ("Bluth Company", "West"),
    ("Dunder Mifflin Scranton", "North"),
    ("Paper Street Soap", "East"),
    ("Los Pollos Hermanos", "South"),
    ("Central Perk LLC", "East"),
    ("Gekko & Co", "West"),
]

EXTRA_PRODUCTS = [
    ("USB-C Hub", "Electronics", "39.99"),
    ("Noise Cancelling Buds", "Electronics", "179.99"),
    ("Merino Sweater", "Clothing", "89.99"),
    ("Trail Running Pack", "Sports", "64.99"),
    ("Cast Iron Skillet", "Home", "54.99"),
    ("Green Tea Bundle", "Food", "22.99"),
    ("Standing Desk Mat", "Home", "44.99"),
    ("Cycling Helmet", "Sports", "79.99"),
    ("Linen Shirt", "Clothing", "49.99"),
    ("Portable SSD 1TB", "Electronics", "109.99"),
]

TICKET_CATEGORIES = [
    "Shipping delay",
    "Wrong item",
    "Billing question",
    "Product defect",
    "Account access",
]

LEDGER_ACCOUNTS = [
    ("1000", "Cash", "asset"),
    ("1100", "Accounts Receivable", "asset"),
    ("2000", "Accounts Payable", "liability"),
    ("4000", "Product Revenue", "revenue"),
    ("5000", "COGS", "expense"),
]

SUPPLIER_NAMES = [
    ("Northwind Supply", "USA", Decimal("4.50")),
    ("Pacific Components", "Taiwan", Decimal("4.20")),
    ("Alpine Textiles", "Italy", Decimal("4.70")),
    ("Harvest Foods Co", "USA", Decimal("4.10")),
    ("Metro Logistics Parts", "Germany", Decimal("3.90")),
]

CITIES = [
    ("New York", "NY", "10001"),
    ("Chicago", "IL", "60601"),
    ("Austin", "TX", "78701"),
    ("Seattle", "WA", "98101"),
    ("Atlanta", "GA", "30301"),
    ("Denver", "CO", "80202"),
]


def _q(schema: str, table: str) -> str:
    if not schema.replace("_", "").isalnum() or not table.replace("_", "").isalnum():
        raise ValueError(f"Invalid identifier: {schema}.{table}")
    return f'"{schema}"."{table}"'


def _ids(cur, sql: str, params=None) -> list:
    cur.execute(sql, params or ())
    return [r[0] for r in cur.fetchall()]


def _id_map(cur, sql: str, params=None) -> dict:
    cur.execute(sql, params or ())
    return {r[0]: r[1] for r in cur.fetchall()}


def _connection_url(args: argparse.Namespace) -> str:
    if args.database_url:
        return args.database_url
    return admin_connection_url(args)


def _truncate_extended(cur, schema: str) -> None:
    """Wipe extended tables only; keep customers / products / orders."""
    tables = [
        "ledger_entries",
        "invoice_lines",
        "invoices",
        "ticket_messages",
        "tickets",
        "ticket_categories",
        "order_discounts",
        "coupon_redemptions",
        "coupons",
        "campaign_touches",
        "campaign_channels",
        "campaigns",
        "return_lines",
        "returns",
        "shipment_lines",
        "shipments",
        "refunds",
        "payments",
        "order_status_history",
        "order_lines",
        "loyalty_transactions",
        "loyalty_accounts",
        "customer_notes",
        "customer_contacts",
        "customer_addresses",
        "inventory_movements",
        "warehouse_inventory",
        "purchase_order_lines",
        "purchase_orders",
        "supplier_products",
        "suppliers",
        "product_prices",
        "product_variants",
        "exchange_rates",
        "ledger_accounts",
        "carriers",
        "payment_methods",
        "order_statuses",
        "currencies",
        "channels",
        "warehouses",
        "employees",
        "departments",
        "customer_segments",
        "categories",
        "territories",
        "regions",
    ]
    joined = ", ".join(_q(schema, t) for t in tables)
    cur.execute(f"TRUNCATE {joined} RESTART IDENTITY CASCADE")
    # Clear FK columns on base tables
    cur.execute(
        f"""
        UPDATE {_q(schema, "customers")}
        SET segment_id = NULL, territory_id = NULL, email = NULL
        """
    )
    cur.execute(
        f"""
        UPDATE {_q(schema, "products")}
        SET category_id = NULL, sku = NULL
        """
    )
    cur.execute(
        f"""
        UPDATE {_q(schema, "orders")}
        SET channel_id = NULL, sales_rep_id = NULL, warehouse_id = NULL,
            currency_code = NULL, order_number = NULL
        """
    )


def seed(args: argparse.Namespace) -> None:
    schema = args.schema or "sales"
    random.seed(args.seed)
    url = _connection_url(args)

    with psycopg2.connect(url) as conn:
        with conn.cursor() as cur:
            if args.reset:
                print("Resetting extended tables (keeping customers/products/orders)...")
                _truncate_extended(cur, schema)

            # ---- Reference dims ----
            execute_values(
                cur,
                f"INSERT INTO {_q(schema, 'regions')} (code, name) VALUES %s "
                f"ON CONFLICT (code) DO NOTHING",
                REGIONS,
            )
            region_by_code = _id_map(cur, f"SELECT code, region_id FROM {_q(schema, 'regions')}")

            territory_rows = [
                (region_by_code[rc], code, name) for rc, code, name in TERRITORIES if rc in region_by_code
            ]
            execute_values(
                cur,
                f"INSERT INTO {_q(schema, 'territories')} (region_id, code, name) VALUES %s "
                f"ON CONFLICT (code) DO NOTHING",
                territory_rows,
            )
            territory_ids = _ids(cur, f"SELECT territory_id FROM {_q(schema, 'territories')}")

            execute_values(
                cur,
                f"INSERT INTO {_q(schema, 'departments')} (name, cost_center) VALUES %s "
                f"ON CONFLICT (name) DO NOTHING",
                DEPARTMENTS,
            )
            dept_ids = _ids(cur, f"SELECT department_id FROM {_q(schema, 'departments')}")

            cur.execute(f"SELECT COUNT(*) FROM {_q(schema, 'employees')}")
            if cur.fetchone()[0] == 0:
                emp_rows = []
                for i in range(40):
                    fn = random.choice(FIRST_NAMES)
                    ln = random.choice(LAST_NAMES)
                    emp_rows.append(
                        (
                            random.choice(dept_ids),
                            fn,
                            ln,
                            f"{fn.lower()}.{ln.lower()}{i}@demo.local",
                            random.choice(["Rep", "Manager", "Specialist", "Associate"]),
                            date(2018, 1, 1) + timedelta(days=random.randint(0, 2500)),
                            True,
                        )
                    )
                execute_values(
                    cur,
                    f"INSERT INTO {_q(schema, 'employees')} "
                    f"(department_id, first_name, last_name, email, title, hire_date, is_active) "
                    f"VALUES %s",
                    emp_rows,
                )
                # Assign a few managers
                emp_ids = _ids(cur, f"SELECT employee_id FROM {_q(schema, 'employees')}")
                managers = emp_ids[:8]
                for eid in emp_ids[8:]:
                    cur.execute(
                        f"UPDATE {_q(schema, 'employees')} SET manager_id = %s WHERE employee_id = %s",
                        (random.choice(managers), eid),
                    )

            employee_ids = _ids(cur, f"SELECT employee_id FROM {_q(schema, 'employees')}")
            sales_reps = employee_ids[:20]

            wh_codes = [("WH-NY", "New York DC", "New York"), ("WH-TX", "Dallas DC", "Dallas"),
                        ("WH-CA", "Los Angeles DC", "Los Angeles"), ("WH-IL", "Chicago DC", "Chicago")]
            for i, (code, name, city) in enumerate(wh_codes):
                tid = territory_ids[i % len(territory_ids)] if territory_ids else None
                cur.execute(
                    f"INSERT INTO {_q(schema, 'warehouses')} (territory_id, code, name, city) "
                    f"VALUES (%s, %s, %s, %s) ON CONFLICT (code) DO NOTHING",
                    (tid, code, name, city),
                )
            warehouse_ids = _ids(cur, f"SELECT warehouse_id FROM {_q(schema, 'warehouses')}")

            execute_values(
                cur,
                f"INSERT INTO {_q(schema, 'channels')} (code, name) VALUES %s ON CONFLICT (code) DO NOTHING",
                CHANNELS,
            )
            channel_ids = _ids(cur, f"SELECT channel_id FROM {_q(schema, 'channels')}")

            execute_values(
                cur,
                f"INSERT INTO {_q(schema, 'currencies')} (currency_code, name, symbol) VALUES %s "
                f"ON CONFLICT (currency_code) DO NOTHING",
                CURRENCIES,
            )

            execute_values(
                cur,
                f"INSERT INTO {_q(schema, 'order_statuses')} (status_code, label, is_terminal) VALUES %s "
                f"ON CONFLICT (status_code) DO NOTHING",
                ORDER_STATUSES,
            )

            execute_values(
                cur,
                f"INSERT INTO {_q(schema, 'payment_methods')} (code, name) VALUES %s "
                f"ON CONFLICT (code) DO NOTHING",
                PAYMENT_METHODS,
            )
            payment_method_ids = _ids(cur, f"SELECT payment_method_id FROM {_q(schema, 'payment_methods')}")

            execute_values(
                cur,
                f"INSERT INTO {_q(schema, 'carriers')} (code, name) VALUES %s ON CONFLICT (code) DO NOTHING",
                CARRIERS,
            )
            carrier_ids = _ids(cur, f"SELECT carrier_id FROM {_q(schema, 'carriers')}")

            execute_values(
                cur,
                f"INSERT INTO {_q(schema, 'customer_segments')} (code, name) VALUES %s "
                f"ON CONFLICT (code) DO NOTHING",
                SEGMENTS,
            )
            segment_ids = _ids(cur, f"SELECT segment_id FROM {_q(schema, 'customer_segments')}")

            # Categories (parents then children) — NULL parents need EXISTS checks
            for parent_name, name in CATEGORY_TREE:
                if parent_name is None:
                    cur.execute(
                        f"INSERT INTO {_q(schema, 'categories')} (parent_id, name) "
                        f"SELECT NULL, %s WHERE NOT EXISTS ("
                        f"  SELECT 1 FROM {_q(schema, 'categories')} WHERE parent_id IS NULL AND name = %s"
                        f")",
                        (name, name),
                    )
            cat_by_name = _id_map(cur, f"SELECT name, category_id FROM {_q(schema, 'categories')}")
            for parent_name, name in CATEGORY_TREE:
                if parent_name is not None and parent_name in cat_by_name:
                    cur.execute(
                        f"INSERT INTO {_q(schema, 'categories')} (parent_id, name) "
                        f"SELECT %s, %s WHERE NOT EXISTS ("
                        f"  SELECT 1 FROM {_q(schema, 'categories')} WHERE parent_id = %s AND name = %s"
                        f")",
                        (cat_by_name[parent_name], name, cat_by_name[parent_name], name),
                    )
            cat_by_name = _id_map(cur, f"SELECT name, category_id FROM {_q(schema, 'categories')}")

            execute_values(
                cur,
                f"INSERT INTO {_q(schema, 'ticket_categories')} (name) VALUES %s ON CONFLICT (name) DO NOTHING",
                [(n,) for n in TICKET_CATEGORIES],
            )
            ticket_cat_ids = _ids(cur, f"SELECT ticket_category_id FROM {_q(schema, 'ticket_categories')}")

            execute_values(
                cur,
                f"INSERT INTO {_q(schema, 'ledger_accounts')} (code, name, account_type) VALUES %s "
                f"ON CONFLICT (code) DO NOTHING",
                LEDGER_ACCOUNTS,
            )
            ledger_ids = _ids(cur, f"SELECT account_id FROM {_q(schema, 'ledger_accounts')}")

            # ---- Ensure base customers / products volume ----
            cur.execute(f"SELECT COUNT(*) FROM {_q(schema, 'customers')}")
            if cur.fetchone()[0] == 0:
                raise RuntimeError(
                    "sales.customers is empty. Run the base warehouse seed first "
                    "(make warehouse-seed) or insert customers, then re-run this script."
                )

            # Add extra customers if requested / sparse
            cur.execute(f"SELECT COUNT(*) FROM {_q(schema, 'customers')}")
            cust_count = cur.fetchone()[0]
            if cust_count < 30:
                execute_values(
                    cur,
                    f"INSERT INTO {_q(schema, 'customers')} (name, region) VALUES %s",
                    EXTRA_CUSTOMERS,
                )

            cur.execute(f"SELECT COUNT(*) FROM {_q(schema, 'products')}")
            if cur.fetchone()[0] < 20:
                execute_values(
                    cur,
                    f"INSERT INTO {_q(schema, 'products')} (name, category, price) VALUES %s",
                    EXTRA_PRODUCTS,
                )

            # Link customers → segment / territory / email
            cur.execute(
                f"SELECT customer_id, name, region FROM {_q(schema, 'customers')} "
                f"WHERE segment_id IS NULL OR territory_id IS NULL OR email IS NULL"
            )
            for cid, name, region in cur.fetchall():
                slug = "".join(c for c in name.lower() if c.isalnum())[:24]
                sid = random.choice(segment_ids)
                # Prefer territory matching region letter if possible
                tid = random.choice(territory_ids)
                cur.execute(
                    f"UPDATE {_q(schema, 'customers')} "
                    f"SET segment_id = COALESCE(segment_id, %s), "
                    f"territory_id = COALESCE(territory_id, %s), "
                    f"email = COALESCE(email, %s), "
                    f"created_at = COALESCE(created_at, %s) "
                    f"WHERE customer_id = %s",
                    (
                        sid,
                        tid,
                        f"{slug}@customer.demo",
                        date(2023, 1, 1) + timedelta(days=random.randint(0, 700)),
                        cid,
                    ),
                )

            customer_ids = _ids(cur, f"SELECT customer_id FROM {_q(schema, 'customers')}")

            # Customer addresses / contacts / loyalty (idempotent-ish: only if none)
            cur.execute(f"SELECT COUNT(*) FROM {_q(schema, 'customer_addresses')}")
            if cur.fetchone()[0] == 0:
                addr_rows = []
                contact_rows = []
                for cid in customer_ids:
                    city, state, zipc = random.choice(CITIES)
                    addr_rows.append(
                        (cid, "billing", f"{random.randint(100, 9999)} Main St", city, state, zipc, "USA", True)
                    )
                    if random.random() < 0.5:
                        city2, state2, zip2 = random.choice(CITIES)
                        addr_rows.append(
                            (cid, "shipping", f"{random.randint(100, 9999)} Oak Ave", city2, state2, zip2, "USA", False)
                        )
                    contact_rows.append(
                        (
                            cid,
                            f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}",
                            f"contact{cid}@demo.local",
                            f"+1-555-{random.randint(1000, 9999)}",
                            random.choice(["Buyer", "AP", "Ops"]),
                        )
                    )
                execute_values(
                    cur,
                    f"INSERT INTO {_q(schema, 'customer_addresses')} "
                    f"(customer_id, address_type, line1, city, state, postal_code, country, is_primary) VALUES %s",
                    addr_rows,
                )
                execute_values(
                    cur,
                    f"INSERT INTO {_q(schema, 'customer_contacts')} "
                    f"(customer_id, full_name, email, phone, role_title) VALUES %s",
                    contact_rows,
                )

            cur.execute(f"SELECT COUNT(*) FROM {_q(schema, 'loyalty_accounts')}")
            if cur.fetchone()[0] == 0:
                loyalty_rows = [
                    (cid, random.choice(["bronze", "silver", "gold", "platinum"]), random.randint(0, 5000))
                    for cid in customer_ids
                ]
                execute_values(
                    cur,
                    f"INSERT INTO {_q(schema, 'loyalty_accounts')} (customer_id, tier, points) VALUES %s",
                    loyalty_rows,
                )
                loyalty_ids = _ids(cur, f"SELECT loyalty_account_id FROM {_q(schema, 'loyalty_accounts')}")
                txn_rows = []
                for lid in loyalty_ids:
                    for _ in range(random.randint(1, 4)):
                        txn_rows.append(
                            (lid, random.choice([-50, 25, 50, 100, 200]), random.choice(["order", "bonus", "redeem"]))
                        )
                execute_values(
                    cur,
                    f"INSERT INTO {_q(schema, 'loyalty_transactions')} "
                    f"(loyalty_account_id, points_delta, reason) VALUES %s",
                    txn_rows,
                )

            # Notes
            cur.execute(f"SELECT COUNT(*) FROM {_q(schema, 'customer_notes')}")
            if cur.fetchone()[0] == 0:
                note_rows = [
                    (
                        random.choice(customer_ids),
                        random.choice(employee_ids),
                        random.choice(
                            [
                                "Prefers email follow-up",
                                "High-touch enterprise account",
                                "Asked about volume discount",
                                "Seasonal buyer — Q4 spike",
                            ]
                        ),
                    )
                    for _ in range(min(80, len(customer_ids) * 2))
                ]
                execute_values(
                    cur,
                    f"INSERT INTO {_q(schema, 'customer_notes')} (customer_id, employee_id, note_text) VALUES %s",
                    note_rows,
                )

            # ---- Products → categories / SKU / variants ----
            cur.execute(f"SELECT product_id, name, category, price FROM {_q(schema, 'products')}")
            products = cur.fetchall()
            for pid, pname, pcat, price in products:
                cat_id = cat_by_name.get(pcat) or cat_by_name.get("Electronics")
                sku = f"SKU-{pid:04d}"
                cur.execute(
                    f"UPDATE {_q(schema, 'products')} "
                    f"SET category_id = COALESCE(category_id, %s), "
                    f"sku = COALESCE(sku, %s), "
                    f"is_active = COALESCE(is_active, TRUE) "
                    f"WHERE product_id = %s",
                    (cat_id, sku, pid),
                )

            cur.execute(f"SELECT COUNT(*) FROM {_q(schema, 'product_variants')}")
            if cur.fetchone()[0] == 0:
                colors = ["Black", "White", "Navy", "Gray", None]
                sizes = ["S", "M", "L", "XL", None]
                variant_rows = []
                for pid, pname, pcat, price in products:
                    n_var = random.randint(1, 3)
                    for v in range(n_var):
                        variant_rows.append(
                            (
                                pid,
                                f"VAR-{pid:04d}-{v+1}",
                                random.choice(colors),
                                random.choice(sizes),
                                True,
                            )
                        )
                execute_values(
                    cur,
                    f"INSERT INTO {_q(schema, 'product_variants')} "
                    f"(product_id, sku, color, size, is_active) VALUES %s",
                    variant_rows,
                )

            cur.execute(
                f"SELECT v.variant_id, p.price FROM {_q(schema, 'product_variants')} v "
                f"JOIN {_q(schema, 'products')} p ON p.product_id = v.product_id"
            )
            variant_price = cur.fetchall()

            cur.execute(f"SELECT COUNT(*) FROM {_q(schema, 'product_prices')}")
            if cur.fetchone()[0] == 0:
                price_rows = [
                    (vid, "USD", Decimal(str(price)), date(2024, 1, 1), None)
                    for vid, price in variant_price
                ]
                execute_values(
                    cur,
                    f"INSERT INTO {_q(schema, 'product_prices')} "
                    f"(variant_id, currency_code, unit_price, effective_from, effective_to) VALUES %s",
                    price_rows,
                )

            variant_ids = [v for v, _ in variant_price]
            product_ids = [p[0] for p in products]
            product_price = {p[0]: Decimal(str(p[3])) for p in products}

            # Suppliers
            cur.execute(f"SELECT COUNT(*) FROM {_q(schema, 'suppliers')}")
            if cur.fetchone()[0] == 0:
                execute_values(
                    cur,
                    f"INSERT INTO {_q(schema, 'suppliers')} (name, country, rating) VALUES %s",
                    SUPPLIER_NAMES,
                )
                supplier_ids = _ids(cur, f"SELECT supplier_id FROM {_q(schema, 'suppliers')}")
                sp_rows = []
                for pid in product_ids:
                    for sid in random.sample(supplier_ids, k=min(2, len(supplier_ids))):
                        sp_rows.append((sid, pid, f"SUP-{sid}-{pid}", random.randint(7, 45)))
                execute_values(
                    cur,
                    f"INSERT INTO {_q(schema, 'supplier_products')} "
                    f"(supplier_id, product_id, supplier_sku, lead_time_days) VALUES %s",
                    sp_rows,
                )
                po_rows = []
                for _ in range(30):
                    po_rows.append(
                        (
                            random.choice(supplier_ids),
                            random.choice(warehouse_ids),
                            date(2024, 1, 1) + timedelta(days=random.randint(0, 500)),
                            random.choice(["open", "received", "cancelled"]),
                            Decimal(str(round(random.uniform(500, 20000), 2))),
                        )
                    )
                execute_values(
                    cur,
                    f"INSERT INTO {_q(schema, 'purchase_orders')} "
                    f"(supplier_id, warehouse_id, order_date, status, total_amount) VALUES %s",
                    po_rows,
                )
                po_ids = _ids(cur, f"SELECT purchase_order_id FROM {_q(schema, 'purchase_orders')}")
                pol_rows = []
                for poid in po_ids:
                    for _ in range(random.randint(1, 4)):
                        pid = random.choice(product_ids)
                        pol_rows.append(
                            (poid, pid, random.randint(10, 200), product_price[pid] * Decimal("0.55"))
                        )
                execute_values(
                    cur,
                    f"INSERT INTO {_q(schema, 'purchase_order_lines')} "
                    f"(purchase_order_id, product_id, qty, unit_cost) VALUES %s",
                    pol_rows,
                )

            # Inventory
            cur.execute(f"SELECT COUNT(*) FROM {_q(schema, 'warehouse_inventory')}")
            if cur.fetchone()[0] == 0 and warehouse_ids and variant_ids:
                inv_rows = []
                for wid in warehouse_ids:
                    for vid in variant_ids:
                        inv_rows.append((wid, vid, random.randint(0, 500), random.randint(0, 50)))
                execute_values(
                    cur,
                    f"INSERT INTO {_q(schema, 'warehouse_inventory')} "
                    f"(warehouse_id, variant_id, qty_on_hand, qty_reserved) VALUES %s",
                    inv_rows,
                )
                mov_rows = [
                    (
                        random.choice(warehouse_ids),
                        random.choice(variant_ids),
                        random.choice(employee_ids),
                        random.choice(["receive", "ship", "adjust"]),
                        random.choice([-20, -10, -5, 5, 10, 25, 50]),
                        datetime.now(UTC) - timedelta(days=random.randint(0, 200)),
                        "demo movement",
                    )
                    for _ in range(400)
                ]
                execute_values(
                    cur,
                    f"INSERT INTO {_q(schema, 'inventory_movements')} "
                    f"(warehouse_id, variant_id, employee_id, movement_type, qty_delta, moved_at, note) VALUES %s",
                    mov_rows,
                )

            # Exchange rates
            cur.execute(f"SELECT COUNT(*) FROM {_q(schema, 'exchange_rates')}")
            if cur.fetchone()[0] == 0:
                rates = {"USD": Decimal("1.0"), "EUR": Decimal("1.08"), "GBP": Decimal("1.27"), "CAD": Decimal("0.74")}
                rate_rows = []
                for i in range(0, 365, 7):
                    d = date(2024, 1, 1) + timedelta(days=i)
                    for code, base in rates.items():
                        jitter = Decimal(str(round(random.uniform(-0.02, 0.02), 4)))
                        rate_rows.append((code, d, max(Decimal("0.01"), base + jitter)))
                execute_values(
                    cur,
                    f"INSERT INTO {_q(schema, 'exchange_rates')} (currency_code, rate_date, rate_to_usd) VALUES %s "
                    f"ON CONFLICT (currency_code, rate_date) DO NOTHING",
                    rate_rows,
                )

            # Campaigns / coupons
            cur.execute(f"SELECT COUNT(*) FROM {_q(schema, 'campaigns')}")
            if cur.fetchone()[0] == 0:
                camp_rows = [
                    ("Spring Launch", "email", date(2024, 3, 1), date(2024, 4, 30), Decimal("25000"), "completed"),
                    ("Summer Clearance", "web", date(2024, 6, 1), date(2024, 7, 31), Decimal("18000"), "completed"),
                    ("Holiday Push", "marketplace", date(2024, 11, 1), date(2024, 12, 31), Decimal("50000"), "active"),
                    ("Partner Promo", "partner", date(2025, 1, 1), date(2025, 3, 31), Decimal("12000"), "active"),
                    ("Winback Q2", "email", date(2025, 4, 1), date(2025, 5, 31), Decimal("9000"), "planned"),
                ]
                execute_values(
                    cur,
                    f"INSERT INTO {_q(schema, 'campaigns')} "
                    f"(name, channel_primary, start_date, end_date, budget, status) VALUES %s",
                    camp_rows,
                )
                campaign_ids = _ids(cur, f"SELECT campaign_id FROM {_q(schema, 'campaigns')}")
                cc_rows = [(cid, random.choice(channel_ids)) for cid in campaign_ids]
                # unique pairs
                cc_rows = list({(c, ch) for c, ch in cc_rows})
                execute_values(
                    cur,
                    f"INSERT INTO {_q(schema, 'campaign_channels')} (campaign_id, channel_id) VALUES %s "
                    f"ON CONFLICT DO NOTHING",
                    cc_rows,
                )
                touch_rows = [
                    (
                        random.choice(campaign_ids),
                        random.choice(customer_ids),
                        datetime.now(UTC) - timedelta(days=random.randint(0, 400)),
                        random.choice(["email", "ad", "sms", "call"]),
                    )
                    for _ in range(min(600, len(customer_ids) * 15))
                ]
                execute_values(
                    cur,
                    f"INSERT INTO {_q(schema, 'campaign_touches')} "
                    f"(campaign_id, customer_id, touched_at, touch_type) VALUES %s",
                    touch_rows,
                )
                coupon_rows = [
                    ("SPRING10", campaign_ids[0], Decimal("10.00"), None, True),
                    ("SUMMER15", campaign_ids[1], Decimal("15.00"), None, True),
                    ("HOLIDAY25", campaign_ids[2], None, Decimal("25.00"), True),
                    ("PARTNER5", campaign_ids[3], Decimal("5.00"), None, True),
                    ("WELCOME20", None, Decimal("20.00"), None, True),
                ]
                execute_values(
                    cur,
                    f"INSERT INTO {_q(schema, 'coupons')} "
                    f"(code, campaign_id, discount_pct, discount_amount, active) VALUES %s",
                    coupon_rows,
                )
            coupon_ids = _ids(cur, f"SELECT coupon_id FROM {_q(schema, 'coupons')}")
            campaign_ids = _ids(cur, f"SELECT campaign_id FROM {_q(schema, 'campaigns')}")

            # ---- Orders: enrich + optional extra volume ----
            status_map = {
                "completed": "completed",
                "pending": "pending",
                "cancelled": "cancelled",
            }

            if args.extra_orders > 0:
                cur.execute(f"SELECT product_id, price FROM {_q(schema, 'products')}")
                product_rows = cur.fetchall()
                start = date(2024, 1, 1)
                new_orders = []
                for _ in range(args.extra_orders):
                    cid = random.choice(customer_ids)
                    pid, price = random.choice(product_rows)
                    qty = random.randint(1, 4)
                    amount = Decimal(str(price)) * qty
                    od = start + timedelta(days=random.randint(0, 540))
                    st = random.choice(["completed", "completed", "completed", "pending", "cancelled"])
                    new_orders.append((cid, pid, amount, od, st))
                execute_values(
                    cur,
                    f"INSERT INTO {_q(schema, 'orders')} "
                    f"(customer_id, product_id, amount, order_date, status) VALUES %s",
                    new_orders,
                )
                print(f"  + inserted {len(new_orders)} extra orders")

            # Enrich order FK columns
            cur.execute(
                f"SELECT order_id, status FROM {_q(schema, 'orders')} "
                f"WHERE channel_id IS NULL OR sales_rep_id IS NULL"
            )
            for oid, st in cur.fetchall():
                cur.execute(
                    f"UPDATE {_q(schema, 'orders')} SET "
                    f"channel_id = COALESCE(channel_id, %s), "
                    f"sales_rep_id = COALESCE(sales_rep_id, %s), "
                    f"warehouse_id = COALESCE(warehouse_id, %s), "
                    f"currency_code = COALESCE(currency_code, 'USD'), "
                    f"order_number = COALESCE(order_number, %s) "
                    f"WHERE order_id = %s",
                    (
                        random.choice(channel_ids),
                        random.choice(sales_reps),
                        random.choice(warehouse_ids),
                        f"ORD-{oid:06d}",
                        oid,
                    ),
                )

            # Backfill order_lines from denormalized orders
            cur.execute(
                f"""
                SELECT o.order_id, o.product_id, o.amount
                FROM {_q(schema, "orders")} o
                WHERE NOT EXISTS (
                    SELECT 1 FROM {_q(schema, "order_lines")} ol WHERE ol.order_id = o.order_id
                )
                """
            )
            missing = cur.fetchall()
            if missing:
                # map product -> one variant
                cur.execute(
                    f"SELECT DISTINCT ON (product_id) product_id, variant_id "
                    f"FROM {_q(schema, 'product_variants')} ORDER BY product_id, variant_id"
                )
                prod_variant = dict(cur.fetchall())
                line_rows = []
                for oid, pid, amount in missing:
                    vid = prod_variant.get(pid)
                    unit = Decimal(str(amount))
                    qty = 1
                    # try to split amount into qty * unit using product price
                    pprice = product_price.get(pid, unit)
                    if pprice > 0 and amount >= pprice:
                        qty = max(1, int(amount / pprice))
                        unit = (amount / qty).quantize(Decimal("0.01"))
                    line_rows.append((oid, vid, pid, qty, unit, Decimal(str(amount))))
                execute_values(
                    cur,
                    f"INSERT INTO {_q(schema, 'order_lines')} "
                    f"(order_id, variant_id, product_id, qty, unit_price, line_amount) VALUES %s",
                    line_rows,
                )
                print(f"  + backfilled {len(line_rows)} order_lines")

            # Related transactional tables (only if empty)
            cur.execute(f"SELECT COUNT(*) FROM {_q(schema, 'payments')}")
            if cur.fetchone()[0] == 0:
                cur.execute(
                    f"SELECT order_id, customer_id, amount, order_date, status "
                    f"FROM {_q(schema, 'orders')}"
                )
                all_orders = cur.fetchall()
                # sample for heavy child tables to keep seed fast on large DBs
                sample = all_orders if len(all_orders) <= 2000 else random.sample(all_orders, 2000)

                # status history
                hist_rows = []
                for oid, _cid, _amt, od, st in sample:
                    mapped = status_map.get(st, "completed")
                    hist_rows.append(
                        (
                            oid,
                            "pending",
                            datetime.combine(od, datetime.min.time()).replace(tzinfo=UTC),
                            random.choice(employee_ids),
                        )
                    )
                    if mapped != "pending":
                        hist_rows.append(
                            (
                                oid,
                                mapped,
                                datetime.combine(od + timedelta(days=1), datetime.min.time()).replace(
                                    tzinfo=UTC
                                ),
                                random.choice(employee_ids),
                            )
                        )
                execute_values(
                    cur,
                    f"INSERT INTO {_q(schema, 'order_status_history')} "
                    f"(order_id, status_code, changed_at, changed_by) VALUES %s",
                    hist_rows,
                )

                pay_rows = []
                for oid, _cid, amt, od, st in sample:
                    if st == "cancelled":
                        continue
                    pay_rows.append(
                        (
                            oid,
                            random.choice(payment_method_ids),
                            Decimal(str(amt)),
                            datetime.combine(od, datetime.min.time()).replace(tzinfo=UTC)
                            + timedelta(hours=random.randint(1, 48)),
                            "captured",
                        )
                    )
                execute_values(
                    cur,
                    f"INSERT INTO {_q(schema, 'payments')} "
                    f"(order_id, payment_method_id, amount, paid_at, status) VALUES %s",
                    pay_rows,
                )
                payment_ids = _ids(cur, f"SELECT payment_id FROM {_q(schema, 'payments')}")
                refund_sample = random.sample(payment_ids, k=min(40, len(payment_ids)))
                refund_rows = [
                    (pid, Decimal(str(round(random.uniform(10, 80), 2))), "partial return")
                    for pid in refund_sample
                ]
                if refund_rows:
                    execute_values(
                        cur,
                        f"INSERT INTO {_q(schema, 'refunds')} (payment_id, amount, reason) VALUES %s",
                        refund_rows,
                    )

                # Shipments for completed-ish orders
                cur.execute(
                    f"SELECT ol.order_line_id, ol.order_id, ol.qty FROM {_q(schema, 'order_lines')} ol"
                )
                lines_by_order: dict[int, list] = {}
                for olid, oid, qty in cur.fetchall():
                    lines_by_order.setdefault(oid, []).append((olid, qty))

                ship_meta = []
                for oid, cid, amt, od, st in sample:
                    if st == "cancelled":
                        continue
                    shipped = od + timedelta(days=random.randint(1, 5))
                    delivered = shipped + timedelta(days=random.randint(1, 7)) if st == "completed" else None
                    ship_meta.append(
                        (
                            oid,
                            random.choice(warehouse_ids),
                            random.choice(carrier_ids),
                            f"TRK{oid:08d}",
                            datetime.combine(shipped, datetime.min.time()).replace(tzinfo=UTC),
                            datetime.combine(delivered, datetime.min.time()).replace(tzinfo=UTC)
                            if delivered
                            else None,
                            "delivered" if delivered else "shipped",
                        )
                    )
                if ship_meta:
                    execute_values(
                        cur,
                        f"INSERT INTO {_q(schema, 'shipments')} "
                        f"(order_id, warehouse_id, carrier_id, tracking_number, shipped_at, delivered_at, status) "
                        f"VALUES %s",
                        ship_meta,
                    )
                cur.execute(f"SELECT shipment_id, order_id FROM {_q(schema, 'shipments')}")
                shipments = cur.fetchall()
                sl_rows = []
                for sid, oid in shipments:
                    for olid, qty in lines_by_order.get(oid, [])[:2]:
                        sl_rows.append((sid, olid, qty))
                if sl_rows:
                    execute_values(
                        cur,
                        f"INSERT INTO {_q(schema, 'shipment_lines')} (shipment_id, order_line_id, qty) VALUES %s",
                        sl_rows,
                    )

                # Returns (~5%)
                ret_candidates = [o for o in sample if o[4] == "completed"]
                ret_pick = random.sample(ret_candidates, k=min(max(1, len(ret_candidates) // 20), 80))
                ret_rows = [
                    (
                        oid,
                        cid,
                        datetime.combine(od + timedelta(days=random.randint(5, 30)), datetime.min.time()).replace(
                            tzinfo=UTC
                        ),
                        random.choice(["requested", "approved", "refunded"]),
                        random.choice(["damaged", "wrong size", "changed mind"]),
                    )
                    for oid, cid, amt, od, st in ret_pick
                ]
                if ret_rows:
                    execute_values(
                        cur,
                        f"INSERT INTO {_q(schema, 'returns')} "
                        f"(order_id, customer_id, requested_at, status, reason) VALUES %s",
                        ret_rows,
                    )
                    cur.execute(f"SELECT return_id, order_id FROM {_q(schema, 'returns')}")
                    rl_rows = []
                    for rid, oid in cur.fetchall():
                        lines = lines_by_order.get(oid) or []
                        if lines:
                            olid, qty = lines[0]
                            rl_rows.append((rid, olid, max(1, qty // 2 or 1)))
                    if rl_rows:
                        execute_values(
                            cur,
                            f"INSERT INTO {_q(schema, 'return_lines')} (return_id, order_line_id, qty) VALUES %s",
                            rl_rows,
                        )

                # Coupons on ~15% of orders
                if coupon_ids:
                    redeem_rows = []
                    discount_rows = []
                    for oid, cid, amt, od, st in sample:
                        if random.random() > 0.15 or st == "cancelled":
                            continue
                        cpn = random.choice(coupon_ids)
                        disc = min(Decimal(str(amt)) * Decimal("0.1"), Decimal("50.00")).quantize(Decimal("0.01"))
                        redeem_rows.append(
                            (
                                cpn,
                                oid,
                                cid,
                                datetime.combine(od, datetime.min.time()).replace(tzinfo=UTC),
                            )
                        )
                        discount_rows.append((oid, cpn, disc))
                    if redeem_rows:
                        execute_values(
                            cur,
                            f"INSERT INTO {_q(schema, 'coupon_redemptions')} "
                            f"(coupon_id, order_id, customer_id, redeemed_at) VALUES %s",
                            redeem_rows,
                        )
                        execute_values(
                            cur,
                            f"INSERT INTO {_q(schema, 'order_discounts')} "
                            f"(order_id, coupon_id, discount_amount) VALUES %s",
                            discount_rows,
                        )

                # Invoices + ledger
                inv_rows = []
                for oid, cid, amt, od, st in sample:
                    if st == "cancelled":
                        continue
                    inv_rows.append(
                        (
                            oid,
                            cid,
                            f"INV-{oid:06d}",
                            od,
                            od + timedelta(days=30),
                            "paid" if st == "completed" else "open",
                            Decimal(str(amt)),
                        )
                    )
                execute_values(
                    cur,
                    f"INSERT INTO {_q(schema, 'invoices')} "
                    f"(order_id, customer_id, invoice_number, issued_at, due_at, status, total_amount) VALUES %s",
                    inv_rows,
                )
                cur.execute(
                    f"SELECT i.invoice_id, i.order_id, i.total_amount FROM {_q(schema, 'invoices')} i"
                )
                invoices = cur.fetchall()
                il_rows = []
                le_rows = []
                rev_acct = ledger_ids[3] if len(ledger_ids) > 3 else ledger_ids[0]
                ar_acct = ledger_ids[1] if len(ledger_ids) > 1 else ledger_ids[0]
                for iid, oid, total in invoices:
                    lines = lines_by_order.get(oid) or []
                    if lines:
                        for olid, _qty in lines[:3]:
                            il_rows.append((iid, olid, "Order line", (total / max(1, len(lines))).quantize(Decimal("0.01"))))
                    else:
                        il_rows.append((iid, None, "Order total", total))
                    le_rows.append((ar_acct, iid, date(2024, 1, 1), total, Decimal("0"), "AR"))
                    le_rows.append((rev_acct, iid, date(2024, 1, 1), Decimal("0"), total, "Revenue"))
                if il_rows:
                    execute_values(
                        cur,
                        f"INSERT INTO {_q(schema, 'invoice_lines')} "
                        f"(invoice_id, order_line_id, description, amount) VALUES %s",
                        il_rows,
                    )
                execute_values(
                    cur,
                    f"INSERT INTO {_q(schema, 'ledger_entries')} "
                    f"(account_id, invoice_id, entry_date, debit, credit, memo) VALUES %s",
                    le_rows,
                )

                # Support tickets
                ticket_rows = [
                    (
                        random.choice(customer_ids),
                        random.choice(ticket_cat_ids),
                        random.choice(employee_ids),
                        random.choice(
                            [
                                "Where is my order?",
                                "Invoice discrepancy",
                                "Damaged shipment",
                                "Need quote for bulk",
                                "Login issue on portal",
                            ]
                        ),
                        random.choice(["open", "open", "pending", "closed"]),
                        random.choice(["low", "medium", "high"]),
                        datetime.now(UTC) - timedelta(days=random.randint(0, 300)),
                    )
                    for _ in range(120)
                ]
                # add closed_at for closed
                ticket_insert = []
                for row in ticket_rows:
                    closed = row[6] + timedelta(days=random.randint(1, 10)) if row[4] == "closed" else None
                    ticket_insert.append(row + (closed,))
                execute_values(
                    cur,
                    f"INSERT INTO {_q(schema, 'tickets')} "
                    f"(customer_id, ticket_category_id, assignee_id, subject, status, priority, opened_at, closed_at) "
                    f"VALUES %s",
                    ticket_insert,
                )
                ticket_ids = _ids(cur, f"SELECT ticket_id FROM {_q(schema, 'tickets')}")
                msg_rows = []
                for tid in ticket_ids:
                    msg_rows.append(
                        (tid, None, True, "Customer: I need help with my recent order.", datetime.now(UTC))
                    )
                    msg_rows.append(
                        (
                            tid,
                            random.choice(employee_ids),
                            False,
                            "Agent: Thanks for reaching out — looking into this now.",
                            datetime.now(UTC),
                        )
                    )
                execute_values(
                    cur,
                    f"INSERT INTO {_q(schema, 'ticket_messages')} "
                    f"(ticket_id, employee_id, is_from_customer, body, created_at) VALUES %s",
                    msg_rows,
                )

            # Counts
            cur.execute(
                f"""
                SELECT
                  (SELECT COUNT(*) FROM {_q(schema, "customers")}),
                  (SELECT COUNT(*) FROM {_q(schema, "products")}),
                  (SELECT COUNT(*) FROM {_q(schema, "orders")}),
                  (SELECT COUNT(*) FROM {_q(schema, "order_lines")}),
                  (SELECT COUNT(*) FROM information_schema.tables
                     WHERE table_schema = %s AND table_type = 'BASE TABLE')
                """,
                (schema,),
            )
            n_cust, n_prod, n_ord, n_lines, n_tables = cur.fetchone()

        conn.commit()

    print(f"✓ Extended sales seed complete → schema={schema}")
    print(f"  tables≈{n_tables} customers={n_cust} products={n_prod} orders={n_ord} order_lines={n_lines}")
    print("  Next: reconnect the app datasource and re-run schema embed.")


def main() -> None:
    parser = build_warehouse_credentials_parser(
        "Seed extended sales demo tables (same sales schema)"
    )
    parser.add_argument(
        "--database-url",
        default="",
        help="Full Postgres URL (overrides host/port/user).",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Truncate extended tables first (keeps customers/products/orders rows)",
    )
    parser.add_argument(
        "--extra-orders",
        type=int,
        default=500,
        help="Insert this many additional orders (default 500). Use 0 to skip.",
    )
    parser.add_argument("--seed", type=int, default=42, help="RNG seed")
    # Prefer sales schema + postgres admin for this script
    parser.set_defaults(schema="sales", username="postgres", admin_username="postgres")
    args = parser.parse_args()
    try:
        seed(args)
    except Exception as exc:
        print(f"✗ Extended seed failed: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
