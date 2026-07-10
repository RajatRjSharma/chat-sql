-- Warehouse database initialization (bi_warehouse)
-- Managed via SQL script — not ORM. Run: make warehouse-init

CREATE SCHEMA IF NOT EXISTS sales;

CREATE TABLE IF NOT EXISTS sales.customers (
    customer_id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    region VARCHAR(50) NOT NULL
);

CREATE TABLE IF NOT EXISTS sales.products (
    product_id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    category VARCHAR(50) NOT NULL,
    price DECIMAL(10, 2) NOT NULL CHECK (price >= 0)
);

CREATE TABLE IF NOT EXISTS sales.orders (
    order_id SERIAL PRIMARY KEY,
    customer_id INT NOT NULL REFERENCES sales.customers(customer_id),
    product_id INT NOT NULL REFERENCES sales.products(product_id),
    amount DECIMAL(10, 2) NOT NULL CHECK (amount >= 0),
    order_date DATE NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'completed'
);

CREATE INDEX IF NOT EXISTS idx_orders_order_date ON sales.orders(order_date);
CREATE INDEX IF NOT EXISTS idx_orders_status ON sales.orders(status);
CREATE INDEX IF NOT EXISTS idx_customers_region ON sales.customers(region);
CREATE INDEX IF NOT EXISTS idx_products_category ON sales.products(category);

DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'bi_readonly') THEN
        CREATE ROLE bi_readonly LOGIN PASSWORD 'readonly_pass';
    END IF;
END
$$;

GRANT CONNECT ON DATABASE bi_warehouse TO bi_readonly;
GRANT USAGE ON SCHEMA sales TO bi_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA sales TO bi_readonly;
ALTER DEFAULT PRIVILEGES IN SCHEMA sales GRANT SELECT ON TABLES TO bi_readonly;
