import re
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS_ROOT = PROJECT_ROOT / "sticky_crm" / "migrations"


def _compact(sql):
    return re.sub(r"\s+", " ", sql).casefold()


class CompanyManagementMigrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        paths = sorted(MIGRATIONS_ROOT.glob("012_*.sql"))
        if len(paths) != 1:
            raise AssertionError(
                f"Expected exactly one migration 012, found {[p.name for p in paths]}"
            )
        cls.path = paths[0]
        cls.sql = cls.path.read_text(encoding="utf-8-sig")
        cls.normalized = _compact(cls.sql)

    def test_expected_migration_name(self):
        self.assertEqual(self.path.name, "012_company_management.sql")

    def test_company_plan_owner_and_default_limit_are_added(self):
        self.assertRegex(
            self.normalized,
            r"add column if not exists employee_limit\s+integer\s+not null\s+default\s+15",
        )
        self.assertRegex(
            self.normalized,
            r"add column if not exists plan_code\s+varchar\([^)]*\)\s+not null\s+default\s+'default'",
        )
        self.assertRegex(
            self.normalized,
            r"add column if not exists owner_employee_id\s+integer",
        )

    def test_company_owner_is_an_allowed_employee_role(self):
        self.assertIn("company_owner", self.normalized)
        self.assertIn("ck_employees_role", self.normalized)

    def test_invitations_schema_reserves_one_slot_per_email(self):
        self.assertIn(
            "create table if not exists company_invitations", self.normalized
        )
        for column in (
            "company_id",
            "email_normalized",
            "requested_role",
            "profile_data",
            "token_hash",
            "invited_by",
            "profile_data",
            "expires_at",
            "accepted_at",
            "revoked_at",
            "created_at",
        ):
            with self.subTest(column=column):
                self.assertRegex(self.normalized, rf"\b{column}\b")

        self.assertRegex(
            self.normalized,
            r"profile_data jsonb not null default '\{\}'::jsonb",
        )

        partial_unique = re.search(
            r"create unique index if not exists .*? "
            r"on company_invitations\s*\([^)]*company_id[^)]*email_normalized[^)]*\) "
            r"where (?P<predicate>.*?);",
            self.normalized,
        )
        self.assertIsNotNone(
            partial_unique,
            "A partial unique index must prevent duplicate pending reservations",
        )
        predicate = partial_unique.group("predicate")
        self.assertIn("accepted_at is null", predicate)
        self.assertIn("revoked_at is null", predicate)

    def test_membership_history_and_audit_tables_are_present(self):
        self.assertIn(
            "create table if not exists company_membership_history",
            self.normalized,
        )
        self.assertIn("create table if not exists audit_log", self.normalized)
        for column in ("company_id", "actor_employee_id", "action", "created_at"):
            with self.subTest(table="audit_log", column=column):
                audit_start = self.normalized.index(
                    "create table if not exists audit_log"
                )
                self.assertIn(column, self.normalized[audit_start:])

    def test_repeatable_ddl_guards_are_present(self):
        statements = [item.strip() for item in self.sql.split(";") if item.strip()]
        for statement in statements:
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

    def test_foreign_keys_are_guarded_and_tenant_scoped_indexes_exist(self):
        self.assertIn("from pg_constraint", self.normalized)
        for fragment in (
            "foreign key (company_id)",
            "references companies",
            "company_invitations",
            "company_membership_history",
            "audit_log",
        ):
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, self.normalized)
        self.assertRegex(
            self.normalized,
            r"foreign key \(owner_employee_id(?:\s*,\s*id)?\)",
        )
        self.assertRegex(
            self.normalized,
            r"foreign key \(invited_by\s*,\s*company_id\) "
            r"references employees\s*\(id\s*,\s*company_id\)",
        )
        self.assertRegex(
            self.normalized,
            r"foreign key \(employee_id\s*,\s*company_id\) "
            r"references employees\s*\(id\s*,\s*company_id\)",
        )
        self.assertRegex(
            self.normalized,
            r"create (?:unique )?index if not exists .*? on company_invitations",
        )
        self.assertRegex(
            self.normalized,
            r"foreign key \(invited_by\s*,\s*company_id\)\s+"
            r"references employees\s*\(id\s*,\s*company_id\)",
        )
        self.assertRegex(
            self.normalized,
            r"foreign key \(employee_id\s*,\s*company_id\)\s+"
            r"references employees\s*\(id\s*,\s*company_id\)",
        )

    def test_migration_has_no_destructive_data_operations(self):
        for fragment in (
            "drop table",
            "truncate ",
            "delete from companies",
            "delete from employees",
            "update employees set company_id",
        ):
            with self.subTest(fragment=fragment):
                self.assertNotIn(fragment, self.normalized)


if __name__ == "__main__":
    unittest.main()
