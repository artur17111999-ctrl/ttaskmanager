import re
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS_ROOT = PROJECT_ROOT / "sticky_crm" / "migrations"


def _compact(sql):
    return re.sub(r"\s+", " ", sql).casefold()


class InvitationAcceptanceMigrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        paths = sorted(MIGRATIONS_ROOT.glob("013_*.sql"))
        if len(paths) != 1:
            raise AssertionError(
                f"Expected exactly one migration 013, found {[path.name for path in paths]}"
            )
        cls.path = paths[0]
        cls.sql = cls.path.read_text(encoding="utf-8-sig")
        cls.normalized = _compact(cls.sql)

    def test_expected_migration_name(self):
        self.assertEqual(self.path.name, "013_invitation_acceptance.sql")

    def test_acceptance_and_delivery_columns_are_additive(self):
        required_columns = {
            "accepted_employee_id": "integer",
            "accepted_account_id": "integer",
            "superseded_by_id": "bigint",
            "last_sent_at": "timestamp",
            "acceptance_request_id": "varchar",
        }
        for column, sql_type in required_columns.items():
            with self.subTest(column=column):
                self.assertRegex(
                    self.normalized,
                    rf"add column if not exists {column}\s+{sql_type}",
                )
        self.assertRegex(
            self.normalized,
            r"add column if not exists delivery_status\s+varchar\([^)]*\)\s+not null\s+default\s+'manual'",
        )

    def test_acceptance_references_are_guarded(self):
        self.assertIn("accepted_employee_id", self.normalized)
        self.assertIn("accepted_account_id", self.normalized)
        self.assertIn("superseded_by_id", self.normalized)
        self.assertRegex(
            self.normalized,
            r"foreign key\s*\(accepted_employee_id\s*,\s*company_id\)\s*references employees\s*\(id\s*,\s*company_id\)",
        )
        self.assertRegex(
            self.normalized,
            r"foreign key\s*\(accepted_account_id\s*,\s*accepted_employee_id\)\s*"
            r"references accounts\s*\(id\s*,\s*employee_id\)",
        )
        self.assertRegex(
            self.normalized,
            r"foreign key\s*\(superseded_by_id\)\s*references company_invitations\s*\(id\)",
        )
        self.assertIn("pg_constraint", self.normalized)

    def test_terminal_state_and_rotation_checks_are_present(self):
        acceptance_check = re.search(
            r"add constraint ck_company_invitations_acceptance_complete\s+"
            r"check\s*\((?P<body>.*?)\)\s+not valid",
            self.normalized,
        )
        self.assertIsNotNone(acceptance_check)
        body = acceptance_check.group("body")
        for fragment in (
            "accepted_at is null",
            "accepted_employee_id is null",
            "accepted_account_id is null",
            "accepted_at is not null",
            "accepted_employee_id is not null",
            "accepted_account_id is not null",
        ):
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, body)
        self.assertRegex(
            self.normalized,
            r"not\s*\(\s*accepted_at\s+is\s+not\s+null\s+and\s+revoked_at\s+is\s+not\s+null\s*\)",
        )
        self.assertRegex(
            self.normalized,
            r"superseded_by_id\s+is\s+null\s+or\s+superseded_by_id\s*<>\s*id",
        )

    def test_one_employee_has_one_account_and_one_accepted_invitation(self):
        self.assertRegex(
            self.normalized,
            r"create unique index if not exists\s+\w+\s+on accounts\s*\(employee_id\)",
        )
        self.assertRegex(
            self.normalized,
            r"create unique index if not exists\s+\w+\s+on company_invitations\s*\(accepted_employee_id\)",
        )

    def test_idempotency_storage_does_not_store_raw_secrets(self):
        self.assertRegex(
            self.normalized,
            r"create table if not exists\s+(?:idempotency_requests|invitation_acceptance_requests)",
        )
        self.assertIn("key_hash", self.normalized)
        self.assertIn("request_hash", self.normalized)
        idempotency_table = re.search(
            r"create table if not exists idempotency_requests\s*"
            r"\((?P<body>.*?)\);",
            self.normalized,
        )
        self.assertIsNotNone(idempotency_table)
        body = idempotency_table.group("body")
        self.assertNotRegex(
            body,
            r"\b(raw_token|token|password|password_hash|session_token|refresh_token)\b",
        )
        self.assertRegex(
            self.normalized,
            r"create unique index if not exists\s+\w+\s+"
            r"on idempotency_requests\s*\(operation\s*,\s*key_hash\)",
        )

    def test_normalized_identity_uniqueness_is_audited_without_backfill(self):
        self.assertRegex(
            self.normalized,
            r"create unique index if not exists\s+uq_accounts_login_normalized\s+"
            r"on accounts\s*\(lower\s*\(btrim\s*\(login\)\)\)",
        )
        self.assertRegex(
            self.normalized,
            r"create unique index if not exists\s+uq_employees_email_normalized\s+"
            r"on employees\s*\(lower\s*\(btrim\s*\(email\)\)\)",
        )
        self.assertIn("having count(*) > 1", self.normalized)
        self.assertIn("raise exception", self.normalized)
        self.assertNotRegex(
            self.normalized,
            r"update\s+(?:accounts|employees)\s+set\s+(?:login|email)",
        )

    def test_account_session_and_lifecycle_fields_are_forward_compatible(self):
        for column in (
            "status",
            "password_changed_at",
            "session_generation",
            "created_at",
            "updated_at",
            "last_login_at",
            "email_verified_at",
        ):
            with self.subTest(column=column):
                self.assertIn(column, self.normalized)
        self.assertRegex(
            self.normalized,
            r"session_generation\s+integer\s+not null\s+default\s+0",
        )

    def test_migration_is_repeatable_and_non_destructive(self):
        self.assertNotRegex(
            self.normalized,
            r"\b(drop table|truncate|delete from|alter table\s+\w+\s+drop column)\b",
        )
        for statement in (item.strip() for item in self.sql.split(";") if item.strip()):
            compact = _compact(statement)
            if compact.startswith("create table"):
                with self.subTest(statement=compact[:100]):
                    self.assertTrue(compact.startswith("create table if not exists"))
            if compact.startswith("create index") or compact.startswith(
            "create unique index"
            ):
                with self.subTest(statement=compact[:100]):
                    self.assertIn("if not exists", compact)
            if re.match(r"alter table(?: if exists)? \w+ add column", compact):
                with self.subTest(statement=compact[:100]):
                    self.assertIn("add column if not exists", compact)

    def test_foreign_keys_and_checks_use_repeatable_catalog_guards(self):
        for constraint in (
            "fk_company_invitations_accepted_employee",
            "fk_company_invitations_accepted_account_employee",
            "fk_company_invitations_superseded_by",
            "ck_company_invitations_acceptance_complete",
            "ck_accounts_status",
            "ck_accounts_session_generation",
        ):
            with self.subTest(constraint=constraint):
                pattern = (
                    r"not exists\s*\(\s*select 1 from pg_constraint.*?"
                    r"conname = '" + re.escape(constraint) + r"'"
                )
                self.assertRegex(self.normalized, pattern)


if __name__ == "__main__":
    unittest.main()
