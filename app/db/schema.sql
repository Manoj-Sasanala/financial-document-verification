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

CREATE TABLE IF NOT EXISTS extracted_fields (
    case_id TEXT NOT NULL,
    field_name TEXT NOT NULL,
    raw_value TEXT,
    normalized_value TEXT,
    status TEXT NOT NULL CHECK (
        status IN (
            'present',
            'missing',
            'uncertain'
        )
    ),
    source_page INTEGER,
    source_reference TEXT,
    PRIMARY KEY (case_id, field_name),
    FOREIGN KEY (case_id) REFERENCES cases(case_id)
);

CREATE INDEX IF NOT EXISTS idx_extracted_fields_case_id
    ON extracted_fields(case_id);

CREATE TABLE IF NOT EXISTS findings (
    case_id TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (
        kind IN (
            'finding',
            'comparison',
            'indicator'
        )
    ),
    ref TEXT NOT NULL,
    code TEXT NOT NULL,
    reason TEXT,
    severity TEXT,
    category TEXT,
    observed_value TEXT,
    reference_value TEXT,
    rule_id TEXT,
    rule_version TEXT,
    PRIMARY KEY (case_id, kind, ref, code),
    FOREIGN KEY (case_id) REFERENCES cases(case_id)
);

CREATE INDEX IF NOT EXISTS idx_findings_case_id
    ON findings(case_id);