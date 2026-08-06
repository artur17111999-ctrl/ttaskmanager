-- Invitation acceptance persistence and account hardening.
--
-- This migration is additive. It does not normalize, merge, or delete legacy
-- accounts/employees. Unique normalized indexes are installed only after an
-- explicit duplicate audit; conflicting legacy data stops the migration so it
-- can be reviewed outside the deployment transaction.

ALTER TABLE IF EXISTS company_invitations
    ADD COLUMN IF NOT EXISTS accepted_employee_id INTEGER,
    ADD COLUMN IF NOT EXISTS accepted_account_id INTEGER,
    ADD COLUMN IF NOT EXISTS superseded_by_id BIGINT,
    ADD COLUMN IF NOT EXISTS last_sent_at TIMESTAMP,
    ADD COLUMN IF NOT EXISTS delivery_status VARCHAR(30) NOT NULL DEFAULT 'manual',
    ADD COLUMN IF NOT EXISTS acceptance_request_id VARCHAR(100);

ALTER TABLE IF EXISTS accounts
    ADD COLUMN IF NOT EXISTS status VARCHAR(30) NOT NULL DEFAULT 'active',
    ADD COLUMN IF NOT EXISTS password_changed_at TIMESTAMP,
    ADD COLUMN IF NOT EXISTS session_generation INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ADD COLUMN IF NOT EXISTS last_login_at TIMESTAMP,
    ADD COLUMN IF NOT EXISTS email_verified_at TIMESTAMP;

-- Preserve the one-account-per-employee contract without creating a redundant
-- index when an installation already has an equivalent UNIQUE constraint.
DO $migration$
BEGIN
    IF to_regclass('public.accounts') IS NULL THEN
        RETURN;
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_index index_row
        JOIN pg_attribute attribute
          ON attribute.attrelid = index_row.indrelid
         AND attribute.attnum = ANY(index_row.indkey)
        WHERE index_row.indrelid = to_regclass('public.accounts')
          AND index_row.indisunique
          AND index_row.indpred IS NULL
          AND index_row.indexprs IS NULL
          AND index_row.indnkeyatts = 1
          AND attribute.attname = 'employee_id'
    ) THEN
        IF EXISTS (
            SELECT 1
            FROM accounts
            GROUP BY employee_id
            HAVING COUNT(*) > 1
        ) THEN
            RAISE EXCEPTION USING
                MESSAGE = 'Cannot enforce one account per employee: duplicate accounts.employee_id values exist',
                HINT = 'Audit and resolve duplicate accounts manually; migration 013 performs no automatic merge or deletion.';
        END IF;

        CREATE UNIQUE INDEX IF NOT EXISTS uq_accounts_employee_id
            ON accounts(employee_id);
    END IF;
END
$migration$;

-- The composite key lets invitation acceptance prove that accepted_account_id
-- belongs to accepted_employee_id without relying on application code.
CREATE UNIQUE INDEX IF NOT EXISTS uq_accounts_id_employee_id
    ON accounts(id, employee_id);

-- Login comparison in authentication is moving to normalized semantics. Stop
-- on collisions instead of silently choosing or rewriting an existing login.
DO $migration$
BEGIN
    IF to_regclass('public.accounts') IS NULL
       OR to_regclass('public.uq_accounts_login_normalized') IS NOT NULL THEN
        RETURN;
    END IF;

    IF EXISTS (
        SELECT 1
        FROM accounts
        GROUP BY LOWER(BTRIM(login))
        HAVING COUNT(*) > 1
    ) THEN
        RAISE EXCEPTION USING
            MESSAGE = 'Cannot enforce normalized account login uniqueness: case or whitespace duplicates exist',
            HINT = 'Audit duplicate logins manually; migration 013 performs no automatic rename.';
    END IF;

    CREATE UNIQUE INDEX IF NOT EXISTS uq_accounts_login_normalized
        ON accounts(LOWER(BTRIM(login)));
END
$migration$;

-- The current employee model permits only one account/company membership, so
-- normalized email remains globally unique for now. This can be replaced by a
-- membership-scoped identity model during the multi-company cutover.
DO $migration$
BEGIN
    IF to_regclass('public.employees') IS NULL
       OR to_regclass('public.uq_employees_email_normalized') IS NOT NULL THEN
        RETURN;
    END IF;

    IF EXISTS (
        SELECT 1
        FROM employees
        WHERE email IS NOT NULL
          AND BTRIM(email) <> ''
        GROUP BY LOWER(BTRIM(email))
        HAVING COUNT(*) > 1
    ) THEN
        RAISE EXCEPTION USING
            MESSAGE = 'Cannot enforce normalized employee email uniqueness: case or whitespace duplicates exist',
            HINT = 'Audit duplicate employee emails manually; migration 013 performs no automatic rewrite.';
    END IF;

    CREATE UNIQUE INDEX IF NOT EXISTS uq_employees_email_normalized
        ON employees(LOWER(BTRIM(email)))
        WHERE email IS NOT NULL AND BTRIM(email) <> '';
END
$migration$;

DO $migration$
BEGIN
    IF to_regclass('public.accounts') IS NULL THEN
        RETURN;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = to_regclass('public.accounts')
          AND conname = 'ck_accounts_status'
    ) THEN
        ALTER TABLE accounts
            ADD CONSTRAINT ck_accounts_status
            CHECK (status IN ('pending', 'active', 'blocked'))
            NOT VALID;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = to_regclass('public.accounts')
          AND conname = 'ck_accounts_session_generation'
    ) THEN
        ALTER TABLE accounts
            ADD CONSTRAINT ck_accounts_session_generation
            CHECK (session_generation >= 0)
            NOT VALID;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = to_regclass('public.accounts')
          AND conname = 'ck_accounts_login_not_blank'
    ) THEN
        ALTER TABLE accounts
            ADD CONSTRAINT ck_accounts_login_not_blank
            CHECK (BTRIM(login) <> '')
            NOT VALID;
    END IF;
END
$migration$;

DO $migration$
BEGIN
    IF to_regclass('public.company_invitations') IS NULL THEN
        RETURN;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = to_regclass('public.company_invitations')
          AND conname = 'fk_company_invitations_accepted_employee'
    ) THEN
        ALTER TABLE company_invitations
            ADD CONSTRAINT fk_company_invitations_accepted_employee
            FOREIGN KEY (accepted_employee_id, company_id)
            REFERENCES employees(id, company_id)
            ON DELETE NO ACTION
            DEFERRABLE INITIALLY DEFERRED
            NOT VALID;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = to_regclass('public.company_invitations')
          AND conname = 'fk_company_invitations_accepted_account_employee'
    ) THEN
        ALTER TABLE company_invitations
            ADD CONSTRAINT fk_company_invitations_accepted_account_employee
            FOREIGN KEY (accepted_account_id, accepted_employee_id)
            REFERENCES accounts(id, employee_id)
            ON DELETE NO ACTION
            DEFERRABLE INITIALLY DEFERRED
            NOT VALID;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = to_regclass('public.company_invitations')
          AND conname = 'fk_company_invitations_superseded_by'
    ) THEN
        ALTER TABLE company_invitations
            ADD CONSTRAINT fk_company_invitations_superseded_by
            FOREIGN KEY (superseded_by_id)
            REFERENCES company_invitations(id)
            ON DELETE NO ACTION
            DEFERRABLE INITIALLY DEFERRED
            NOT VALID;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = to_regclass('public.company_invitations')
          AND conname = 'ck_company_invitations_acceptance_complete'
    ) THEN
        ALTER TABLE company_invitations
            ADD CONSTRAINT ck_company_invitations_acceptance_complete
            CHECK (
                (accepted_at IS NULL
                    AND accepted_employee_id IS NULL
                    AND accepted_account_id IS NULL)
                OR
                (accepted_at IS NOT NULL
                    AND accepted_employee_id IS NOT NULL
                    AND accepted_account_id IS NOT NULL)
            )
            NOT VALID;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = to_regclass('public.company_invitations')
          AND conname = 'ck_company_invitations_terminal_state'
    ) THEN
        ALTER TABLE company_invitations
            ADD CONSTRAINT ck_company_invitations_terminal_state
            CHECK (NOT (accepted_at IS NOT NULL AND revoked_at IS NOT NULL))
            NOT VALID;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = to_regclass('public.company_invitations')
          AND conname = 'ck_company_invitations_not_self_superseded'
    ) THEN
        ALTER TABLE company_invitations
            ADD CONSTRAINT ck_company_invitations_not_self_superseded
            CHECK (superseded_by_id IS NULL OR superseded_by_id <> id)
            NOT VALID;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = to_regclass('public.company_invitations')
          AND conname = 'ck_company_invitations_delivery_status_not_blank'
    ) THEN
        ALTER TABLE company_invitations
            ADD CONSTRAINT ck_company_invitations_delivery_status_not_blank
            CHECK (BTRIM(delivery_status) <> '')
            NOT VALID;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = to_regclass('public.company_invitations')
          AND conname = 'ck_company_invitations_acceptance_request_not_blank'
    ) THEN
        ALTER TABLE company_invitations
            ADD CONSTRAINT ck_company_invitations_acceptance_request_not_blank
            CHECK (
                acceptance_request_id IS NULL
                OR BTRIM(acceptance_request_id) <> ''
            )
            NOT VALID;
    END IF;
END
$migration$;

-- One employee may originate from only one accepted invitation in the current
-- one-company identity model. A future multiple-membership model should move
-- this relationship from employees to memberships.
CREATE UNIQUE INDEX IF NOT EXISTS uq_company_invitations_accepted_employee
    ON company_invitations(accepted_employee_id)
    WHERE accepted_employee_id IS NOT NULL;

-- acceptance_request_id is a server-generated, non-secret correlation ID. Raw
-- idempotency keys belong nowhere in this column or elsewhere in the database.
CREATE UNIQUE INDEX IF NOT EXISTS uq_company_invitations_acceptance_request
    ON company_invitations(acceptance_request_id)
    WHERE acceptance_request_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_company_invitations_accepted_account
    ON company_invitations(accepted_account_id)
    WHERE accepted_account_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_company_invitations_superseded_by
    ON company_invitations(superseded_by_id)
    WHERE superseded_by_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_company_invitations_delivery_status
    ON company_invitations(company_id, delivery_status, created_at DESC);

-- Store only hashes of caller-provided idempotency keys. response_body must be
-- a deliberately small replay payload and must never contain invitation tokens,
-- password material, session credentials, or other secrets.
CREATE TABLE IF NOT EXISTS idempotency_requests (
    id BIGSERIAL PRIMARY KEY,
    operation VARCHAR(100) NOT NULL,
    key_hash VARCHAR(128) NOT NULL,
    invitation_id BIGINT,
    principal_employee_id INTEGER,
    request_hash VARCHAR(128) NOT NULL,
    response_code INTEGER,
    response_body JSONB,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NOT NULL,
    CONSTRAINT fk_idempotency_requests_invitation
        FOREIGN KEY (invitation_id)
        REFERENCES company_invitations(id) ON DELETE RESTRICT,
    CONSTRAINT fk_idempotency_requests_principal
        FOREIGN KEY (principal_employee_id)
        REFERENCES employees(id) ON DELETE SET NULL,
    CONSTRAINT ck_idempotency_requests_operation_not_blank
        CHECK (BTRIM(operation) <> ''),
    CONSTRAINT ck_idempotency_requests_key_hash
        CHECK (key_hash ~ '^[0-9a-f]{64}$'),
    CONSTRAINT ck_idempotency_requests_request_hash
        CHECK (request_hash ~ '^[0-9a-f]{64}$'),
    CONSTRAINT ck_idempotency_requests_response_code
        CHECK (response_code IS NULL OR response_code BETWEEN 100 AND 599),
    CONSTRAINT ck_idempotency_requests_expiration
        CHECK (expires_at > created_at)
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_idempotency_requests_operation_key
    ON idempotency_requests(operation, key_hash);

CREATE INDEX IF NOT EXISTS idx_idempotency_requests_invitation_created
    ON idempotency_requests(invitation_id, created_at DESC)
    WHERE invitation_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_idempotency_requests_expiration
    ON idempotency_requests(expires_at);
