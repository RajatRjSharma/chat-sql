# Extended `sales` schema (Postgres)

Adds ~47 related tables **into the existing `sales` schema** (keeps `customers`, `products`, `orders`), wires FKs, and seeds join-friendly demo data.

Works against any Postgres warehouse that already has the base `sales` tables.

## What you get

| Area | Tables (examples) |
|------|-------------------|
| Org / geo | `regions`, `territories`, `departments`, `employees`, `warehouses`, `channels` |
| Catalog | `categories`, `product_variants`, `product_prices`, `suppliers`, inventory… |
| Customers | `customer_segments`, addresses, contacts, loyalty… |
| Orders | `order_lines`, payments, shipments, returns, status history… |
| Marketing | `campaigns`, coupons, touches… |
| Support / finance | `tickets`, `invoices`, `ledger_entries`, `exchange_rates` |

Existing tables are **altered** (nullable FKs): `customers.segment_id`, `products.category_id`, `orders.channel_id`, etc. Old columns (`region`, `category`, `product_id` on orders) stay for compatibility.

## Steps

### 1) Apply schema

```bash
psql "$DATABASE_URL" -f backend/scripts/sales_extended/01_extend_sales_schema.sql
```

Or paste `01_extend_sales_schema.sql` into your Postgres SQL client and run it.

### 2) Seed data

From the project root (needs backend venv + `psycopg2`):

```bash
# Full connection URL
cd backend && PYTHONPATH=. .venv/bin/python scripts/sales_extended/seed_sales_extended.py \
  --database-url "postgresql://USER:PASSWORD@HOST:5432/DATABASE" \
  --schema sales \
  --extra-orders 500

# Or host/port style (Makefile defaults to local Docker warehouse)
make warehouse-seed-extended \
  DEMO_WH_HOST=HOST \
  DEMO_WH_PORT=5432 \
  DEMO_WH_DATABASE=DATABASE \
  DEMO_WH_ADMIN_USER=USER \
  DEMO_WH_ADMIN_PASSWORD='PASSWORD'
```

Flags:

- `--reset` — truncate **extended** tables only, then re-seed (keeps existing `customers` / `products` / `orders` rows)
- `--extra-orders N` — add N more orders (default `500`; use `0` to only enrich existing rows)
- Requires base `sales.customers` (and ideally products/orders) already present

### 3) App reconnect + re-embed

1. In the app, connect to the same warehouse (`schema=sales`).
2. Run **embed schema** again so RAG sees the new tables.
3. Try join questions, e.g. revenue by channel, tickets by segment, campaign touches → orders.

## Local Docker warehouse

```bash
make warehouse-init          # base 3 tables (if needed)
make warehouse-seed          # base customers/products/orders
make warehouse-extend        # apply 01_extend_sales_schema.sql into warehouse_db
make warehouse-seed-extended # seed related data
```

## Safety notes

- Everything lives in **`sales`** — no new schema.
- `--reset` does **not** delete `customers` / `products` / `orders`; it clears child/dim tables and nulls the new FK columns on those three.
- Do not commit secrets; pass DB password via env/CLI only.
