import re
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS_ROOT = PROJECT_ROOT / "sticky_crm" / "migrations"


def _company_migration_files():
    result = []
    for path in sorted(MIGRATIONS_ROOT.glob("*.sql")):
        sql = path.read_text(encoding="utf-8")
        if re.search(r"\bcompanies\b", sql, flags=re.IGNORECASE):
            result.append((path, sql))
    return result


class CompanyMigrationContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.migrations = _company_migration_files()
        cls.sql = "\n".join(sql for _, sql in cls.migrations)

    def test_company_migration_exists(self):
        self.assertTrue(
            self.migrations,
            "Expected a migration that creates or references the companies table",
        )

    def test_companies_table_contains_required_fields(self):
        required_fragments = (
            "CREATE TABLE IF NOT EXISTS companies",
            "name",
            "inn",
            "kpp",
            "legal_address",
            "actual_address",
            "contact_email",
            "website_url",
        )
        normalized = re.sub(r"\s+", " ", self.sql).casefold()
        for fragment in required_fragments:
            with self.subTest(fragment=fragment):
                self.assertIn(fragment.casefold(), normalized)

    def test_employee_company_and_role_columns_are_repeatable(self):
        normalized = re.sub(r"\s+", " ", self.sql).casefold()
        employee_alter = re.search(
            r"alter table(?: if exists)? employees (?P<body>.*?);",
            normalized,
        )
        self.assertIsNotNone(employee_alter)
        body = employee_alter.group("body")
        self.assertRegex(body, r"add column if not exists company_id\b")
        self.assertRegex(body, r"add column if not exists role\b")

    def test_all_release_one_tenant_columns_are_declared(self):
        normalized = re.sub(r"\s+", " ", self.sql).casefold()
        tenant_tables = (
            "employees",
            "tasks",
            "chats",
            "stickies",
            "task_statuses",
            "task_tags",
            "task_tags_link",
        )
        for table in tenant_tables:
            with self.subTest(table=table):
                match = re.search(
                    rf"alter table(?: if exists)? {table} (?P<body>.*?);",
                    normalized,
                )
                self.assertIsNotNone(match)
                self.assertRegex(
                    match.group("body"),
                    r"add column if not exists company_id\b",
                )

    def test_dynamic_constraints_are_guarded_for_repeat_execution(self):
        normalized = re.sub(r"\s+", " ", self.sql).casefold()
        self.assertIn("from pg_constraint", normalized)
        self.assertIn("if not exists", normalized)
        self.assertIn("ck_employees_role", normalized)
        self.assertIn("foreign key (company_id)", normalized)

    def test_repeatable_ddl_guards_are_present(self):
        for path, sql in self.migrations:
            statements = [item.strip() for item in sql.split(";") if item.strip()]
            for statement in statements:
                compact = re.sub(r"\s+", " ", statement).casefold()
                if compact.startswith("create table"):
                    with self.subTest(path=path.name, statement=compact[:100]):
                        self.assertTrue(compact.startswith("create table if not exists"))
                if compact.startswith("create index") or compact.startswith("create unique index"):
                    with self.subTest(path=path.name, statement=compact[:100]):
                        self.assertIn("if not exists", compact)
                if re.match(r"alter table(?: if exists)? \w+ add column", compact):
                    with self.subTest(path=path.name, statement=compact[:100]):
                        self.assertIn("add column if not exists", compact)

    def test_migration_does_not_contain_destructive_company_operations(self):
        normalized = re.sub(r"\s+", " ", self.sql).casefold()
        forbidden = (
            "drop table companies",
            "truncate companies",
            "delete from companies",
        )
        for fragment in forbidden:
            with self.subTest(fragment=fragment):
                self.assertNotIn(fragment, normalized)


if __name__ == "__main__":
    unittest.main()
