-- Release 1A: additive tenant columns only.
-- No company backfill, NOT NULL tenant constraints, or catalog cutover belongs here.

ALTER TABLE IF EXISTS employees
    ADD COLUMN IF NOT EXISTS company_id INTEGER,
    ADD COLUMN IF NOT EXISTS role VARCHAR(50) NOT NULL DEFAULT 'employee';

ALTER TABLE IF EXISTS tasks
    ADD COLUMN IF NOT EXISTS company_id INTEGER;

ALTER TABLE IF EXISTS chats
    ADD COLUMN IF NOT EXISTS company_id INTEGER;

ALTER TABLE IF EXISTS stickies
    ADD COLUMN IF NOT EXISTS company_id INTEGER;

ALTER TABLE IF EXISTS task_statuses
    ADD COLUMN IF NOT EXISTS company_id INTEGER;

ALTER TABLE IF EXISTS task_tags
    ADD COLUMN IF NOT EXISTS company_id INTEGER;

ALTER TABLE IF EXISTS task_tags_link
    ADD COLUMN IF NOT EXISTS company_id INTEGER;

-- NOT VALID keeps this release additive for pre-existing data while still enforcing
-- the foreign keys for new and changed rows. Validation follows the audited backfill.
DO $migration$
DECLARE
    target_table TEXT;
    constraint_name TEXT;
BEGIN
    FOREACH target_table IN ARRAY ARRAY[
        'employees',
        'tasks',
        'chats',
        'stickies',
        'task_statuses',
        'task_tags',
        'task_tags_link'
    ]
    LOOP
        IF to_regclass(target_table) IS NULL THEN
            CONTINUE;
        END IF;

        constraint_name := 'fk_' || target_table || '_company';
        IF NOT EXISTS (
            SELECT 1
            FROM pg_constraint
            WHERE conrelid = to_regclass(target_table)
              AND conname = constraint_name
        ) THEN
            EXECUTE format(
                'ALTER TABLE %I ADD CONSTRAINT %I FOREIGN KEY (company_id) '
                'REFERENCES companies(id) ON DELETE RESTRICT NOT VALID',
                target_table,
                constraint_name
            );
        END IF;
    END LOOP;
END
$migration$;

DO $migration$
BEGIN
    IF to_regclass('employees') IS NOT NULL
       AND NOT EXISTS (
           SELECT 1
           FROM pg_constraint
           WHERE conrelid = to_regclass('employees')
             AND conname = 'ck_employees_role'
       ) THEN
        ALTER TABLE employees
            ADD CONSTRAINT ck_employees_role
            CHECK (role IN ('employee', 'company_admin', 'system_admin'))
            NOT VALID;
    END IF;
END
$migration$;

-- Index creation is conditional because task_statuses can be provisioned outside the
-- repository's historical SQL files in existing installations.
DO $migration$
DECLARE
    target_table TEXT;
    index_name TEXT;
BEGIN
    FOREACH target_table IN ARRAY ARRAY[
        'employees',
        'tasks',
        'chats',
        'stickies',
        'task_statuses',
        'task_tags',
        'task_tags_link'
    ]
    LOOP
        IF to_regclass(target_table) IS NULL THEN
            CONTINUE;
        END IF;

        index_name := 'idx_' || target_table || '_company_id';
        EXECUTE format(
            'CREATE INDEX IF NOT EXISTS %I ON %I(company_id)',
            index_name,
            target_table
        );
    END LOOP;
END
$migration$;
