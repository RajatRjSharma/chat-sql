# Extended `sales` schema (Postgres)

Adds ~47 related tables **into the existing `sales` schema** (keeps `customers`, `products`, `orders`), wires FKs, and seeds join-friendly demo data.

Works against any Postgres warehouse that already has the base `sales` tables.

Architecture / join linking: [docs/architecture.md](../../../docs/architecture.md)

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

FK edges in this schema are what the app’s **FK neighborhood expand** walks after cosine RAG — so multi-table demo questions work more reliably after you re-index.

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

### 3) App reconnect + refresh schema index

1. In the app, connect to the same warehouse (`schema=sales`).
2. On connect, embed runs automatically; if already connected, use **Refresh schema index** in the Evidence panel.
   Indexing also profiles tables (row counts, date min/max, measure ranges, top categorical values) into
   `data_sources.extra_config.data_profile` and injects that into SQL prompts — so relative time asks
   (“last 12 months”) follow **observed** date windows on fact tables, not wall-clock `CURRENT_DATE`
   when the warehouse clock is ahead of the data.
3. Try join questions, e.g. revenue by channel + segment, tickets by customer, campaign touches → orders.

### Demo prompts that exercise linking + charts

| Ask | What you should see |
|-----|---------------------|
| `Show total order revenue by territory and sales channel.` | Dense grid → **heatmap** (or grouped if dims collapse) |
| `What is total revenue by customer segment and sales channel?` | Multi-join → grouped/stacked |
| `Monthly revenue by sales channel for the last 12 months.` | Time × series → **multi-line** |
| `For each order, show invoice total vs payment total.` | Row-level 2 measures → **scatter** |
| `What is total revenue by region and channel?` | Prefer `orders.amount` + `customers → territories → regions` (not `regions.code = customers.region`) |

**Region tip:** `customers.region` stores names (`North`); `regions.code` stores short codes (`N`). Join via `territories` / `regions.name`, never code-to-name.

Re-indexing also stores structured `foreign_keys` in chunk metadata (content FK lines still work for older embeddings).

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
