import unittest
from datetime import datetime, timezone
from pathlib import Path

from sticky_crm import migration_runner


class MigrationRunnerTests(unittest.TestCase):
    def test_managed_migrations_start_at_ten_and_are_contiguous(self):
        migrations = migration_runner.discover_migrations()

        self.assertEqual([item.version for item in migrations], [10, 11, 12, 13])
        self.assertEqual(
            [item.name for item in migrations],
            [
                "010_create_companies.sql",
                "011_add_release1_tenant_columns.sql",
                "012_company_management.sql",
                "013_invitation_acceptance.sql",
            ],
        )
        self.assertTrue(all(len(item.checksum) == 64 for item in migrations))

    def test_transaction_control_is_rejected(self):
        migration = migration_runner.Migration(
            version=12,
            name="012_unsafe.sql",
            checksum="0" * 64,
            sql="BEGIN; SELECT 1; COMMIT;",
            path=Path("012_unsafe.sql"),
        )

        with self.assertRaises(migration_runner.MigrationError):
            migration_runner._validate_atomic_sql(migration)

    def test_do_block_is_parsed_as_one_atomic_statement(self):
        migration = migration_runner.Migration(
            version=12,
            name="012_do_block.sql",
            checksum="0" * 64,
            sql="DO $migration$ BEGIN PERFORM 1; PERFORM 2; END $migration$;",
            path=Path("012_do_block.sql"),
        )

        migration_runner._validate_atomic_sql(migration)
        self.assertEqual(len(migration_runner._top_level_statements(migration.sql)), 1)

    def test_changed_checksum_is_rejected(self):
        migration = migration_runner.Migration(
            version=10,
            name="010_create_companies.sql",
            checksum="a" * 64,
            sql="SELECT 1;",
            path=Path("010_create_companies.sql"),
        )
        applied = {
            10: migration_runner.AppliedMigration(
                version=10,
                name=migration.name,
                checksum="b" * 64,
                applied_at=datetime.now(timezone.utc),
            )
        }

        with self.assertRaises(migration_runner.MigrationError):
            migration_runner._verify_history([migration], applied)

    def test_missing_earlier_history_entry_is_rejected(self):
        migrations = migration_runner.discover_migrations()
        second = migrations[1]
        applied = {
            second.version: migration_runner.AppliedMigration(
                version=second.version,
                name=second.name,
                checksum=second.checksum,
                applied_at=datetime.now(timezone.utc),
            )
        }

        with self.assertRaises(migration_runner.MigrationError):
            migration_runner._verify_history(migrations, applied)

    def test_existing_managed_schema_without_history_blocks_bootstrap(self):
        connection = _HistoryConnection(
            history_exists=False,
            markers=(True, True, True, True, True),
        )

        with self.assertRaisesRegex(
            migration_runner.MigrationError,
            "Managed schema exists without public.schema_migrations",
        ) as error:
            migration_runner._assert_history_bootstrap_is_safe(connection)

        self.assertIn("companies_table", str(error.exception))

    def test_clean_database_can_create_migration_history(self):
        connection = _HistoryConnection(
            history_exists=False,
            markers=(False, False, False, False, False),
        )

        migration_runner._assert_history_bootstrap_is_safe(connection)

    def test_existing_history_skips_schema_fingerprint_probe(self):
        connection = _HistoryConnection(history_exists=True)

        migration_runner._assert_history_bootstrap_is_safe(connection)

        self.assertEqual(len(connection.cursor_instance.executed), 1)

    def test_read_only_check_rejects_untracked_managed_schema(self):
        cursor = _HistoryCursor(
            history_exists=False,
            markers=(True, False, False, False, False),
        )

        with self.assertRaisesRegex(
            migration_runner.MigrationError,
            "Managed schema exists without public.schema_migrations",
        ):
            migration_runner._raise_for_untracked_managed_schema(cursor)


class _HistoryCursor:
    def __init__(self, history_exists, markers=()):
        self.history_exists = history_exists
        self.markers = markers
        self.executed = []
        self.fetch_index = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def execute(self, query, params=None):
        self.executed.append((query, params))

    def fetchone(self):
        self.fetch_index += 1
        if self.fetch_index == 1:
            return ("schema_migrations" if self.history_exists else None,)
        return tuple(self.markers)


class _HistoryConnection:
    def __init__(self, history_exists, markers=()):
        self.cursor_instance = _HistoryCursor(history_exists, markers)

    def cursor(self):
        return self.cursor_instance


if __name__ == "__main__":
    unittest.main()
