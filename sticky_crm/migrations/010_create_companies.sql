-- Release 1A: company directory.
-- The migration intentionally creates no company rows: legal details must be supplied
-- by an operator during the later audited backfill.

CREATE TABLE IF NOT EXISTS companies (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    inn VARCHAR(12) NOT NULL,
    kpp VARCHAR(9),
    legal_address TEXT,
    actual_address TEXT,
    contact_email VARCHAR(255),
    website_url VARCHAR(500),
    status VARCHAR(20) NOT NULL DEFAULT 'active',
    task_catalog_version BIGINT NOT NULL DEFAULT 1,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    archived_at TIMESTAMP,
    CONSTRAINT ck_companies_name_not_blank CHECK (BTRIM(name) <> ''),
    CONSTRAINT ck_companies_inn_format CHECK (inn ~ '^[0-9]{10}([0-9]{2})?$'),
    CONSTRAINT ck_companies_kpp_format CHECK (kpp IS NULL OR kpp ~ '^[0-9]{9}$'),
    CONSTRAINT ck_companies_status CHECK (status IN ('active', 'blocked', 'archived'))
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_companies_inn_kpp
    ON companies(inn, kpp)
    WHERE kpp IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_companies_inn_without_kpp
    ON companies(inn)
    WHERE kpp IS NULL;

CREATE INDEX IF NOT EXISTS idx_companies_status
    ON companies(status);
