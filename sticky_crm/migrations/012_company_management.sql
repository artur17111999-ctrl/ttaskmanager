-- Company management schema: ownership, seat limits, invitations, membership
-- history, and administrative audit. This migration is additive and performs no
-- company or employee backfill.

ALTER TABLE IF EXISTS companies
    ADD COLUMN IF NOT EXISTS owner_employee_id INTEGER,
    ADD COLUMN IF NOT EXISTS employee_limit INTEGER NOT NULL DEFAULT 15,
    ADD COLUMN IF NOT EXISTS plan_code VARCHAR(50) NOT NULL DEFAULT 'default';

DO $migration$
BEGIN
    IF to_regclass('companies') IS NOT NULL
       AND NOT EXISTS (
           SELECT 1
           FROM pg_constraint
           WHERE conrelid = to_regclass('companies')
             AND conname = 'ck_companies_employee_limit'
       ) THEN
        ALTER TABLE companies
            ADD CONSTRAINT ck_companies_employee_limit
            CHECK (employee_limit > 0)
            NOT VALID;
    END IF;

    IF to_regclass('companies') IS NOT NULL
       AND NOT EXISTS (
           SELECT 1
           FROM pg_constraint
           WHERE conrelid = to_regclass('companies')
             AND conname = 'ck_companies_plan_code_not_blank'
       ) THEN
        ALTER TABLE companies
            ADD CONSTRAINT ck_companies_plan_code_not_blank
            CHECK (BTRIM(plan_code) <> '')
            NOT VALID;
    END IF;
END
$migration$;

-- The owner reference is composite so a company can only point to an employee
-- whose current employees.company_id is that same company. It remains nullable
-- until the audited legacy-data backfill is complete.
DO $migration$
BEGIN
    IF to_regclass('employees') IS NOT NULL THEN
        CREATE UNIQUE INDEX IF NOT EXISTS uq_employees_id_company_id
            ON employees(id, company_id);
    END IF;

    IF to_regclass('companies') IS NOT NULL
       AND to_regclass('employees') IS NOT NULL
       AND NOT EXISTS (
           SELECT 1
           FROM pg_constraint
           WHERE conrelid = to_regclass('companies')
             AND conname = 'fk_companies_owner_employee'
       ) THEN
        ALTER TABLE companies
            ADD CONSTRAINT fk_companies_owner_employee
            FOREIGN KEY (owner_employee_id, id)
            REFERENCES employees(id, company_id)
            ON DELETE NO ACTION
            DEFERRABLE INITIALLY DEFERRED
            NOT VALID;
    END IF;
END
$migration$;

CREATE UNIQUE INDEX IF NOT EXISTS uq_companies_owner_employee
    ON companies(owner_employee_id)
    WHERE owner_employee_id IS NOT NULL;

-- Release 011 did not yet include the canonical company_owner role. Replace only
-- that known check while leaving any installation-specific constraints intact.
DO $migration$
DECLARE
    role_constraint_definition TEXT;
BEGIN
    IF to_regclass('employees') IS NULL THEN
        RETURN;
    END IF;

    SELECT pg_get_constraintdef(oid)
    INTO role_constraint_definition
    FROM pg_constraint
    WHERE conrelid = to_regclass('employees')
      AND conname = 'ck_employees_role';

    IF role_constraint_definition IS NOT NULL
       AND POSITION('company_owner' IN role_constraint_definition) = 0 THEN
        ALTER TABLE employees DROP CONSTRAINT ck_employees_role;
        role_constraint_definition := NULL;
    END IF;

    IF role_constraint_definition IS NULL
       AND NOT EXISTS (
           SELECT 1
           FROM pg_constraint
           WHERE conrelid = to_regclass('employees')
             AND conname = 'ck_employees_role'
       ) THEN
        ALTER TABLE employees
            ADD CONSTRAINT ck_employees_role
            CHECK (role IN (
                'employee',
                'company_admin',
                'company_owner',
                'system_admin'
            ))
            NOT VALID;
    END IF;
END
$migration$;

CREATE TABLE IF NOT EXISTS company_invitations (
    id BIGSERIAL PRIMARY KEY,
    company_id INTEGER NOT NULL,
    email_normalized VARCHAR(320) NOT NULL,
    requested_role VARCHAR(50) NOT NULL DEFAULT 'employee',
    token_hash VARCHAR(128) NOT NULL,
    invited_by INTEGER NOT NULL,
    profile_data JSONB NOT NULL DEFAULT '{}'::JSONB,
    expires_at TIMESTAMP NOT NULL,
    accepted_at TIMESTAMP,
    revoked_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_company_invitations_company
        FOREIGN KEY (company_id) REFERENCES companies(id) ON DELETE CASCADE,
    CONSTRAINT fk_company_invitations_invited_by
        FOREIGN KEY (invited_by, company_id)
        REFERENCES employees(id, company_id) ON DELETE RESTRICT,
    CONSTRAINT ck_company_invitations_email_normalized CHECK (
        email_normalized = LOWER(BTRIM(email_normalized))
        AND BTRIM(email_normalized) <> ''
    ),
    CONSTRAINT ck_company_invitations_requested_role CHECK (
        requested_role IN ('employee', 'company_admin')
    ),
    CONSTRAINT ck_company_invitations_token_hash_not_blank CHECK (
        BTRIM(token_hash) <> ''
    ),
    CONSTRAINT ck_company_invitations_expiration CHECK (expires_at > created_at),
    CONSTRAINT ck_company_invitations_terminal_state CHECK (
        NOT (accepted_at IS NOT NULL AND revoked_at IS NOT NULL)
    )
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_company_invitations_token_hash
    ON company_invitations(token_hash);

-- Expired invitations must be revoked by the service before another invitation
-- for the same address is issued; SQL predicates cannot safely depend on NOW().
CREATE UNIQUE INDEX IF NOT EXISTS uq_company_invitations_pending_email
    ON company_invitations(company_id, email_normalized)
    WHERE accepted_at IS NULL AND revoked_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_company_invitations_company_created
    ON company_invitations(company_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_company_invitations_pending_expiration
    ON company_invitations(company_id, expires_at)
    WHERE accepted_at IS NULL AND revoked_at IS NULL;

CREATE TABLE IF NOT EXISTS company_membership_history (
    id BIGSERIAL PRIMARY KEY,
    company_id INTEGER NOT NULL,
    employee_id INTEGER NOT NULL,
    role VARCHAR(50) NOT NULL,
    membership_status VARCHAR(30) NOT NULL DEFAULT 'active',
    source_invitation_id BIGINT,
    changed_by INTEGER,
    reason TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::JSONB,
    started_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    ended_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_company_membership_history_company
        FOREIGN KEY (company_id) REFERENCES companies(id) ON DELETE RESTRICT,
    CONSTRAINT fk_company_membership_history_employee
        FOREIGN KEY (employee_id, company_id)
        REFERENCES employees(id, company_id) ON DELETE RESTRICT,
    CONSTRAINT fk_company_membership_history_invitation
        FOREIGN KEY (source_invitation_id)
        REFERENCES company_invitations(id) ON DELETE SET NULL,
    CONSTRAINT fk_company_membership_history_changed_by
        FOREIGN KEY (changed_by) REFERENCES employees(id) ON DELETE SET NULL,
    CONSTRAINT ck_company_membership_history_role CHECK (
        role IN ('employee', 'company_admin', 'company_owner')
    ),
    CONSTRAINT ck_company_membership_history_status CHECK (
        membership_status IN ('active', 'dismissed', 'blocked')
    ),
    CONSTRAINT ck_company_membership_history_period CHECK (
        ended_at IS NULL OR ended_at >= started_at
    )
);

-- The current employees model has one company_id, so an employee may have only
-- one open membership period across all companies.
CREATE UNIQUE INDEX IF NOT EXISTS uq_company_membership_history_open_employee
    ON company_membership_history(employee_id)
    WHERE ended_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_company_membership_history_company_started
    ON company_membership_history(company_id, started_at DESC);

CREATE INDEX IF NOT EXISTS idx_company_membership_history_employee_started
    ON company_membership_history(employee_id, started_at DESC);

CREATE TABLE IF NOT EXISTS audit_log (
    id BIGSERIAL PRIMARY KEY,
    company_id INTEGER,
    actor_employee_id INTEGER,
    action VARCHAR(100) NOT NULL,
    entity_type VARCHAR(100) NOT NULL,
    entity_id TEXT,
    old_values JSONB,
    new_values JSONB,
    metadata JSONB NOT NULL DEFAULT '{}'::JSONB,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_audit_log_company
        FOREIGN KEY (company_id) REFERENCES companies(id) ON DELETE RESTRICT,
    CONSTRAINT fk_audit_log_actor
        FOREIGN KEY (actor_employee_id) REFERENCES employees(id) ON DELETE SET NULL,
    CONSTRAINT ck_audit_log_action_not_blank CHECK (BTRIM(action) <> ''),
    CONSTRAINT ck_audit_log_entity_type_not_blank CHECK (BTRIM(entity_type) <> '')
);

CREATE INDEX IF NOT EXISTS idx_audit_log_company_created
    ON audit_log(company_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_audit_log_actor_created
    ON audit_log(actor_employee_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_audit_log_entity
    ON audit_log(entity_type, entity_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_audit_log_action_created
    ON audit_log(action, created_at DESC);
