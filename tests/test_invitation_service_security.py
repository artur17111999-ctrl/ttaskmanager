import hashlib
import json
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = PROJECT_ROOT / "sticky_crm"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

import invitation_service


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
        normalized = " ".join(sql.split()).casefold()
        self.executed.append((normalized, bound))
        result = self.responder(normalized, bound)
        self.current = result if isinstance(result, _Result) else _Result(one=result)
        self.rowcount = self.current.rowcount if self.current.rowcount is not None else -1

    def fetchone(self):
        return self.current.one

    def fetchall(self):
        return list(self.current.many)

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

    def cursor(self):
        return self._cursor

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closed = True


def _account_data(**overrides):
    data = {
        "login": "new.user",
        "password": "StrongPassword!234",
        "password_confirmation": "StrongPassword!234",
        "birth_date": "1990-01-01",
        "policy_version": "1",
    }
    data.update(overrides)
    return data


def _profile():
    return {
        "last_name": "Иванов",
        "first_name": "Иван",
        "middle_name": "Иванович",
        "position_id": 4,
        "department_id": 5,
        "start_date": "2026-08-06",
    }


def _invitation_row(*, accepted_at=None, revoked_at=None, superseded_by_id=None):
    return (
        51,
        7,
        "new@example.test",
        "employee",
        _profile(),
        datetime.now() + timedelta(days=3),
        accepted_at,
        revoked_at,
        superseded_by_id,
        101,
    )


def _actor_row(role="company_owner"):
    return (101, 7, role, False, "active", 101 if role == "company_owner" else 999)


class _AcceptanceScenario:
    def __init__(self, *, active_count=14, reserved_count=1):
        self.active_count = active_count
        self.reserved_count = reserved_count
        self.accepted_at = None
        self.employee_inserts = 0
        self.account_inserts = 0
        self.connections = []

    def connection(self):
        connection = _Connection(self.respond)
        self.connections.append(connection)
        return connection

    @property
    def executed(self):
        return [item for connection in self.connections for item in connection.executed]

    def respond(self, sql, params):
        if "select id, company_id from company_invitations" in sql:
            return (51, 7)
        if "from companies" in sql and "for update" in sql:
            return (7, "Acme", 15, "active")
        if "from company_invitations invitation" in sql and "for update" in sql:
            return _invitation_row(accepted_at=self.accepted_at)
        if "from idempotency_requests" in sql:
            return None
        if "count(*)" in sql and "from employees" in sql:
            return (self.active_count,)
        if "count(*)" in sql and "from company_invitations" in sql:
            return (self.reserved_count,)
        if "select 1 from employees where lower" in sql:
            return None
        if "select 1 from accounts where lower" in sql:
            return None
        if "select id from positions" in sql:
            return (4,)
        if "select id from departments" in sql:
            return (5,)
        if "insert into employees" in sql:
            self.employee_inserts += 1
            return (202,)
        if "insert into accounts" in sql:
            self.account_inserts += 1
            return (303,)
        if sql.startswith("update company_invitations") and "accepted_employee_id" in sql:
            self.accepted_at = datetime.now()
            return (self.accepted_at,)
        return _Result(rowcount=1)


class InvitationPublicErrorTests(unittest.TestCase):
    def test_unknown_expired_revoked_and_accepted_share_one_public_error(self):
        def no_invitation(sql, params):
            if "from company_invitations invitation" in sql:
                return None
            return _Result()

        messages = []
        connections = []
        for state in ("unknown", "expired", "revoked", "accepted"):
            connection = _Connection(no_invitation)
            connections.append(connection)
            with patch.object(
                invitation_service, "get_connection", return_value=connection
            ):
                with self.assertRaises(
                    invitation_service.InvalidInvitationError
                ) as raised:
                    invitation_service.inspect_invitation((state + "A" * 40)[:40])
            messages.append(str(raised.exception))

        self.assertEqual(len(set(messages)), 1)
        self.assertEqual(messages[0], invitation_service.INVALID_INVITATION_MESSAGE)
        self.assertNotRegex(messages[0].casefold(), r"unknown|expired|revoked|accepted")

    def test_malformed_token_uses_fixed_probe_and_same_public_error(self):
        connection = _Connection(lambda sql, params: None)
        with patch.object(invitation_service, "get_connection", return_value=connection):
            with self.assertRaises(invitation_service.InvalidInvitationError) as raised:
                invitation_service.inspect_invitation("not valid token")

        query_params = next(
            params
            for sql, params in connection.executed
            if "from company_invitations invitation" in sql
        )
        self.assertEqual(len(query_params[0]), 64)
        self.assertNotIn("not valid token", query_params)
        self.assertEqual(str(raised.exception), invitation_service.INVALID_INVITATION_MESSAGE)


class InvitationAcceptanceSecurityTests(unittest.TestCase):
    def test_company_role_and_ownership_fields_are_rejected_before_database_access(self):
        for field in (
            "company_id",
            "role",
            "requested_role",
            "owner_employee_id",
            "employee_limit",
            "is_dismissed",
            "status",
            "account_status",
            "position_id",
            "department_id",
            "email",
        ):
            with self.subTest(field=field):
                get_connection = Mock()
                with patch.object(invitation_service, "get_connection", get_connection):
                    with self.assertRaises(invitation_service.ValidationError):
                        invitation_service.accept_invitation(
                            "A" * 43,
                            _account_data(**{field: 999}),
                        )
                get_connection.assert_not_called()

    def test_pending_seat_converts_to_active_without_double_counting(self):
        scenario = _AcceptanceScenario(active_count=14, reserved_count=1)
        with patch.object(
            invitation_service, "get_connection", side_effect=scenario.connection
        ), patch.object(invitation_service.bcrypt, "gensalt", return_value=b"salt"), patch.object(
            invitation_service.bcrypt, "hashpw", return_value=b"hashed-password"
        ):
            result = invitation_service.accept_invitation(
                "A" * 43,
                _account_data(),
                idempotency_key="accept-request-1",
            )

        self.assertEqual(result["employee_id"], 202)
        self.assertEqual(result["account_id"], 303)
        self.assertEqual(scenario.employee_inserts, 1)
        self.assertEqual(scenario.account_inserts, 1)
        self.assertEqual(scenario.connections[0].commits, 1)
        employee_insert = next(
            params for sql, params in scenario.executed if "insert into employees" in sql
        )
        self.assertEqual(employee_insert[-2], 7, "company_id must come from invitation")
        self.assertEqual(employee_insert[-1], "employee", "role must come from invitation")

    def test_over_limit_state_rolls_back_before_creating_identity(self):
        scenario = _AcceptanceScenario(active_count=15, reserved_count=1)
        with patch.object(
            invitation_service, "get_connection", side_effect=scenario.connection
        ):
            with self.assertRaises(invitation_service.SeatLimitError):
                invitation_service.accept_invitation("A" * 43, _account_data())

        self.assertEqual(scenario.employee_inserts, 0)
        self.assertEqual(scenario.account_inserts, 0)
        self.assertEqual(scenario.connections[0].rollbacks, 1)

    def test_one_token_creates_at_most_one_employee_and_account(self):
        scenario = _AcceptanceScenario(active_count=14, reserved_count=1)
        patches = (
            patch.object(invitation_service, "get_connection", side_effect=scenario.connection),
            patch.object(invitation_service.bcrypt, "gensalt", return_value=b"salt"),
            patch.object(invitation_service.bcrypt, "hashpw", return_value=b"hashed-password"),
        )
        with patches[0], patches[1], patches[2]:
            invitation_service.accept_invitation("A" * 43, _account_data())
            with self.assertRaises(invitation_service.InvalidInvitationError):
                invitation_service.accept_invitation(
                    "A" * 43,
                    _account_data(login="another.user"),
                )

        self.assertEqual(scenario.employee_inserts, 1)
        self.assertEqual(scenario.account_inserts, 1)
        self.assertEqual(scenario.connections[0].commits, 1)
        self.assertEqual(scenario.connections[1].rollbacks, 1)

    def test_accept_locks_company_then_invitation_before_identity_inserts(self):
        scenario = _AcceptanceScenario()
        with patch.object(
            invitation_service, "get_connection", side_effect=scenario.connection
        ), patch.object(invitation_service.bcrypt, "gensalt", return_value=b"salt"), patch.object(
            invitation_service.bcrypt, "hashpw", return_value=b"hashed-password"
        ):
            invitation_service.accept_invitation("A" * 43, _account_data())

        sql = [query for query, _ in scenario.executed]
        company_lock = next(
            index
            for index, query in enumerate(sql)
            if "from companies" in query and "for update" in query
        )
        invitation_lock = next(
            index
            for index, query in enumerate(sql)
            if "from company_invitations invitation" in query and "for update" in query
        )
        employee_insert = next(
            index for index, query in enumerate(sql) if "insert into employees" in query
        )
        self.assertLess(company_lock, invitation_lock)
        self.assertLess(invitation_lock, employee_insert)

    def test_idempotency_storage_contains_hashes_and_no_password_or_token(self):
        scenario = _AcceptanceScenario()
        raw_token = "T" * 43
        raw_key = "caller-idempotency-key"
        password = "StrongPassword!234"
        with patch.object(
            invitation_service, "get_connection", side_effect=scenario.connection
        ), patch.object(invitation_service.bcrypt, "gensalt", return_value=b"salt"), patch.object(
            invitation_service.bcrypt, "hashpw", return_value=b"hashed-password"
        ):
            invitation_service.accept_invitation(
                raw_token,
                _account_data(password=password, password_confirmation=password),
                idempotency_key=raw_key,
            )

        sql, params = next(
            (sql, params)
            for sql, params in scenario.executed
            if "insert into idempotency_requests" in sql
        )
        serialized = json.dumps(params, default=str)
        self.assertNotIn(raw_token, serialized)
        self.assertNotIn(raw_key, serialized)
        self.assertNotIn(password, serialized)
        self.assertEqual(params[0], hashlib.sha256(raw_key.encode()).hexdigest())


class InvitationAdministrationSecurityTests(unittest.TestCase):
    @staticmethod
    def _connection_for_admin_operation(*, new_token_id=52):
        now = datetime.now()

        def responder(sql, params):
            if "from employees employee" in sql and "join companies" in sql:
                return _actor_row()
            if "from companies" in sql and "for update" in sql:
                return (7, "Acme", 15, "active")
            if "from company_invitations" in sql and "for update" in sql:
                return _invitation_row() + (now,)
            if "insert into company_invitations" in sql:
                return (new_token_id, now)
            if "returning revoked_at" in sql:
                return (now,)
            return _Result(rowcount=1)

        return _Connection(responder)

    def test_revoke_uses_company_then_invitation_lock_order(self):
        connection = self._connection_for_admin_operation()
        with patch.object(invitation_service, "get_connection", return_value=connection):
            result = invitation_service.revoke_invitation(101, 51)

        self.assertEqual(result["status"], "revoked")
        sql = [query for query, _ in connection.executed]
        company_lock = next(
            i for i, query in enumerate(sql) if "from companies" in query and "for update" in query
        )
        invitation_lock = next(
            i
            for i, query in enumerate(sql)
            if "from company_invitations" in query and "for update" in query
        )
        revoke_update = next(
            i
            for i, query in enumerate(sql)
            if query.startswith("update company_invitations") and "revoked_at" in query
        )
        self.assertLess(company_lock, invitation_lock)
        self.assertLess(invitation_lock, revoke_update)

    def test_resend_rotates_hash_and_does_not_create_a_second_reservation_first(self):
        connection = self._connection_for_admin_operation()
        new_token = "new-secure-delivery-token"
        with patch.object(invitation_service, "get_connection", return_value=connection), patch.object(
            invitation_service.secrets, "token_urlsafe", return_value=new_token
        ):
            result = invitation_service.resend_invitation(101, 51)

        self.assertEqual(result["id"], 52)
        self.assertEqual(result["supersedes_id"], 51)
        self.assertEqual(result["delivery_token"], new_token)
        sql = [query for query, _ in connection.executed]
        revoke_old = next(
            i
            for i, query in enumerate(sql)
            if query.startswith("update company_invitations") and "coalesce(revoked_at" in query
        )
        insert_new = next(
            i for i, query in enumerate(sql) if "insert into company_invitations" in query
        )
        link_old = next(
            i
            for i, query in enumerate(sql)
            if query.startswith("update company_invitations") and "superseded_by_id" in query
        )
        self.assertLess(revoke_old, insert_new)
        self.assertLess(insert_new, link_old)
        insert_params = connection.executed[insert_new][1]
        self.assertNotIn(new_token, insert_params)
        self.assertIn(hashlib.sha256(new_token.encode()).hexdigest(), insert_params)


if __name__ == "__main__":
    unittest.main()
