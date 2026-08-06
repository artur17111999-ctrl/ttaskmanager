import hashlib
import json
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = PROJECT_ROOT / "sticky_crm"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

import invitation_service


VALID_TOKEN = "A" * 43
VALID_PASSWORD = "Strong pass 123!"


class _Cursor:
    def __init__(self, responder):
        self.responder = responder
        self.executed = []
        self.current = None
        self.rowcount = 0

    def execute(self, sql, params=None):
        params = tuple(params or ())
        self.executed.append((sql, params))
        result = self.responder(" ".join(sql.split()).casefold(), params)
        self.current = result
        self.rowcount = getattr(result, "rowcount", 1 if result is not None else 0)

    def fetchone(self):
        if isinstance(self.current, list):
            return self.current.pop(0) if self.current else None
        return self.current

    def fetchall(self):
        if self.current is None:
            return []
        if isinstance(self.current, list):
            return list(self.current)
        return [self.current]

    def close(self):
        pass


class _Connection:
    def __init__(self, responder):
        self.cursor_value = _Cursor(responder)
        self.commits = 0
        self.rollbacks = 0
        self.closed = False

    def cursor(self):
        return self.cursor_value

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closed = True


class _WriteResult:
    def __init__(self, rowcount=1):
        self.rowcount = rowcount


def _account_data(**changes):
    data = {
        "login": "new.user",
        "password": VALID_PASSWORD,
        "password_confirmation": VALID_PASSWORD,
        "birth_date": "1990-01-02",
        "policy_version": "2026-08",
    }
    data.update(changes)
    return data


class InvitationValidationTests(unittest.TestCase):
    def test_accept_rejects_client_controlled_tenant_and_role(self):
        for field, value in (("company_id", 999), ("role", "company_owner")):
            with self.subTest(field=field):
                with patch.object(invitation_service, "get_connection") as connection:
                    with self.assertRaises(invitation_service.ValidationError):
                        invitation_service.accept_invitation(
                            VALID_TOKEN,
                            _account_data(**{field: value}),
                        )
                connection.assert_not_called()

    def test_birth_date_is_required_by_the_employee_schema(self):
        with self.assertRaises(invitation_service.ValidationError):
            invitation_service._normalize_account_data(
                _account_data(birth_date=None)
            )

    def test_bcrypt_byte_limit_is_enforced_for_unicode_passwords(self):
        with self.assertRaises(invitation_service.ValidationError):
            invitation_service._validate_password("я" * 40)

    def test_all_unavailable_public_states_use_one_error_message(self):
        responses = [None, None]

        def responder(sql, params):
            return responses.pop(0) if responses else None

        messages = []
        for token in ("short", VALID_TOKEN):
            connection = _Connection(responder)
            with patch.object(
                invitation_service, "get_connection", return_value=connection
            ):
                with self.assertRaises(
                    invitation_service.InvalidInvitationError
                ) as raised:
                    invitation_service.inspect_invitation(token)
            messages.append(str(raised.exception))
        self.assertEqual(messages, [invitation_service.INVALID_INVITATION_MESSAGE] * 2)


class InvitationInspectionTests(unittest.TestCase):
    def test_inspect_returns_only_safe_preview_and_queries_by_digest(self):
        expires_at = datetime.now() + timedelta(days=1)

        def responder(sql, params):
            return (
                "new@example.test",
                "employee",
                {
                    "last_name": "Иванов",
                    "first_name": "Иван",
                    "position_id": 10,
                    "department_id": 20,
                },
                expires_at,
                "Acme",
                "Инженер",
                "ИТ",
            )

        connection = _Connection(responder)
        with patch.object(
            invitation_service, "get_connection", return_value=connection
        ):
            preview = invitation_service.inspect_invitation(VALID_TOKEN)

        self.assertEqual(preview["company_name"], "Acme")
        self.assertEqual(preview["email"], "new@example.test")
        self.assertEqual(preview["profile_data"]["position"], "Инженер")
        self.assertEqual(preview["profile_data"]["department"], "ИТ")
        self.assertNotIn("position_id", preview["profile_data"])
        self.assertNotIn("department_id", preview["profile_data"])
        self.assertIn("preview_id", preview)
        self.assertNotIn("company_id", preview)
        self.assertNotIn("employee_limit", preview)
        query_params = connection.cursor_value.executed[0][1]
        self.assertEqual(
            query_params,
            (hashlib.sha256(VALID_TOKEN.encode("utf-8")).hexdigest(),),
        )
        self.assertNotIn(VALID_TOKEN, query_params)


class InvitationAcceptanceServiceTests(unittest.TestCase):
    def _success_responder(self, *, accepted=False, idempotent_response=None):
        profile = {
            "last_name": "Иванов",
            "first_name": "Иван",
            "middle_name": None,
            "start_date": "2026-08-10",
            "position_id": 10,
            "department_id": 20,
        }
        expires_at = datetime.now() + timedelta(days=1)

        def responder(sql, params):
            if sql.startswith("select id, company_id from company_invitations"):
                return (501, 7)
            if "from companies" in sql and "for update" in sql:
                return (7, "Acme", 15, "active")
            if "from company_invitations invitation" in sql and "for update" in sql:
                return (
                    501,
                    7,
                    "new@example.test",
                    "employee",
                    profile,
                    expires_at,
                    datetime.now() if accepted else None,
                    None,
                    None,
                    101,
                )
            if "from idempotency_requests" in sql:
                if idempotent_response is None:
                    return None
                normalized = invitation_service._normalize_account_data(_account_data())
                token_hash, _ = invitation_service._token_digest(VALID_TOKEN)
                return (
                    501,
                    invitation_service._request_digest(token_hash, normalized),
                    200,
                    idempotent_response,
                )
            if "count(*) from employees" in sql:
                return (4,)
            if "count(*) from company_invitations" in sql:
                return (3,)
            if sql.startswith("select 1 from employees"):
                return None
            if sql.startswith("select 1 from accounts"):
                return None
            if sql.startswith("select id from positions"):
                return (10,)
            if sql.startswith("select id from departments"):
                return (20,)
            if sql.startswith("insert into employees"):
                return (601,)
            if sql.startswith("insert into accounts"):
                return (701,)
            if sql.startswith("update company_invitations") and "returning accepted_at" in sql:
                return (datetime.now(),)
            return _WriteResult()

        return responder

    def test_accept_is_atomic_uses_company_first_lock_and_persists_no_raw_secrets(self):
        connection = _Connection(self._success_responder())
        with patch.object(
            invitation_service, "get_connection", return_value=connection
        ), patch.object(
            invitation_service.bcrypt, "gensalt", return_value=b"salt"
        ), patch.object(
            invitation_service.bcrypt, "hashpw", return_value=b"bcrypt-hash"
        ):
            result = invitation_service.accept_invitation(
                VALID_TOKEN,
                _account_data(),
                idempotency_key="request-123",
            )

        self.assertEqual(
            result,
            {
                "employee_id": 601,
                "account_id": 701,
                "login": "new.user",
                "company_name": "Acme",
                "requested_role": "employee",
            },
        )
        self.assertEqual(connection.commits, 1)
        normalized_sql = [
            " ".join(sql.split()).casefold()
            for sql, _ in connection.cursor_value.executed
        ]
        company_lock = next(
            index
            for index, sql in enumerate(normalized_sql)
            if "from companies" in sql and "for update" in sql
        )
        invitation_lock = next(
            index
            for index, sql in enumerate(normalized_sql)
            if "from company_invitations invitation" in sql and "for update" in sql
        )
        employee_insert = next(
            index for index, sql in enumerate(normalized_sql) if sql.startswith("insert into employees")
        )
        account_insert = next(
            index for index, sql in enumerate(normalized_sql) if sql.startswith("insert into accounts")
        )
        acceptance_update = next(
            index
            for index, sql in enumerate(normalized_sql)
            if sql.startswith("update company_invitations")
            and "accepted_employee_id" in sql
        )
        self.assertLess(company_lock, invitation_lock)
        self.assertLess(invitation_lock, employee_insert)
        self.assertLess(employee_insert, account_insert)
        self.assertLess(account_insert, acceptance_update)

        serialized_params = json.dumps(
            [params for _, params in connection.cursor_value.executed],
            default=str,
        )
        self.assertNotIn(VALID_TOKEN, serialized_params)
        self.assertNotIn(VALID_PASSWORD, serialized_params)
        self.assertNotIn("request-123", serialized_params)

    def test_same_idempotency_key_returns_committed_result_without_new_writes(self):
        previous = {
            "employee_id": 601,
            "account_id": 701,
            "login": "new.user",
            "company_name": "Acme",
            "requested_role": "employee",
        }
        connection = _Connection(
            self._success_responder(accepted=True, idempotent_response=previous)
        )
        with patch.object(
            invitation_service, "get_connection", return_value=connection
        ):
            result = invitation_service.accept_invitation(
                VALID_TOKEN,
                _account_data(),
                idempotency_key="request-123",
            )

        self.assertEqual(result, previous)
        writes = [
            " ".join(sql.split()).casefold()
            for sql, _ in connection.cursor_value.executed
            if sql.lstrip().casefold().startswith(("insert", "update", "delete"))
        ]
        self.assertEqual(writes, [])


if __name__ == "__main__":
    unittest.main()
