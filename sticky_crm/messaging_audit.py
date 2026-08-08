"""Read-only preflight audit for the legacy messaging schema.

The audit deliberately returns only finding categories, aggregate counts, and a
bounded sample of entity identifiers. It never selects message bodies, attachment
bytes, passwords, tokens, or other user-provided content.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Mapping


DEFAULT_SAMPLE_LIMIT = 25
MAX_SAMPLE_LIMIT = 100

_CATEGORY_RE = re.compile(r"^[A-Za-z0-9._-]{1,160}$")
_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9:_-]{1,128}$")

_REQUIRED_SCHEMA = {
    "employees": {"id", "company_id"},
    "chats": {"id", "company_id", "is_group", "is_self"},
    "chat_members": {"chat_id", "employee_id"},
    "messages": {"id", "chat_id", "sender_id", "is_read"},
    "notifications": {"id", "user_id", "chat_id", "message_id"},
}

_OPTIONAL_SCHEMA = {
    "image_attachments": {"id", "owner_type", "owner_id"},
    "pinned_chats": {"user_id", "chat_id"},
    "drafts": {"user_id", "chat_id"},
}

_AUDITED_TABLES = tuple(sorted({*_REQUIRED_SCHEMA, *_OPTIONAL_SCHEMA}))


@dataclass(frozen=True)
class AuditFinding:
    """A content-free result of one audit check."""

    category: str
    count: int
    ids: tuple[int | str, ...] = ()
    blocking: bool = True

    def __post_init__(self) -> None:
        if not self.category or not _CATEGORY_RE.fullmatch(self.category):
            raise ValueError("Audit category is invalid")
        if isinstance(self.count, bool) or self.count < 0:
            raise ValueError("Audit count is invalid")
        for entity_id in self.ids:
            _safe_identifier(entity_id)

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "count": self.count,
            "ids": list(self.ids),
            "blocking": self.blocking,
        }


@dataclass(frozen=True)
class MessagingAuditReport:
    """Complete, safe-to-print result of the messaging preflight audit."""

    findings: tuple[AuditFinding, ...]

    @property
    def ok(self) -> bool:
        return not any(item.blocking and item.count > 0 for item in self.findings)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "findings": [item.to_dict() for item in self.findings],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True)


class _AuditQueryFailed(RuntimeError):
    def __init__(self, category: str):
        super().__init__(category)
        self.category = category


def _safe_identifier(value: Any) -> int | str:
    if isinstance(value, bool):
        raise ValueError("Boolean values are not entity identifiers")
    if isinstance(value, int):
        return value
    candidate = str(value)
    if not _IDENTIFIER_RE.fullmatch(candidate):
        raise ValueError("Entity identifier has an unsafe representation")
    return candidate


def _row_value(row: Any, index: int, key: str) -> Any:
    if isinstance(row, Mapping):
        return row.get(key)
    return row[index]


def _assert_read_only_sql(sql: str) -> None:
    normalized = sql.lstrip().upper()
    if not (normalized.startswith("SELECT ") or normalized.startswith("WITH ")):
        raise ValueError("Messaging audit attempted a non-read-only statement")


def _load_schema(cursor: Any) -> dict[str, set[str]]:
    sql = """
        SELECT table_name, column_name
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = ANY(%s)
        ORDER BY table_name, ordinal_position
        /* messaging_audit:schema_catalog */
    """
    _assert_read_only_sql(sql)
    try:
        cursor.execute(sql, (list(_AUDITED_TABLES),))
        rows = cursor.fetchall()
    except Exception as error:
        raise _AuditQueryFailed("schema_catalog") from error

    schema: dict[str, set[str]] = {}
    for row in rows:
        table_name = str(_row_value(row, 0, "table_name"))
        column_name = str(_row_value(row, 1, "column_name"))
        if table_name in _AUDITED_TABLES:
            schema.setdefault(table_name, set()).add(column_name)
    return schema


def _run_check(
    cursor: Any,
    *,
    category: str,
    sql: str,
    sample_limit: int,
    params: Iterable[Any] = (),
    blocking: bool = True,
) -> AuditFinding:
    _assert_read_only_sql(sql)
    query_params = (*tuple(params), sample_limit)
    try:
        cursor.execute(sql, query_params)
        rows = cursor.fetchall()
        if not rows:
            return AuditFinding(category=category, count=0, blocking=blocking)

        total = int(_row_value(rows[0], 1, "total_count"))
        if total < 0:
            raise ValueError("Negative audit count")
        identifiers = tuple(
            _safe_identifier(_row_value(row, 0, "entity_id")) for row in rows
        )
        return AuditFinding(
            category=category,
            count=total,
            ids=identifiers,
            blocking=blocking,
        )
    except _AuditQueryFailed:
        raise
    except Exception as error:
        raise _AuditQueryFailed(category) from error


def _has(schema: Mapping[str, set[str]], table: str, *columns: str) -> bool:
    available = schema.get(table)
    return available is not None and set(columns).issubset(available)


def _schema_findings(schema: Mapping[str, set[str]]) -> list[AuditFinding]:
    findings: list[AuditFinding] = []
    for table, required_columns in _REQUIRED_SCHEMA.items():
        if table not in schema:
            findings.append(AuditFinding(f"schema.missing_table.{table}", 1))
            continue
        for column in sorted(required_columns.difference(schema[table])):
            findings.append(
                AuditFinding(f"schema.missing_column.{table}.{column}", 1)
            )

    for table, required_columns in _OPTIONAL_SCHEMA.items():
        if table not in schema:
            continue
        for column in sorted(required_columns.difference(schema[table])):
            findings.append(
                AuditFinding(f"schema.missing_column.{table}.{column}", 1)
            )
    return findings


def _data_checks(
    cursor: Any,
    schema: Mapping[str, set[str]],
    sample_limit: int,
) -> list[AuditFinding]:
    findings: list[AuditFinding] = []

    def check(
        category: str,
        sql: str,
        *,
        requires: tuple[tuple[str, tuple[str, ...]], ...],
        params: Iterable[Any] = (),
        blocking: bool = True,
    ) -> None:
        if all(_has(schema, table, *columns) for table, columns in requires):
            findings.append(
                _run_check(
                    cursor,
                    category=category,
                    sql=sql,
                    sample_limit=sample_limit,
                    params=params,
                    blocking=blocking,
                )
            )

    check(
        "tenant.employee_without_company",
        """
        SELECT employee.id AS entity_id, COUNT(*) OVER() AS total_count
        FROM public.employees employee
        WHERE employee.company_id IS NULL
        ORDER BY employee.id
        LIMIT %s
        /* messaging_audit:tenant.employee_without_company */
        """,
        requires=(("employees", ("id", "company_id")),),
    )

    check(
        "tenant.chat_without_company",
        """
        SELECT chat.id AS entity_id, COUNT(*) OVER() AS total_count
        FROM public.chats chat
        WHERE chat.company_id IS NULL
        ORDER BY chat.id
        LIMIT %s
        /* messaging_audit:tenant.chat_without_company */
        """,
        requires=(("chats", ("id", "company_id")),),
    )

    check(
        "integrity.chat_member_without_chat",
        """
        SELECT member.chat_id AS entity_id, COUNT(*) OVER() AS total_count
        FROM public.chat_members member
        LEFT JOIN public.chats chat ON chat.id = member.chat_id
        WHERE chat.id IS NULL
        ORDER BY member.chat_id
        LIMIT %s
        /* messaging_audit:integrity.chat_member_without_chat */
        """,
        requires=(
            ("chat_members", ("chat_id",)),
            ("chats", ("id",)),
        ),
    )

    check(
        "integrity.chat_member_without_employee",
        """
        SELECT member.employee_id AS entity_id, COUNT(*) OVER() AS total_count
        FROM public.chat_members member
        LEFT JOIN public.employees employee ON employee.id = member.employee_id
        WHERE employee.id IS NULL
        ORDER BY member.employee_id
        LIMIT %s
        /* messaging_audit:integrity.chat_member_without_employee */
        """,
        requires=(
            ("chat_members", ("employee_id",)),
            ("employees", ("id",)),
        ),
    )

    check(
        "tenant.chat_member_without_company",
        """
        WITH affected_employees AS (
            SELECT DISTINCT member.employee_id AS entity_id
            FROM public.chat_members member
            JOIN public.employees employee ON employee.id = member.employee_id
            WHERE employee.company_id IS NULL
        )
        SELECT entity_id, COUNT(*) OVER() AS total_count
        FROM affected_employees
        ORDER BY entity_id
        LIMIT %s
        /* messaging_audit:tenant.chat_member_without_company */
        """,
        requires=(
            ("chat_members", ("employee_id",)),
            ("employees", ("id", "company_id")),
        ),
    )

    check(
        "tenant.cross_company_chat_member",
        """
        SELECT CONCAT(member.chat_id, ':', member.employee_id) AS entity_id,
               COUNT(*) OVER() AS total_count
        FROM public.chat_members member
        JOIN public.chats chat ON chat.id = member.chat_id
        JOIN public.employees employee ON employee.id = member.employee_id
        WHERE employee.company_id IS DISTINCT FROM chat.company_id
        ORDER BY member.chat_id, member.employee_id
        LIMIT %s
        /* messaging_audit:tenant.cross_company_chat_member */
        """,
        requires=(
            ("chat_members", ("chat_id", "employee_id")),
            ("chats", ("id", "company_id")),
            ("employees", ("id", "company_id")),
        ),
    )

    check(
        "integrity.duplicate_chat_member",
        """
        WITH duplicates AS (
            SELECT CONCAT(member.chat_id, ':', member.employee_id) AS entity_id
            FROM public.chat_members member
            GROUP BY member.chat_id, member.employee_id
            HAVING COUNT(*) > 1
        )
        SELECT entity_id, COUNT(*) OVER() AS total_count
        FROM duplicates
        ORDER BY entity_id
        LIMIT %s
        /* messaging_audit:integrity.duplicate_chat_member */
        """,
        requires=(("chat_members", ("chat_id", "employee_id")),),
    )

    check(
        "integrity.invalid_direct_member_count",
        """
        WITH invalid_chats AS (
            SELECT chat.id AS entity_id
            FROM public.chats chat
            LEFT JOIN public.chat_members member ON member.chat_id = chat.id
            WHERE chat.is_group = FALSE AND chat.is_self = FALSE
            GROUP BY chat.id
            HAVING COUNT(DISTINCT member.employee_id) <> 2
        )
        SELECT entity_id, COUNT(*) OVER() AS total_count
        FROM invalid_chats
        ORDER BY entity_id
        LIMIT %s
        /* messaging_audit:integrity.invalid_direct_member_count */
        """,
        requires=(
            ("chats", ("id", "is_group", "is_self")),
            ("chat_members", ("chat_id", "employee_id")),
        ),
    )

    check(
        "integrity.invalid_self_member_count",
        """
        WITH invalid_chats AS (
            SELECT chat.id AS entity_id
            FROM public.chats chat
            LEFT JOIN public.chat_members member ON member.chat_id = chat.id
            WHERE chat.is_self = TRUE
            GROUP BY chat.id
            HAVING COUNT(DISTINCT member.employee_id) <> 1
        )
        SELECT entity_id, COUNT(*) OVER() AS total_count
        FROM invalid_chats
        ORDER BY entity_id
        LIMIT %s
        /* messaging_audit:integrity.invalid_self_member_count */
        """,
        requires=(
            ("chats", ("id", "is_self")),
            ("chat_members", ("chat_id", "employee_id")),
        ),
    )

    check(
        "integrity.duplicate_direct_chat",
        """
        WITH direct_chats AS (
            SELECT chat.id AS chat_id,
                   ARRAY_AGG(DISTINCT member.employee_id ORDER BY member.employee_id) AS members
            FROM public.chats chat
            JOIN public.chat_members member ON member.chat_id = chat.id
            WHERE chat.is_group = FALSE AND chat.is_self = FALSE
            GROUP BY chat.id
            HAVING COUNT(DISTINCT member.employee_id) = 2
        ), duplicates AS (
            SELECT MIN(chat_id) AS entity_id
            FROM direct_chats
            GROUP BY members
            HAVING COUNT(*) > 1
        )
        SELECT entity_id, COUNT(*) OVER() AS total_count
        FROM duplicates
        ORDER BY entity_id
        LIMIT %s
        /* messaging_audit:integrity.duplicate_direct_chat */
        """,
        requires=(
            ("chats", ("id", "is_group", "is_self")),
            ("chat_members", ("chat_id", "employee_id")),
        ),
    )

    check(
        "integrity.duplicate_self_chat",
        """
        WITH duplicates AS (
            SELECT MIN(chat.id) AS entity_id
            FROM public.chats chat
            JOIN public.chat_members member ON member.chat_id = chat.id
            WHERE chat.is_self = TRUE
            GROUP BY member.employee_id
            HAVING COUNT(DISTINCT chat.id) > 1
        )
        SELECT entity_id, COUNT(*) OVER() AS total_count
        FROM duplicates
        ORDER BY entity_id
        LIMIT %s
        /* messaging_audit:integrity.duplicate_self_chat */
        """,
        requires=(
            ("chats", ("id", "is_self")),
            ("chat_members", ("chat_id", "employee_id")),
        ),
    )

    check(
        "integrity.message_without_chat",
        """
        SELECT message.id AS entity_id, COUNT(*) OVER() AS total_count
        FROM public.messages message
        LEFT JOIN public.chats chat ON chat.id = message.chat_id
        WHERE chat.id IS NULL
        ORDER BY message.id
        LIMIT %s
        /* messaging_audit:integrity.message_without_chat */
        """,
        requires=(
            ("messages", ("id", "chat_id")),
            ("chats", ("id",)),
        ),
    )

    check(
        "integrity.message_without_sender",
        """
        SELECT message.id AS entity_id, COUNT(*) OVER() AS total_count
        FROM public.messages message
        LEFT JOIN public.employees employee ON employee.id = message.sender_id
        WHERE employee.id IS NULL
        ORDER BY message.id
        LIMIT %s
        /* messaging_audit:integrity.message_without_sender */
        """,
        requires=(
            ("messages", ("id", "sender_id")),
            ("employees", ("id",)),
        ),
    )

    check(
        "authorization.sender_not_chat_member",
        """
        SELECT message.id AS entity_id, COUNT(*) OVER() AS total_count
        FROM public.messages message
        WHERE NOT EXISTS (
            SELECT 1
            FROM public.chat_members member
            WHERE member.chat_id = message.chat_id
              AND member.employee_id = message.sender_id
        )
        ORDER BY message.id
        LIMIT %s
        /* messaging_audit:authorization.sender_not_chat_member */
        """,
        requires=(
            ("messages", ("id", "chat_id", "sender_id")),
            ("chat_members", ("chat_id", "employee_id")),
        ),
    )

    check(
        "tenant.message_sender_cross_company",
        """
        SELECT message.id AS entity_id, COUNT(*) OVER() AS total_count
        FROM public.messages message
        JOIN public.chats chat ON chat.id = message.chat_id
        JOIN public.employees employee ON employee.id = message.sender_id
        WHERE employee.company_id IS DISTINCT FROM chat.company_id
        ORDER BY message.id
        LIMIT %s
        /* messaging_audit:tenant.message_sender_cross_company */
        """,
        requires=(
            ("messages", ("id", "chat_id", "sender_id")),
            ("chats", ("id", "company_id")),
            ("employees", ("id", "company_id")),
        ),
    )

    check(
        "read.null_legacy_is_read",
        """
        SELECT message.id AS entity_id, COUNT(*) OVER() AS total_count
        FROM public.messages message
        WHERE message.is_read IS NULL
        ORDER BY message.id
        LIMIT %s
        /* messaging_audit:read.null_legacy_is_read */
        """,
        requires=(("messages", ("id", "is_read")),),
    )

    check(
        "read.group_receipt_ambiguous",
        """
        SELECT message.id AS entity_id, COUNT(*) OVER() AS total_count
        FROM public.messages message
        JOIN public.chats chat ON chat.id = message.chat_id
        WHERE chat.is_group = TRUE
        ORDER BY message.id
        LIMIT %s
        /* messaging_audit:read.group_receipt_ambiguous */
        """,
        requires=(
            ("messages", ("id", "chat_id", "is_read")),
            ("chats", ("id", "is_group")),
        ),
    )

    check(
        "state.dismissed_chat_member",
        """
        WITH affected_employees AS (
            SELECT DISTINCT member.employee_id AS entity_id
            FROM public.chat_members member
            JOIN public.employees employee ON employee.id = member.employee_id
            WHERE employee.is_dismissed = TRUE
        )
        SELECT entity_id, COUNT(*) OVER() AS total_count
        FROM affected_employees
        ORDER BY entity_id
        LIMIT %s
        /* messaging_audit:state.dismissed_chat_member */
        """,
        requires=(
            ("chat_members", ("employee_id",)),
            ("employees", ("id", "is_dismissed")),
        ),
    )

    check(
        "integrity.notification_without_recipient",
        """
        SELECT notification.id AS entity_id, COUNT(*) OVER() AS total_count
        FROM public.notifications notification
        LEFT JOIN public.employees employee ON employee.id = notification.user_id
        WHERE employee.id IS NULL
        ORDER BY notification.id
        LIMIT %s
        /* messaging_audit:integrity.notification_without_recipient */
        """,
        requires=(
            ("notifications", ("id", "user_id")),
            ("employees", ("id",)),
        ),
    )

    check(
        "integrity.notification_without_chat",
        """
        SELECT notification.id AS entity_id, COUNT(*) OVER() AS total_count
        FROM public.notifications notification
        LEFT JOIN public.chats chat ON chat.id = notification.chat_id
        WHERE notification.chat_id IS NOT NULL AND chat.id IS NULL
        ORDER BY notification.id
        LIMIT %s
        /* messaging_audit:integrity.notification_without_chat */
        """,
        requires=(
            ("notifications", ("id", "chat_id")),
            ("chats", ("id",)),
        ),
    )

    check(
        "integrity.notification_without_message",
        """
        SELECT notification.id AS entity_id, COUNT(*) OVER() AS total_count
        FROM public.notifications notification
        LEFT JOIN public.messages message ON message.id = notification.message_id
        WHERE notification.message_id IS NOT NULL AND message.id IS NULL
        ORDER BY notification.id
        LIMIT %s
        /* messaging_audit:integrity.notification_without_message */
        """,
        requires=(
            ("notifications", ("id", "message_id")),
            ("messages", ("id",)),
        ),
    )

    check(
        "authorization.notification_recipient_not_member",
        """
        SELECT notification.id AS entity_id, COUNT(*) OVER() AS total_count
        FROM public.notifications notification
        WHERE notification.chat_id IS NOT NULL
          AND NOT EXISTS (
              SELECT 1
              FROM public.chat_members member
              WHERE member.chat_id = notification.chat_id
                AND member.employee_id = notification.user_id
          )
        ORDER BY notification.id
        LIMIT %s
        /* messaging_audit:authorization.notification_recipient_not_member */
        """,
        requires=(
            ("notifications", ("id", "user_id", "chat_id")),
            ("chat_members", ("chat_id", "employee_id")),
        ),
    )

    check(
        "tenant.notification_cross_company",
        """
        SELECT notification.id AS entity_id, COUNT(*) OVER() AS total_count
        FROM public.notifications notification
        JOIN public.employees employee ON employee.id = notification.user_id
        JOIN public.chats chat ON chat.id = notification.chat_id
        WHERE employee.company_id IS DISTINCT FROM chat.company_id
        ORDER BY notification.id
        LIMIT %s
        /* messaging_audit:tenant.notification_cross_company */
        """,
        requires=(
            ("notifications", ("id", "user_id", "chat_id")),
            ("employees", ("id", "company_id")),
            ("chats", ("id", "company_id")),
        ),
    )

    check(
        "authorization.pinned_chat_without_membership",
        """
        SELECT CONCAT(pin.user_id, ':', pin.chat_id) AS entity_id,
               COUNT(*) OVER() AS total_count
        FROM public.pinned_chats pin
        WHERE NOT EXISTS (
            SELECT 1 FROM public.chat_members member
            WHERE member.chat_id = pin.chat_id
              AND member.employee_id = pin.user_id
        )
        ORDER BY pin.user_id, pin.chat_id
        LIMIT %s
        /* messaging_audit:authorization.pinned_chat_without_membership */
        """,
        requires=(
            ("pinned_chats", ("user_id", "chat_id")),
            ("chat_members", ("chat_id", "employee_id")),
        ),
    )

    check(
        "integrity.duplicate_pinned_chat",
        """
        WITH duplicates AS (
            SELECT CONCAT(pin.user_id, ':', pin.chat_id) AS entity_id
            FROM public.pinned_chats pin
            GROUP BY pin.user_id, pin.chat_id
            HAVING COUNT(*) > 1
        )
        SELECT entity_id, COUNT(*) OVER() AS total_count
        FROM duplicates
        ORDER BY entity_id
        LIMIT %s
        /* messaging_audit:integrity.duplicate_pinned_chat */
        """,
        requires=(("pinned_chats", ("user_id", "chat_id")),),
    )

    check(
        "authorization.draft_without_membership",
        """
        SELECT CONCAT(draft.user_id, ':', draft.chat_id) AS entity_id,
               COUNT(*) OVER() AS total_count
        FROM public.drafts draft
        WHERE NOT EXISTS (
            SELECT 1 FROM public.chat_members member
            WHERE member.chat_id = draft.chat_id
              AND member.employee_id = draft.user_id
        )
        ORDER BY draft.user_id, draft.chat_id
        LIMIT %s
        /* messaging_audit:authorization.draft_without_membership */
        """,
        requires=(
            ("drafts", ("user_id", "chat_id")),
            ("chat_members", ("chat_id", "employee_id")),
        ),
    )

    check(
        "integrity.duplicate_draft",
        """
        WITH duplicates AS (
            SELECT CONCAT(draft.user_id, ':', draft.chat_id) AS entity_id
            FROM public.drafts draft
            GROUP BY draft.user_id, draft.chat_id
            HAVING COUNT(*) > 1
        )
        SELECT entity_id, COUNT(*) OVER() AS total_count
        FROM duplicates
        ORDER BY entity_id
        LIMIT %s
        /* messaging_audit:integrity.duplicate_draft */
        """,
        requires=(("drafts", ("user_id", "chat_id")),),
    )

    check(
        "integrity.orphan_message_attachment",
        """
        SELECT attachment.id AS entity_id, COUNT(*) OVER() AS total_count
        FROM public.image_attachments attachment
        LEFT JOIN public.messages message ON message.id = attachment.owner_id
        WHERE attachment.owner_type = %s AND message.id IS NULL
        ORDER BY attachment.id
        LIMIT %s
        /* messaging_audit:integrity.orphan_message_attachment */
        """,
        requires=(
            ("image_attachments", ("id", "owner_type", "owner_id")),
            ("messages", ("id",)),
        ),
        params=("message",),
    )

    check(
        "storage.legacy_message_attachment",
        """
        SELECT attachment.id AS entity_id, COUNT(*) OVER() AS total_count
        FROM public.image_attachments attachment
        WHERE attachment.owner_type = %s
        ORDER BY attachment.id
        LIMIT %s
        /* messaging_audit:storage.legacy_message_attachment */
        """,
        requires=(("image_attachments", ("id", "owner_type")),),
        params=("message",),
        blocking=False,
    )

    return findings


def audit_messaging(connection: Any, sample_limit: int = DEFAULT_SAMPLE_LIMIT) -> MessagingAuditReport:
    """Audit an open database connection without committing or changing data."""

    if isinstance(sample_limit, bool) or not 1 <= int(sample_limit) <= MAX_SAMPLE_LIMIT:
        raise ValueError(f"sample_limit must be between 1 and {MAX_SAMPLE_LIMIT}")
    sample_limit = int(sample_limit)

    findings: list[AuditFinding] = []
    cursor = None
    try:
        set_session = getattr(connection, "set_session", None)
        if set_session is not None:
            try:
                set_session(readonly=True, autocommit=False)
            except Exception:
                findings.append(AuditFinding("audit.readonly_session_failed", 1))
                return MessagingAuditReport(tuple(findings))

        cursor = connection.cursor()
        try:
            schema = _load_schema(cursor)
            findings.extend(_schema_findings(schema))
            findings.extend(_data_checks(cursor, schema, sample_limit))
        except _AuditQueryFailed as error:
            findings.append(
                AuditFinding(f"audit.query_failed.{error.category}", 1)
            )
    finally:
        if cursor is not None:
            try:
                cursor.close()
            except Exception:
                findings.append(AuditFinding("audit.cursor_close_failed", 1))
        rollback = getattr(connection, "rollback", None)
        if rollback is not None:
            try:
                rollback()
            except Exception:
                findings.append(AuditFinding("audit.rollback_failed", 1))

    return MessagingAuditReport(tuple(findings))


def run_audit(
    connection_factory: Callable[[], Any] | None = None,
    sample_limit: int = DEFAULT_SAMPLE_LIMIT,
) -> MessagingAuditReport:
    """Open a connection, run the read-only audit, and close it safely."""

    if connection_factory is None:
        try:
            from .db import get_connection
        except ImportError:  # Support direct execution from the sticky_crm directory.
            from db import get_connection

        connection_factory = get_connection

    try:
        connection = connection_factory()
    except Exception:
        return MessagingAuditReport((AuditFinding("audit.connection_failed", 1),))
    if connection is None:
        return MessagingAuditReport((AuditFinding("audit.connection_unavailable", 1),))

    try:
        return audit_messaging(connection, sample_limit=sample_limit)
    finally:
        try:
            connection.close()
        except Exception:
            # The report remains fail-closed at the query/transaction boundary. A
            # close failure contains no actionable data and must not expose a raw
            # driver exception through this content-free interface.
            pass


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run a read-only preflight audit of Sticky CRM messaging data."
    )
    parser.add_argument(
        "--sample-limit",
        type=int,
        default=DEFAULT_SAMPLE_LIMIT,
        help=f"Maximum identifiers per category (1-{MAX_SAMPLE_LIMIT}).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = run_audit(sample_limit=args.sample_limit)
    except ValueError:
        report = MessagingAuditReport((AuditFinding("audit.invalid_options", 1),))
    print(report.to_json())
    return 0 if report.ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
