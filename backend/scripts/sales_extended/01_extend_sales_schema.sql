-- Extend existing sales schema (keeps customers / products / orders).
-- Target: any Postgres warehouse. Run via psql (or SQL client) BEFORE seeding.
-- Schema: sales (same as current demo)

CREATE SCHEMA IF NOT EXISTS sales;

-- ---------------------------------------------------------------------------
-- A. Reference / org
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS sales.regions (
    region_id SERIAL PRIMARY KEY,
    code VARCHAR(10) NOT NULL UNIQUE,
    name VARCHAR(100) NOT NULL
);

CREATE TABLE IF NOT EXISTS sales.territories (
    territory_id SERIAL PRIMARY KEY,
    region_id INT NOT NULL REFERENCES sales.regions(region_id),
    code VARCHAR(20) NOT NULL UNIQUE,
    name VARCHAR(100) NOT NULL
);

CREATE TABLE IF NOT EXISTS sales.departments (
    department_id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    cost_center VARCHAR(20)
);

CREATE TABLE IF NOT EXISTS sales.employees (
    employee_id SERIAL PRIMARY KEY,
    department_id INT REFERENCES sales.departments(department_id),
    manager_id INT REFERENCES sales.employees(employee_id),
    first_name VARCHAR(80) NOT NULL,
    last_name VARCHAR(80) NOT NULL,
    email VARCHAR(160) UNIQUE,
    title VARCHAR(60),
    hire_date DATE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS sales.warehouses (
    warehouse_id SERIAL PRIMARY KEY,
    territory_id INT REFERENCES sales.territories(territory_id),
    code VARCHAR(20) NOT NULL UNIQUE,
    name VARCHAR(100) NOT NULL,
    city VARCHAR(80)
);

CREATE TABLE IF NOT EXISTS sales.channels (
    channel_id SERIAL PRIMARY KEY,
    code VARCHAR(30) NOT NULL UNIQUE,
    name VARCHAR(80) NOT NULL
);

CREATE TABLE IF NOT EXISTS sales.currencies (
    currency_code CHAR(3) PRIMARY KEY,
    name VARCHAR(60) NOT NULL,
    symbol VARCHAR(8)
);

CREATE TABLE IF NOT EXISTS sales.order_statuses (
    status_code VARCHAR(30) PRIMARY KEY,
    label VARCHAR(60) NOT NULL,
    is_terminal BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS sales.payment_methods (
    payment_method_id SERIAL PRIMARY KEY,
    code VARCHAR(30) NOT NULL UNIQUE,
    name VARCHAR(80) NOT NULL
);

CREATE TABLE IF NOT EXISTS sales.carriers (
    carrier_id SERIAL PRIMARY KEY,
    code VARCHAR(30) NOT NULL UNIQUE,
    name VARCHAR(100) NOT NULL
);

-- ---------------------------------------------------------------------------
-- B. Catalog & supply
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS sales.categories (
    category_id SERIAL PRIMARY KEY,
    parent_id INT REFERENCES sales.categories(category_id),
    name VARCHAR(100) NOT NULL,
    UNIQUE (parent_id, name)
);

-- Evolve existing products (keep name/category/price columns)
ALTER TABLE sales.products
    ADD COLUMN IF NOT EXISTS category_id INT,
    ADD COLUMN IF NOT EXISTS sku VARCHAR(40),
    ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'products_category_id_fkey'
    ) THEN
        ALTER TABLE sales.products
            ADD CONSTRAINT products_category_id_fkey
            FOREIGN KEY (category_id) REFERENCES sales.categories(category_id);
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS sales.product_variants (
    variant_id SERIAL PRIMARY KEY,
    product_id INT NOT NULL REFERENCES sales.products(product_id),
    sku VARCHAR(40) NOT NULL UNIQUE,
    color VARCHAR(40),
    size VARCHAR(20),
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS sales.product_prices (
    price_id SERIAL PRIMARY KEY,
    variant_id INT NOT NULL REFERENCES sales.product_variants(variant_id),
    currency_code CHAR(3) NOT NULL REFERENCES sales.currencies(currency_code),
    unit_price DECIMAL(12, 2) NOT NULL CHECK (unit_price >= 0),
    effective_from DATE NOT NULL,
    effective_to DATE
);

CREATE TABLE IF NOT EXISTS sales.suppliers (
    supplier_id SERIAL PRIMARY KEY,
    name VARCHAR(120) NOT NULL,
    country VARCHAR(60),
    rating DECIMAL(3, 2)
);

CREATE TABLE IF NOT EXISTS sales.supplier_products (
    supplier_id INT NOT NULL REFERENCES sales.suppliers(supplier_id),
    product_id INT NOT NULL REFERENCES sales.products(product_id),
    supplier_sku VARCHAR(60),
    lead_time_days INT DEFAULT 14,
    PRIMARY KEY (supplier_id, product_id)
);

CREATE TABLE IF NOT EXISTS sales.purchase_orders (
    purchase_order_id SERIAL PRIMARY KEY,
    supplier_id INT NOT NULL REFERENCES sales.suppliers(supplier_id),
    warehouse_id INT REFERENCES sales.warehouses(warehouse_id),
    order_date DATE NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'open',
    total_amount DECIMAL(14, 2) DEFAULT 0
);

CREATE TABLE IF NOT EXISTS sales.purchase_order_lines (
    po_line_id SERIAL PRIMARY KEY,
    purchase_order_id INT NOT NULL REFERENCES sales.purchase_orders(purchase_order_id),
    product_id INT NOT NULL REFERENCES sales.products(product_id),
    qty INT NOT NULL CHECK (qty > 0),
    unit_cost DECIMAL(12, 2) NOT NULL CHECK (unit_cost >= 0)
);

CREATE TABLE IF NOT EXISTS sales.warehouse_inventory (
    warehouse_id INT NOT NULL REFERENCES sales.warehouses(warehouse_id),
    variant_id INT NOT NULL REFERENCES sales.product_variants(variant_id),
    qty_on_hand INT NOT NULL DEFAULT 0,
    qty_reserved INT NOT NULL DEFAULT 0,
    PRIMARY KEY (warehouse_id, variant_id)
);

CREATE TABLE IF NOT EXISTS sales.inventory_movements (
    movement_id BIGSERIAL PRIMARY KEY,
    warehouse_id INT NOT NULL REFERENCES sales.warehouses(warehouse_id),
    variant_id INT NOT NULL REFERENCES sales.product_variants(variant_id),
    employee_id INT REFERENCES sales.employees(employee_id),
    movement_type VARCHAR(30) NOT NULL,
    qty_delta INT NOT NULL,
    moved_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    note TEXT
);

-- ---------------------------------------------------------------------------
-- C. Customers (evolve existing)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS sales.customer_segments (
    segment_id SERIAL PRIMARY KEY,
    code VARCHAR(30) NOT NULL UNIQUE,
    name VARCHAR(80) NOT NULL
);

ALTER TABLE sales.customers
    ADD COLUMN IF NOT EXISTS segment_id INT,
    ADD COLUMN IF NOT EXISTS territory_id INT,
    ADD COLUMN IF NOT EXISTS email VARCHAR(160),
    ADD COLUMN IF NOT EXISTS created_at DATE DEFAULT CURRENT_DATE;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'customers_segment_id_fkey'
    ) THEN
        ALTER TABLE sales.customers
            ADD CONSTRAINT customers_segment_id_fkey
            FOREIGN KEY (segment_id) REFERENCES sales.customer_segments(segment_id);
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'customers_territory_id_fkey'
    ) THEN
        ALTER TABLE sales.customers
            ADD CONSTRAINT customers_territory_id_fkey
            FOREIGN KEY (territory_id) REFERENCES sales.territories(territory_id);
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS sales.customer_addresses (
    address_id SERIAL PRIMARY KEY,
    customer_id INT NOT NULL REFERENCES sales.customers(customer_id),
    address_type VARCHAR(20) NOT NULL DEFAULT 'billing',
    line1 VARCHAR(160) NOT NULL,
    city VARCHAR(80) NOT NULL,
    state VARCHAR(80),
    postal_code VARCHAR(20),
    country VARCHAR(60) NOT NULL DEFAULT 'USA',
    is_primary BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS sales.customer_contacts (
    contact_id SERIAL PRIMARY KEY,
    customer_id INT NOT NULL REFERENCES sales.customers(customer_id),
    full_name VARCHAR(120) NOT NULL,
    email VARCHAR(160),
    phone VARCHAR(40),
    role_title VARCHAR(80)
);

CREATE TABLE IF NOT EXISTS sales.customer_notes (
    note_id SERIAL PRIMARY KEY,
    customer_id INT NOT NULL REFERENCES sales.customers(customer_id),
    employee_id INT REFERENCES sales.employees(employee_id),
    note_text TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS sales.loyalty_accounts (
    loyalty_account_id SERIAL PRIMARY KEY,
    customer_id INT NOT NULL UNIQUE REFERENCES sales.customers(customer_id),
    tier VARCHAR(30) NOT NULL DEFAULT 'bronze',
    points INT NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS sales.loyalty_transactions (
    loyalty_txn_id BIGSERIAL PRIMARY KEY,
    loyalty_account_id INT NOT NULL REFERENCES sales.loyalty_accounts(loyalty_account_id),
    points_delta INT NOT NULL,
    reason VARCHAR(120),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ---------------------------------------------------------------------------
-- D. Orders & fulfillment (evolve existing orders)
-- ---------------------------------------------------------------------------

ALTER TABLE sales.orders
    ADD COLUMN IF NOT EXISTS channel_id INT,
    ADD COLUMN IF NOT EXISTS sales_rep_id INT,
    ADD COLUMN IF NOT EXISTS warehouse_id INT,
    ADD COLUMN IF NOT EXISTS currency_code CHAR(3),
    ADD COLUMN IF NOT EXISTS order_number VARCHAR(40);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'orders_channel_id_fkey'
    ) THEN
        ALTER TABLE sales.orders
            ADD CONSTRAINT orders_channel_id_fkey
            FOREIGN KEY (channel_id) REFERENCES sales.channels(channel_id);
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'orders_sales_rep_id_fkey'
    ) THEN
        ALTER TABLE sales.orders
            ADD CONSTRAINT orders_sales_rep_id_fkey
            FOREIGN KEY (sales_rep_id) REFERENCES sales.employees(employee_id);
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'orders_warehouse_id_fkey'
    ) THEN
        ALTER TABLE sales.orders
            ADD CONSTRAINT orders_warehouse_id_fkey
            FOREIGN KEY (warehouse_id) REFERENCES sales.warehouses(warehouse_id);
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'orders_currency_code_fkey'
    ) THEN
        ALTER TABLE sales.orders
            ADD CONSTRAINT orders_currency_code_fkey
            FOREIGN KEY (currency_code) REFERENCES sales.currencies(currency_code);
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS sales.order_lines (
    order_line_id BIGSERIAL PRIMARY KEY,
    order_id INT NOT NULL REFERENCES sales.orders(order_id) ON DELETE CASCADE,
    variant_id INT REFERENCES sales.product_variants(variant_id),
    product_id INT REFERENCES sales.products(product_id),
    qty INT NOT NULL CHECK (qty > 0),
    unit_price DECIMAL(12, 2) NOT NULL CHECK (unit_price >= 0),
    line_amount DECIMAL(14, 2) NOT NULL CHECK (line_amount >= 0)
);

CREATE TABLE IF NOT EXISTS sales.order_status_history (
    history_id BIGSERIAL PRIMARY KEY,
    order_id INT NOT NULL REFERENCES sales.orders(order_id) ON DELETE CASCADE,
    status_code VARCHAR(30) NOT NULL REFERENCES sales.order_statuses(status_code),
    changed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    changed_by INT REFERENCES sales.employees(employee_id)
);

CREATE TABLE IF NOT EXISTS sales.payments (
    payment_id BIGSERIAL PRIMARY KEY,
    order_id INT NOT NULL REFERENCES sales.orders(order_id),
    payment_method_id INT REFERENCES sales.payment_methods(payment_method_id),
    amount DECIMAL(14, 2) NOT NULL CHECK (amount >= 0),
    paid_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    status VARCHAR(30) NOT NULL DEFAULT 'captured'
);

CREATE TABLE IF NOT EXISTS sales.refunds (
    refund_id BIGSERIAL PRIMARY KEY,
    payment_id BIGINT NOT NULL REFERENCES sales.payments(payment_id),
    amount DECIMAL(14, 2) NOT NULL CHECK (amount >= 0),
    reason VARCHAR(160),
    refunded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS sales.shipments (
    shipment_id BIGSERIAL PRIMARY KEY,
    order_id INT NOT NULL REFERENCES sales.orders(order_id),
    warehouse_id INT REFERENCES sales.warehouses(warehouse_id),
    carrier_id INT REFERENCES sales.carriers(carrier_id),
    tracking_number VARCHAR(60),
    shipped_at TIMESTAMPTZ,
    delivered_at TIMESTAMPTZ,
    status VARCHAR(30) NOT NULL DEFAULT 'pending'
);

CREATE TABLE IF NOT EXISTS sales.shipment_lines (
    shipment_line_id BIGSERIAL PRIMARY KEY,
    shipment_id BIGINT NOT NULL REFERENCES sales.shipments(shipment_id) ON DELETE CASCADE,
    order_line_id BIGINT REFERENCES sales.order_lines(order_line_id),
    qty INT NOT NULL CHECK (qty > 0)
);

CREATE TABLE IF NOT EXISTS sales.returns (
    return_id BIGSERIAL PRIMARY KEY,
    order_id INT NOT NULL REFERENCES sales.orders(order_id),
    customer_id INT NOT NULL REFERENCES sales.customers(customer_id),
    requested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    status VARCHAR(30) NOT NULL DEFAULT 'requested',
    reason VARCHAR(160)
);

CREATE TABLE IF NOT EXISTS sales.return_lines (
    return_line_id BIGSERIAL PRIMARY KEY,
    return_id BIGINT NOT NULL REFERENCES sales.returns(return_id) ON DELETE CASCADE,
    order_line_id BIGINT REFERENCES sales.order_lines(order_line_id),
    qty INT NOT NULL CHECK (qty > 0)
);

-- ---------------------------------------------------------------------------
-- E. Marketing & support
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS sales.campaigns (
    campaign_id SERIAL PRIMARY KEY,
    name VARCHAR(120) NOT NULL,
    channel_primary VARCHAR(40),
    start_date DATE,
    end_date DATE,
    budget DECIMAL(14, 2) DEFAULT 0,
    status VARCHAR(30) NOT NULL DEFAULT 'active'
);

CREATE TABLE IF NOT EXISTS sales.campaign_channels (
    campaign_id INT NOT NULL REFERENCES sales.campaigns(campaign_id),
    channel_id INT NOT NULL REFERENCES sales.channels(channel_id),
    PRIMARY KEY (campaign_id, channel_id)
);

CREATE TABLE IF NOT EXISTS sales.campaign_touches (
    touch_id BIGSERIAL PRIMARY KEY,
    campaign_id INT NOT NULL REFERENCES sales.campaigns(campaign_id),
    customer_id INT NOT NULL REFERENCES sales.customers(customer_id),
    touched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    touch_type VARCHAR(40) NOT NULL DEFAULT 'email'
);

CREATE TABLE IF NOT EXISTS sales.coupons (
    coupon_id SERIAL PRIMARY KEY,
    code VARCHAR(40) NOT NULL UNIQUE,
    campaign_id INT REFERENCES sales.campaigns(campaign_id),
    discount_pct DECIMAL(5, 2),
    discount_amount DECIMAL(12, 2),
    active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS sales.coupon_redemptions (
    redemption_id BIGSERIAL PRIMARY KEY,
    coupon_id INT NOT NULL REFERENCES sales.coupons(coupon_id),
    order_id INT NOT NULL REFERENCES sales.orders(order_id),
    customer_id INT NOT NULL REFERENCES sales.customers(customer_id),
    redeemed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS sales.order_discounts (
    order_discount_id BIGSERIAL PRIMARY KEY,
    order_id INT NOT NULL REFERENCES sales.orders(order_id),
    coupon_id INT REFERENCES sales.coupons(coupon_id),
    discount_amount DECIMAL(12, 2) NOT NULL CHECK (discount_amount >= 0)
);

CREATE TABLE IF NOT EXISTS sales.ticket_categories (
    ticket_category_id SERIAL PRIMARY KEY,
    name VARCHAR(80) NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS sales.tickets (
    ticket_id BIGSERIAL PRIMARY KEY,
    customer_id INT NOT NULL REFERENCES sales.customers(customer_id),
    ticket_category_id INT REFERENCES sales.ticket_categories(ticket_category_id),
    assignee_id INT REFERENCES sales.employees(employee_id),
    subject VARCHAR(200) NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'open',
    priority VARCHAR(20) NOT NULL DEFAULT 'medium',
    opened_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    closed_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS sales.ticket_messages (
    message_id BIGSERIAL PRIMARY KEY,
    ticket_id BIGINT NOT NULL REFERENCES sales.tickets(ticket_id) ON DELETE CASCADE,
    employee_id INT REFERENCES sales.employees(employee_id),
    is_from_customer BOOLEAN NOT NULL DEFAULT FALSE,
    body TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ---------------------------------------------------------------------------
-- F. Finance
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS sales.invoices (
    invoice_id BIGSERIAL PRIMARY KEY,
    order_id INT REFERENCES sales.orders(order_id),
    customer_id INT NOT NULL REFERENCES sales.customers(customer_id),
    invoice_number VARCHAR(40) NOT NULL UNIQUE,
    issued_at DATE NOT NULL,
    due_at DATE,
    status VARCHAR(30) NOT NULL DEFAULT 'open',
    total_amount DECIMAL(14, 2) NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS sales.invoice_lines (
    invoice_line_id BIGSERIAL PRIMARY KEY,
    invoice_id BIGINT NOT NULL REFERENCES sales.invoices(invoice_id) ON DELETE CASCADE,
    order_line_id BIGINT REFERENCES sales.order_lines(order_line_id),
    description VARCHAR(200),
    amount DECIMAL(14, 2) NOT NULL CHECK (amount >= 0)
);

CREATE TABLE IF NOT EXISTS sales.ledger_accounts (
    account_id SERIAL PRIMARY KEY,
    code VARCHAR(20) NOT NULL UNIQUE,
    name VARCHAR(100) NOT NULL,
    account_type VARCHAR(30) NOT NULL
);

CREATE TABLE IF NOT EXISTS sales.ledger_entries (
    entry_id BIGSERIAL PRIMARY KEY,
    account_id INT NOT NULL REFERENCES sales.ledger_accounts(account_id),
    invoice_id BIGINT REFERENCES sales.invoices(invoice_id),
    entry_date DATE NOT NULL,
    debit DECIMAL(14, 2) NOT NULL DEFAULT 0,
    credit DECIMAL(14, 2) NOT NULL DEFAULT 0,
    memo VARCHAR(200)
);

CREATE TABLE IF NOT EXISTS sales.exchange_rates (
    rate_id SERIAL PRIMARY KEY,
    currency_code CHAR(3) NOT NULL REFERENCES sales.currencies(currency_code),
    rate_date DATE NOT NULL,
    rate_to_usd DECIMAL(18, 8) NOT NULL,
    UNIQUE (currency_code, rate_date)
);

-- ---------------------------------------------------------------------------
-- Indexes for analytics joins
-- ---------------------------------------------------------------------------

CREATE INDEX IF NOT EXISTS idx_territories_region ON sales.territories(region_id);
CREATE INDEX IF NOT EXISTS idx_employees_dept ON sales.employees(department_id);
CREATE INDEX IF NOT EXISTS idx_variants_product ON sales.product_variants(product_id);
CREATE INDEX IF NOT EXISTS idx_order_lines_order ON sales.order_lines(order_id);
CREATE INDEX IF NOT EXISTS idx_order_lines_product ON sales.order_lines(product_id);
CREATE INDEX IF NOT EXISTS idx_payments_order ON sales.payments(order_id);
CREATE INDEX IF NOT EXISTS idx_shipments_order ON sales.shipments(order_id);
CREATE INDEX IF NOT EXISTS idx_campaign_touches_customer ON sales.campaign_touches(customer_id);
CREATE INDEX IF NOT EXISTS idx_tickets_customer ON sales.tickets(customer_id);
CREATE INDEX IF NOT EXISTS idx_invoices_customer ON sales.invoices(customer_id);
CREATE INDEX IF NOT EXISTS idx_customers_segment ON sales.customers(segment_id);
CREATE INDEX IF NOT EXISTS idx_customers_territory ON sales.customers(territory_id);
CREATE INDEX IF NOT EXISTS idx_orders_channel ON sales.orders(channel_id);
CREATE INDEX IF NOT EXISTS idx_orders_rep ON sales.orders(sales_rep_id);

-- ---------------------------------------------------------------------------
-- Grants (run as a privileged role; tighten to a readonly user in production)
-- ---------------------------------------------------------------------------

GRANT USAGE ON SCHEMA sales TO PUBLIC;
GRANT SELECT ON ALL TABLES IN SCHEMA sales TO PUBLIC;
ALTER DEFAULT PRIVILEGES IN SCHEMA sales GRANT SELECT ON TABLES TO PUBLIC;
