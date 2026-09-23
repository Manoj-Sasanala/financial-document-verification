CREATE TABLE IF NOT EXISTS customers (
    customer_id TEXT PRIMARY KEY,
    customer_name TEXT NOT NULL,
    address TEXT NOT NULL,
    postal_code TEXT NOT NULL
);