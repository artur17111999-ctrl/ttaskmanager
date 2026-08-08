import inspect
import json
import re
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = PROJECT_ROOT / "sticky_crm"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

import messaging_audit
from messaging_audit import AuditFinding, MAX_SAMPLE_LIMIT, audit_messaging, run_audit


FULL_SCHEMA = {
    "employees": {"id", "company_id", "is_dismissed"},
    "chats": {"id", "company_id", "is_group", "is_self"},
    "chat_members": {"chat_id", "employee_id"},
    "messages": {"id", "chat_id", "sender_id", "is_read"},
    "notifications": {"id", "user_id", "chat_id", "message_id"},
    "image_attachments": {"id", "owner_type", "owner_id", "image_data"},
    "pinned_chats": {"user_id", "chat_id"},
    "drafts": {"user_id", "chat_id"},
}


class _AuditCursor:
    def __init__(self, schema=None, violations=None, fail_category=None):
        self.schema = schema or {}
        self.violations = violations or {}
        self.fail_category = fail_category
        self.executed = []
        self._rows = []
        self.closed = False

    def execute(self, sql, params=None):
        self.executed.append((sql, params))
        match = re.search(r"messaging_audit:([A-Za-z0-9._-]+)", sql)
        category = match.group(1) if match else None
        if category == self.fail_category:
            raise RuntimeError("SECRET message body and token must never escape")

        if category == "schema_catalog":
            self._rows = [
                (table, column)
                for table, columns in sorted(self.schema.items())
                for column in sorted(columns)
            ]
            return

        identifiers = list(self.violations.get(category, ()))
        sample_limit = params[-1]
        self._rows = [
            (entity_id, len(identifiers))
            for entity_id in identifiers[:sample_limit]
        ]

    def fetchall(self):
        return list(self._rows)

    def close(self):
        self.closed = True


class _AuditConnection:
    def __init__(self, cursor, readonly_error=None, rollback_error=None):
        self._cursor = cursor
        self.readonly_error = readonly_error
        self.rollback_error = rollback_error
        self.session_calls = []
        self.rollback_count = 0
        self.commit_count = 0
        self.closed = False

    def set_session(self, **kwargs):
        self.session_calls.append(kwargs)
        if self.readonly_error:
            raise self.readonly_error

    def cursor(self):
        return self._cursor

    def rollback(self):
        self.rollback_count += 1
        if self.rollback_error:
            raise self.rollback_error

    def commit(self):
        self.commit_count += 1

    def close(self):
        self.closed = True


def _finding(report, category):
    return next(item for item in report.findings if item.category == category)


class MessagingAuditTests(unittest.TestCase):
    def test_dotted_categories_are_valid_but_unsafe_categories_are_rejected(self):
        finding = AuditFinding("tenant.chat_without_company", 1, (7,))

        self.assertEqual(finding.category, "tenant.chat_without_company")
        with self.assertRaises(ValueError):
            AuditFinding("tenant.invalid category", 1)

    def test_clean_complete_schema_is_read_only_and_passes(self):
        cursor = _AuditCursor(schema=FULL_SCHEMA)
        connection = _AuditConnection(cursor)

        report = audit_messaging(connection)

        self.assertTrue(report.ok)
        self.assertEqual(connection.session_calls, [{"readonly": True, "autocommit": False}])
        self.assertEqual(connection.commit_count, 0)
        self.assertEqual(connection.rollback_count, 1)
        self.assertTrue(cursor.closed)
        for sql, params in cursor.executed:
            normalized = sql.lstrip().upper()
            self.assertTrue(normalized.startswith(("SELECT ", "WITH ")))
            self.assertIsNotNone(params)

    def test_counts_are_exact_and_identifier_samples_are_bounded(self):
        identifiers = list(range(1, 11))
        cursor = _AuditCursor(
            schema=FULL_SCHEMA,
            violations={"tenant.chat_without_company": identifiers},
        )
        connection = _AuditConnection(cursor)

        report = audit_messaging(connection, sample_limit=3)

        finding = _finding(report, "tenant.chat_without_company")
        self.assertEqual(finding.count, 10)
        self.assertEqual(finding.ids, (1, 2, 3))
        self.assertFalse(report.ok)

    def test_employee_without_company_blocks_tenant_rollout(self):
        cursor = _AuditCursor(
            schema=FULL_SCHEMA,
            violations={"tenant.employee_without_company": [17]},
        )
        connection = _AuditConnection(cursor)

        report = audit_messaging(connection)

        finding = _finding(report, "tenant.employee_without_company")
        self.assertEqual(finding.count, 1)
        self.assertEqual(finding.ids, (17,))
        self.assertFalse(report.ok)

    def test_every_legacy_group_receipt_is_treated_as_ambiguous(self):
        source = inspect.getsource(messaging_audit._data_checks)
        group_check = re.search(
            r'"read\.group_receipt_ambiguous"(?P<body>.*?)'
            r'/\* messaging_audit:read\.group_receipt_ambiguous \*/',
            source,
            flags=re.DOTALL,
        )

        self.assertIsNotNone(group_check)
        self.assertIn("WHERE chat.is_group = TRUE", group_check.group("body"))
        self.assertNotIn("message.is_read = TRUE", group_check.group("body"))

    def test_values_are_bound_as_sql_parameters(self):
        cursor = _AuditCursor(schema=FULL_SCHEMA)
        connection = _AuditConnection(cursor)

        audit_messaging(connection, sample_limit=7)

        for sql, params in cursor.executed:
            self.assertIsInstance(params, tuple)
            if "schema_catalog" in sql:
                self.assertEqual(len(params), 1)
                self.assertIsInstance(params[0], list)
            else:
                self.assertEqual(params[-1], 7)
        attachment_calls = [
            (sql, params)
            for sql, params in cursor.executed
            if "legacy_message_attachment" in sql or "orphan_message_attachment" in sql
        ]
        self.assertTrue(attachment_calls)
        self.assertTrue(all(params[0] == "message" for _, params in attachment_calls))

    def test_audit_is_pinned_to_public_schema(self):
        cursor = _AuditCursor(schema=FULL_SCHEMA)
        connection = _AuditConnection(cursor)

        audit_messaging(connection)

        schema_sql = cursor.executed[0][0]
        self.assertIn("table_schema = 'public'", schema_sql)
        for sql, _ in cursor.executed[1:]:
            for table in FULL_SCHEMA:
                with self.subTest(table=table):
                    self.assertNotRegex(
                        sql,
                        rf"\b(?:FROM|JOIN)\s+{re.escape(table)}\b",
                    )

    def test_incomplete_legacy_schema_fails_closed_without_query_errors(self):
        legacy_schema = {
            "chats": {"id", "is_group"},
            "messages": {"id", "chat_id", "sender_id", "is_read"},
        }
        cursor = _AuditCursor(schema=legacy_schema)
        connection = _AuditConnection(cursor)

        report = audit_messaging(connection)

        categories = {item.category for item in report.findings}
        self.assertFalse(report.ok)
        self.assertIn("schema.missing_table.employees", categories)
        self.assertIn("schema.missing_table.chat_members", categories)
        self.assertIn("schema.missing_table.notifications", categories)
        self.assertIn("schema.missing_column.chats.company_id", categories)
        self.assertIn("schema.missing_column.chats.is_self", categories)
        self.assertFalse(any(item.startswith("audit.query_failed") for item in categories))

    def test_query_failure_is_sanitized_and_blocks_rollout(self):
        cursor = _AuditCursor(
            schema=FULL_SCHEMA,
            fail_category="authorization.sender_not_chat_member",
        )
        connection = _AuditConnection(cursor)

        report = audit_messaging(connection)
        serialized = report.to_json()

        self.assertFalse(report.ok)
        self.assertIn(
            "audit.query_failed.authorization.sender_not_chat_member",
            {item.category for item in report.findings},
        )
        self.assertNotIn("SECRET", serialized)
        self.assertNotIn("token must never escape", serialized)

    def test_report_contains_no_content_fields_or_driver_details(self):
        cursor = _AuditCursor(
            schema=FULL_SCHEMA,
            violations={
                "integrity.message_without_chat": [101],
                "storage.legacy_message_attachment": [8, 9],
            },
        )
        connection = _AuditConnection(cursor)

        payload = json.loads(audit_messaging(connection).to_json())
        serialized = json.dumps(payload, ensure_ascii=False).casefold()

        self.assertEqual(set(payload), {"ok", "findings"})
        self.assertFalse(
            any(
                forbidden in serialized
                for forbidden in (
                    "message_text",
                    "password_hash",
                    "image_data",
                    "access_token",
                    "refresh_token",
                    "signed_url",
                    "secret body",
                )
            )
        )
        for finding in payload["findings"]:
            self.assertEqual(set(finding), {"category", "count", "ids", "blocking"})

    def test_readonly_session_failure_stops_before_queries(self):
        cursor = _AuditCursor(schema=FULL_SCHEMA)
        connection = _AuditConnection(cursor, readonly_error=RuntimeError("secret"))

        report = audit_messaging(connection)

        self.assertFalse(report.ok)
        self.assertEqual(report.findings[0].category, "audit.readonly_session_failed")
        self.assertEqual(cursor.executed, [])
        self.assertEqual(connection.commit_count, 0)

    def test_connection_failure_is_content_free_and_fail_closed(self):
        def failed_connection():
            raise RuntimeError("password=SECRET")

        report = run_audit(connection_factory=failed_connection)

        self.assertFalse(report.ok)
        self.assertEqual(report.findings[0].category, "audit.connection_failed")
        self.assertNotIn("SECRET", report.to_json())

    def test_run_audit_closes_connection(self):
        cursor = _AuditCursor(schema=FULL_SCHEMA)
        connection = _AuditConnection(cursor)

        report = run_audit(connection_factory=lambda: connection)

        self.assertTrue(report.ok)
        self.assertTrue(connection.closed)

    def test_invalid_sample_limit_is_rejected_before_sql(self):
        for value in (0, MAX_SAMPLE_LIMIT + 1, True):
            with self.subTest(value=value):
                cursor = _AuditCursor(schema=FULL_SCHEMA)
                connection = _AuditConnection(cursor)
                with self.assertRaises(ValueError):
                    audit_messaging(connection, sample_limit=value)
                self.assertEqual(cursor.executed, [])


if __name__ == "__main__":
    unittest.main()
