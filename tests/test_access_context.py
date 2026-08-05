import sys
import unittest
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = PROJECT_ROOT / "sticky_crm"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

import db
from access_context import AccessContext, coerce_access_context


REQUIRED_CONTEXT_KEYS = {
    "account_id",
    "employee_id",
    "full_name",
    "company_id",
    "company_name",
    "role",
    "status",
    "company_status",
    "principal_trusted",
    "session_generation",
}


class _CursorStub:
    def __init__(self, table_columns, login_row):
        self.table_columns = table_columns
        self.login_row = login_row
        self.executed = []
        self._fetch_mode = None
        self._table_name = None
        self.closed = False

    def execute(self, query, params=None):
        self.executed.append((query, params))
        compact = " ".join(str(query).split()).casefold()
        if "information_schema.columns" in compact:
            self._fetch_mode = "columns"
            self._table_name = params[0]
        else:
            self._fetch_mode = "login"

    def fetchall(self):
        if self._fetch_mode != "columns":
            return []
        return [(column,) for column in self.table_columns.get(self._table_name, ())]

    def fetchone(self):
        if self._fetch_mode == "login":
            return self.login_row
        return None

    def close(self):
        self.closed = True


class _ConnectionStub:
    def __init__(self, cursor):
        self._cursor = cursor
        self.closed = False

    def cursor(self):
        return self._cursor

    def close(self):
        self.closed = True


def _login_row(
    *,
    company_id=7,
    company_name="Компания A",
    role="company_admin",
    employee_status="active",
    company_status="active",
    is_locked=False,
    is_dismissed=False,
):
    return (
        1,
        "$2b$stub",
        is_locked,
        2,
        "Иванов",
        "Иван",
        None,
        "ivanov@example.test",
        is_dismissed,
        company_id,
        company_name,
        role,
        employee_status,
        company_status,
    )


class AccessContextContractTests(unittest.TestCase):
    def test_access_context_is_mapping_with_required_fields(self):
        context = AccessContext(
            account_id=1,
            employee_id=2,
            last_name="Иванов",
            first_name="Иван",
            middle_name=None,
            email="ivanov@example.test",
            full_name="Иванов Иван",
            company_id=7,
            company_name="Компания A",
            role="employee",
        )

        self.assertTrue(REQUIRED_CONTEXT_KEYS.issubset(context.keys()))
        self.assertEqual(context["company_id"], 7)
        self.assertEqual(context.to_dict()["role"], "employee")
        with self.assertRaises(Exception):
            context.company_id = 8

    def test_legacy_user_data_is_coerced_without_breaking_login(self):
        context = coerce_access_context(
            {
                "account_id": 1,
                "employee_id": 2,
                "last_name": "Иванов",
                "first_name": "Иван",
                "email": "ivanov@example.test",
            }
        )

        self.assertEqual(context.full_name, "Иванов Иван")
        self.assertIsNone(context.company_id)
        self.assertEqual(context.role, "employee")
        self.assertFalse(context.principal_trusted)


class CheckUserAccessContextTests(unittest.TestCase):
    def _run_check_user(self, columns, row, password_matches=True):
        cursor = _CursorStub(columns, row)
        connection = _ConnectionStub(cursor)
        with patch.object(db, "get_connection", return_value=connection), patch(
            "bcrypt.checkpw", return_value=password_matches
        ):
            result = db.check_user("ivanov", "secret")
        return result, cursor, connection

    def test_login_returns_complete_company_context(self):
        columns = {
            "employees": {"company_id", "role", "status", "is_dismissed"},
            "companies": {"id", "name", "status"},
        }
        (success, context), cursor, connection = self._run_check_user(
            columns, _login_row()
        )

        self.assertTrue(success)
        self.assertIsInstance(context, AccessContext)
        self.assertTrue(REQUIRED_CONTEXT_KEYS.issubset(context.keys()))
        self.assertEqual(context.company_id, 7)
        self.assertEqual(context.company_name, "Компания A")
        self.assertEqual(context.role, "company_admin")
        self.assertFalse(context.principal_trusted)
        self.assertTrue(cursor.closed)
        self.assertTrue(connection.closed)
        login_sql = next(
            query for query, _ in cursor.executed if "FROM accounts" in query
        )
        self.assertIn("LEFT JOIN companies", login_sql)

    def test_login_remains_compatible_before_tenant_columns_are_available(self):
        columns = {
            "employees": {"is_dismissed"},
            "companies": set(),
        }
        row = _login_row(
            company_id=None,
            company_name=None,
            role="employee",
            company_status=None,
        )
        success, context = self._run_check_user(columns, row)[0]

        self.assertTrue(success)
        self.assertIsNone(context.company_id)
        self.assertIsNone(context.company_name)
        self.assertEqual(context.role, "employee")

    def test_blocked_company_cannot_log_in(self):
        columns = {
            "employees": {"company_id", "role", "status", "is_dismissed"},
            "companies": {"id", "name", "status"},
        }
        success, message = self._run_check_user(
            columns, _login_row(company_status="blocked")
        )[0]

        self.assertFalse(success)
        self.assertEqual(message, "Компания не имеет доступа к системе")

    def test_wrong_password_does_not_return_access_context(self):
        columns = {
            "employees": {"company_id", "role", "status", "is_dismissed"},
            "companies": {"id", "name", "status"},
        }
        success, message = self._run_check_user(
            columns, _login_row(), password_matches=False
        )[0]

        self.assertFalse(success)
        self.assertEqual(message, "Неверный логин или пароль")


if __name__ == "__main__":
    unittest.main()
