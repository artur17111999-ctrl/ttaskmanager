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


if __name__ == "__main__":
    unittest.main()
