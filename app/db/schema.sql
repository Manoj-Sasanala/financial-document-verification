CREATE TABLE IF NOT EXISTS customers (
    customer_id TEXT PRIMARY KEY,
    customer_name TEXT NOT NULL,
    address TEXT NOT NULL,
    postal_code TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS cases (
    case_id TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL,
    original_filename TEXT NOT NULL,
    content_type TEXT NOT NULL,
    status TEXT NOT NULL CHECK (
        status IN (
            'processing',
            'completed',
            'completed_with_warnings',
            'failed'
        )
    ),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    review_decision TEXT CHECK (
        review_decision IS NULL OR review_decision IN (
            'approve',
            'reject',
            'request_information'
        )
    ),
    review_comment TEXT,
    reviewed_at TEXT,
    FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
);

CREATE INDEX IF NOT EXISTS idx_cases_customer_id
    ON cases(customer_id);