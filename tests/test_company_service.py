import json
import sys
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = PROJECT_ROOT / "sticky_crm"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

import company_service
from access_context import AccessContext


class _Result:
    def __init__(self, one=None, many=None, rowcount=None):
        self.one = one
        self.many = list(many or ())
        self.rowcount = rowcount


class _Cursor:
    def __init__(self, responder):
        self.responder = responder
        self.executed = []
        self.current = _Result()
        self.rowcount = -1
        self.closed = False

    def execute(self, query, params=None):
        sql = str(query)
        bound = tuple(params or ())
        self.executed.append((sql, bound))
        result = self.responder(" ".join(sql.split()).casefold(), bound)
        self.current = result if isinstance(result, _Result) else _Result(one=result)
        self.rowcount = (
            self.current.rowcount if self.current.rowcount is not None else -1
        )

    def fetchone(self):
        return self.current.one

    def fetchall(self):
        return list(self.current.many)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    def close(self):
        self.closed = True


class _Connection:
    def __init__(self, responder):
        self._cursor = _Cursor(responder)
        self.commits = 0
        self.rollbacks = 0
        self.closed = False

    @property
    def executed(self):
        return self._cursor.executed

    def cursor(self, *args, **kwargs):
        return self._cursor

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closed = True

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if exc_type is None:
            self.commit()
        else:
            self.rollback()
        self.close()


def _actor_row(
    *, employee_id=101, company_id=7, role="company_owner", company_status="active"
):
    owner_employee_id = None
    if company_id is not None:
        owner_employee_id = employee_id if role == "company_owner" else 999
    return (
        employee_id,
        company_id,
        role,
        False,
        company_status if company_id is not None else None,
        owner_employee_id,
    )


def _company_row(company_id=7):
    now = datetime(2026, 8, 5, 12, 0, 0)
    return (
        company_id,
        "Acme",
        "6671000000",
        "667101001",
        "Legal address",
        "Actual address",
        "office@example.test",
        "https://example.test",
        "active",
        101,
        15,
        "default",
        1,
        now,
        now,
    )


def _is_actor_query(sql, params, actor_id=101):
    return (
        "from employees" in sql
        and params
        and params[0] == actor_id
        and ("company_status" in sql or "join companies" in sql)
    )


def _invitation_data(**overrides):
    data = {
        "email": "new@example.test",
        "last_name": "Employee",
        "first_name": "Test",
        "requested_role": "employee",
    }
    data.update(overrides)
    return data


class CompanyServicePermissionTests(unittest.TestCase):
    def _call(self, responder, function, *args, **kwargs):
        connection = _Connection(responder)
        with patch.object(company_service, "get_connection", return_value=connection):
            result = function(*args, **kwargs)
        return result, connection

    def test_employee_without_company_can_create_company_and_becomes_owner(self):
        company = _company_row()

        def responder(sql, params):
            if _is_actor_query(sql, params):
                return _actor_row(company_id=None, role="employee")
            if "insert into companies" in sql:
                return (company[0],)
            if "update employees" in sql:
                return _Result(rowcount=1)
            if "from companies company" in sql:
                return company
            return _Result(rowcount=1)

        result, connection = self._call(
            responder,
            company_service.create_company,
            101,
            {
                "name": "Acme",
                "inn": "6671000000",
                "kpp": "667101001",
                "legal_address": "Legal address",
                "actual_address": "Actual address",
                "contact_email": "office@example.test",
                "website_url": "https://example.test",
            },
        )

        self.assertEqual(result["id"], 7)
        self.assertEqual(result["employee_limit"], 15)
        sql = "\n".join(item[0].casefold() for item in connection.executed)
        self.assertIn("insert into companies", sql)
        self.assertIn("update employees", sql)
        self.assertIn("company_owner", sql)
        self.assertEqual(connection.commits, 1)

    def test_assigned_employee_cannot_create_second_company(self):
        def responder(sql, params):
            if _is_actor_query(sql, params):
                return _actor_row(role="employee")
            return _Result(rowcount=1)

        connection = _Connection(responder)
        with patch.object(company_service, "get_connection", return_value=connection):
            with self.assertRaises(
                (company_service.PermissionDenied, company_service.ConflictError)
            ):
                company_service.create_company(
                    101, {"name": "Acme", "inn": "6671000000"}
                )
        self.assertFalse(
            any("insert into companies" in sql.casefold() for sql, _ in connection.executed)
        )

    def test_delegated_admin_has_employee_rights_but_not_company_manage(self):
        def responder(sql, params):
            if _is_actor_query(sql, params):
                return _actor_row(role="company_admin")
            return _Result(rowcount=1)

        connection = _Connection(responder)
        with patch.object(company_service, "get_connection", return_value=connection):
            with self.assertRaises(company_service.PermissionDenied):
                company_service.update_company(101, {"name": "Changed"})
        self.assertFalse(
            any("update companies" in sql.casefold() for sql, _ in connection.executed)
        )

    def test_regular_employee_cannot_open_company_service(self):
        def responder(sql, params):
            if _is_actor_query(sql, params):
                return _actor_row(role="employee")
            return _company_row()

        connection = _Connection(responder)
        with patch.object(company_service, "get_connection", return_value=connection):
            with self.assertRaises(company_service.PermissionDenied):
                company_service.get_company(101)

    def test_spoofed_access_context_does_not_override_database_role(self):
        spoofed = AccessContext(
            account_id=1,
            employee_id=101,
            last_name="User",
            first_name="Test",
            middle_name=None,
            email="user@example.test",
            full_name="Test User",
            company_id=999,
            company_name="Foreign",
            role="company_owner",
        )

        def responder(sql, params):
            if _is_actor_query(sql, params):
                return _actor_row(company_id=7, role="employee")
            return _Result(rowcount=1)

        connection = _Connection(responder)
        with patch.object(company_service, "get_connection", return_value=connection):
            with self.assertRaises(company_service.PermissionDenied):
                company_service.update_company(spoofed, {"name": "Foreign changed"})
        self.assertFalse(
            any("update companies" in sql.casefold() for sql, _ in connection.executed)
        )


class InvitationLimitAndIsolationTests(unittest.TestCase):
    def _invitation_responder(self, *, active_count, reserved_count, target=None):
        company = _company_row()

        def responder(sql, params):
            if _is_actor_query(sql, params):
                return _actor_row(role="company_admin")
            if "from companies" in sql and "for update" in sql:
                return (company[10], company[8])
            if "count(" in sql and "from employees" in sql:
                return (active_count,)
            if "count(" in sql and "from company_invitations" in sql:
                return (reserved_count,)
            if "from company_invitations" in sql and "count(" not in sql:
                return None
            if "insert into company_invitations" in sql:
                return (501, datetime(2026, 8, 5, 12, 0, 0))
            if "from employees" in sql and params and params[0] != 101:
                return target
            return _Result(rowcount=1)

        return responder

    def _create_invitation(self, responder):
        connection = _Connection(responder)
        with patch.object(company_service, "get_connection", return_value=connection):
            result = company_service.create_invitation(
                101,
                _invitation_data(email=" New@Example.Test "),
            )
        return result, connection

    def test_pending_invitation_reserves_the_last_seat(self):
        responder = self._invitation_responder(active_count=14, reserved_count=1)
        connection = _Connection(responder)
        with patch.object(company_service, "get_connection", return_value=connection):
            with self.assertRaises(company_service.SeatLimitError):
                company_service.create_invitation(
                    101,
                    _invitation_data(),
                )
        self.assertFalse(
            any(
                "insert into company_invitations" in sql.casefold()
                for sql, _ in connection.executed
            )
        )
        self.assertGreaterEqual(connection.rollbacks, 1)

    def test_invitation_locks_company_before_counting_and_inserting(self):
        result, connection = self._create_invitation(
            self._invitation_responder(active_count=10, reserved_count=1)
        )
        normalized = [" ".join(sql.split()).casefold() for sql, _ in connection.executed]
        lock_index = next(
            i
            for i, sql in enumerate(normalized)
            if "from companies" in sql and "for update" in sql
        )
        count_indexes = [
            i
            for i, sql in enumerate(normalized)
            if i > lock_index and "count(" in sql
        ]
        insert_index = next(
            i
            for i, sql in enumerate(normalized)
            if "insert into company_invitations" in sql
        )

        self.assertTrue(count_indexes, "Seat counts must be read after the row lock")
        self.assertLess(lock_index, min(count_indexes))
        self.assertLess(max(count_indexes), insert_index)
        invitation_insert = next(
            params
            for sql, params in connection.executed
            if "insert into company_invitations" in sql.casefold()
        )
        self.assertEqual(invitation_insert[0], 7)
        self.assertEqual(result["email"], "new@example.test")
        self.assertIn("delivery_token", result)

    def test_input_company_id_is_rejected(self):
        responder = self._invitation_responder(active_count=1, reserved_count=0)
        connection = _Connection(responder)
        with patch.object(company_service, "get_connection", return_value=connection):
            with self.assertRaises(company_service.ValidationError):
                company_service.create_invitation(
                    101,
                    _invitation_data(company_id=999),
                )
        self.assertFalse(
            any(
                "insert into company_invitations" in sql.casefold()
                for sql, _ in connection.executed
            )
        )

    def test_cross_tenant_employee_is_not_mutated(self):
        responder = self._invitation_responder(
            active_count=1,
            reserved_count=0,
            target=None,
        )
        connection = _Connection(responder)
        with patch.object(company_service, "get_connection", return_value=connection):
            with self.assertRaises(
                (company_service.NotFoundError, company_service.PermissionDenied)
            ):
                company_service.dismiss_employee(101, 202)

        target_queries = [
            (" ".join(sql.split()).casefold(), params)
            for sql, params in connection.executed
            if params and 202 in params
        ]
        self.assertTrue(target_queries)
        self.assertTrue(
            any("company_id" in sql for sql, _ in target_queries),
            "Target lookup/update must be scoped to the actor company",
        )
        self.assertFalse(
            any(
                sql.startswith("update employees") and 202 in params
                for sql, params in target_queries
            )
        )

    def test_usage_count_explicitly_excludes_system_admin(self):
        responder = self._invitation_responder(active_count=3, reserved_count=2)
        connection = _Connection(responder)
        with patch.object(company_service, "get_connection", return_value=connection):
            usage = company_service.get_company_usage(101)

        active_query = next(
            " ".join(sql.split()).casefold()
            for sql, _ in connection.executed
            if "count(" in sql.casefold() and "from employees" in sql.casefold()
        )
        self.assertIn("role", active_query)
        self.assertIn("system_admin", active_query)
        self.assertEqual(usage["active_count"], 3)
        self.assertEqual(usage["reserved_count"], 2)
        self.assertEqual(usage["free_count"], 10)

    def test_invitation_profile_is_normalized_and_persisted(self):
        result, connection = self._create_invitation(
            self._invitation_responder(active_count=1, reserved_count=0)
        )
        self.assertEqual(
            result["profile_data"],
            {"last_name": "Employee", "first_name": "Test"},
        )
        insert_sql, insert_params = next(
            (" ".join(sql.split()).casefold(), params)
            for sql, params in connection.executed
            if "insert into company_invitations" in sql.casefold()
        )
        self.assertIn("profile_data", insert_sql)
        self.assertEqual(json.loads(insert_params[-1]), result["profile_data"])
        self.assertEqual(len(insert_params[3]), 64)
        self.assertNotEqual(insert_params[3], result["delivery_token"])

    def test_invitation_requires_first_and_last_name(self):
        for missing in ("first_name", "last_name"):
            with self.subTest(missing=missing):
                data = _invitation_data()
                data.pop(missing)
                with self.assertRaises(company_service.ValidationError):
                    company_service.create_invitation(101, data)

        with self.assertRaises(company_service.ValidationError):
            company_service.create_invitation(
                101, _invitation_data(first_name="   ")
            )

    def test_email_conflict_message_does_not_reveal_account_or_invitation(self):
        messages = []
        for conflict_source in ("employee", "invitation"):
            base = self._invitation_responder(active_count=1, reserved_count=0)

            def responder(sql, params, source=conflict_source):
                if "select 1 from employees where lower" in sql:
                    return (1,) if source == "employee" else None
                if (
                    "select 1" in sql
                    and "from company_invitations" in sql
                    and "count(" not in sql
                ):
                    return (1,) if source == "invitation" else None
                return base(sql, params)

            connection = _Connection(responder)
            with patch.object(
                company_service, "get_connection", return_value=connection
            ):
                with self.assertRaises(company_service.ConflictError) as raised:
                    company_service.create_invitation(101, _invitation_data())
            messages.append(str(raised.exception))

        self.assertEqual(messages[0], messages[1])
        self.assertNotIn("account", messages[0].casefold())
        self.assertNotIn("pending", messages[0].casefold())

    def test_active_tasks_block_dismissal_before_employee_update(self):
        def responder(sql, params):
            if _is_actor_query(sql, params):
                return _actor_row(role="company_admin")
            if "from employees target" in sql:
                return (202, 7, "employee", False, "target@example.test", 999)
            if "from tasks" in sql and "count(" in sql:
                return (2,)
            return _Result(rowcount=1)

        connection = _Connection(responder)
        with patch.object(company_service, "get_connection", return_value=connection):
            with self.assertRaises(company_service.ConflictError) as raised:
                company_service.dismiss_employee(101, 202)

        self.assertIn("active", str(raised.exception).casefold())
        self.assertFalse(
            any(
                "update employees" in sql.casefold()
                for sql, _ in connection.executed
            )
        )


if __name__ == "__main__":
    unittest.main()
