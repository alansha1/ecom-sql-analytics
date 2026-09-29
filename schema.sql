-- ============================================================
-- E-Commerce Customer Analytics — Database Schema
-- ============================================================

CREATE TABLE IF NOT EXISTS customers (
    customer_id   TEXT PRIMARY KEY,
    first_name    TEXT NOT NULL,
    last_name     TEXT NOT NULL,
    segment       TEXT NOT NULL,          -- 'B2B', 'B2C', 'Enterprise'
    region        TEXT NOT NULL,          -- 'Dublin', 'Cork', etc.
    channel       TEXT NOT NULL,          -- acquisition channel
    acquired_date TEXT NOT NULL           -- ISO date YYYY-MM-DD
);

CREATE TABLE IF NOT EXISTS products (
    product_id    TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    category      TEXT NOT NULL,
    unit_price    REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS orders (
    order_id      TEXT PRIMARY KEY,
    customer_id   TEXT NOT NULL REFERENCES customers(customer_id),
    order_date    TEXT NOT NULL,          -- ISO date YYYY-MM-DD
    status        TEXT NOT NULL           -- 'Completed', 'Refunded', 'Pending'
);

CREATE TABLE IF NOT EXISTS order_items (
    item_id       TEXT PRIMARY KEY,
    order_id      TEXT NOT NULL REFERENCES orders(order_id),
    product_id    TEXT NOT NULL REFERENCES products(product_id),
    quantity      INTEGER NOT NULL,
    unit_price    REAL NOT NULL           -- price at time of purchase
);
