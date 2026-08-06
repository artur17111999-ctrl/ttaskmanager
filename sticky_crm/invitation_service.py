"""Secure service layer for accepting and managing company invitations.

The desktop client still connects directly to PostgreSQL.  Consequently this
module must not be treated as the final authentication boundary.  It does,
however, derive company and role data from locked database rows and keeps raw
tokens and passwords out of persistent metadata.
"""

from __future__ import annotations

import hashlib
import json
import re
import secrets
import unicodedata
from collections.abc import Mapping
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from typing import Any

import bcrypt

from access_context import AccessContext
from company_service import (
    CompanyServiceError,
    ConflictError,
    NotFoundError,
    PermissionDenied,
    SeatLimitError,
    ValidationError,
)
from db import get_connection


ROLE_EMPLOYEE = "employee"
ROLE_ADMIN = "company_admin"
ROLE_OWNER = "company_owner"
COMPANY_ACTIVE = "active"

INVALID_INVITATION_MESSAGE = "Invitation is invalid or no longer available"
DEFAULT_INVITATION_DAYS = 7
DEFAULT_IDEMPOTENCY_DAYS = 7
MAX_TOKEN_LENGTH = 256
MAX_PASSWORD_BYTES = 72  # bcrypt's effective input limit

_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{32,256}$")
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")
_ACCEPT_FIELDS = {
    "login",
    "password",
    "password_confirmation",
    "birth_date",
    "policy_version",
}
_FORBIDDEN_ACCEPT_FIELDS = {
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
}


class InvitationServiceError(CompanyServiceError):
    """Base invitation error that is safe to translate at the UI boundary."""


class InvalidInvitationError(InvitationServiceError):
    """Opaque error used for every unavailable public invitation state."""

    def __init__(self, *_private_details: Any):
        super().__init__(INVALID_INVITATION_MESSAGE)


class LoginConflictError(ConflictError):
    """The requested login cannot be used."""


class EmailConflictError(ConflictError):
    """The invited email already belongs to an employee."""


class IdempotencyConflictError(ConflictError):
    """An idempotency key was reused for a different request."""


@contextmanager
def _database(*, write: bool = False):
    connection = get_connection()
    if connection is None:
        raise InvitationServiceError("Database connection is unavailable")

    cursor = None
    try:
        cursor = connection.cursor()
        yield cursor
        if write:
            connection.commit()
    except CompanyServiceError:
        rollback = getattr(connection, "rollback", None)
        if rollback:
            rollback()
        raise
    except Exception as error:
        rollback = getattr(connection, "rollback", None)
        if rollback:
            rollback()
        pgcode = getattr(error, "pgcode", None)
        if pgcode == "23505":
            raise ConflictError("Account credentials or invitation state conflict") from error
        if pgcode == "23503":
            raise ConflictError("Invitation references unavailable data") from error
        raise InvitationServiceError("Invitation operation failed") from error
    finally:
        if cursor is not None:
            cursor.close()
        connection.close()


def _row_value(row, index: int, *keys: str, default=None):
    if row is None:
        return default
    if isinstance(row, Mapping):
        for key in keys:
            if key in row:
                return row[key]
        return default
    try:
        return row[index]
    except (IndexError, TypeError):
        return default


def _json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except (TypeError, ValueError):
            return {}
        return dict(decoded) if isinstance(decoded, Mapping) else {}
    return {}


def _utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _token_digest(token: Any) -> tuple[str, bool]:
    """Return a digest and validity flag without hashing unbounded input."""
    candidate = token.strip() if isinstance(token, str) else ""
    valid = bool(
        candidate
        and len(candidate) <= MAX_TOKEN_LENGTH
        and _TOKEN_RE.fullmatch(candidate)
    )
    material = candidate if valid else "invalid-invitation-token-probe"
    return hashlib.sha256(material.encode("utf-8")).hexdigest(), valid


def _normalize_login(value: Any) -> str:
    if not isinstance(value, str):
        raise ValidationError("Login is required")
    login = unicodedata.normalize("NFKC", value).strip()
    if not 3 <= len(login) <= 100:
        raise ValidationError("Login must contain 3-100 characters")
    if _CONTROL_RE.search(login):
        raise ValidationError("Login contains unsupported characters")
    return login


def _validate_password(value: Any) -> str:
    if not isinstance(value, str):
        raise ValidationError("Password is required")
    if len(value) < 12:
        raise ValidationError("Password must contain at least 12 characters")
    encoded = value.encode("utf-8")
    if len(encoded) > MAX_PASSWORD_BYTES:
        raise ValidationError("Password is too long for the current password scheme")
    if "\x00" in value:
        raise ValidationError("Password contains an unsupported character")
    return value


def _normalize_birth_date(value: Any) -> str:
    if value in (None, ""):
        raise ValidationError("birth_date is required")
    candidate = str(value).strip()
    try:
        parsed = date.fromisoformat(candidate)
    except ValueError as error:
        raise ValidationError("birth_date must use YYYY-MM-DD format") from error
    if parsed >= date.today():
        raise ValidationError("birth_date must be in the past")
    return parsed.isoformat()


def _normalize_account_data(account_data: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(account_data, Mapping):
        raise ValidationError("Account data must be a mapping")
    forbidden = _FORBIDDEN_ACCEPT_FIELDS.intersection(account_data)
    if forbidden:
        raise ValidationError(
            "Client-controlled invitation fields are forbidden: "
            + ", ".join(sorted(forbidden))
        )
    unknown = set(account_data).difference(_ACCEPT_FIELDS)
    if unknown:
        raise ValidationError("Unknown account fields: " + ", ".join(sorted(unknown)))

    login = _normalize_login(account_data.get("login"))
    password = _validate_password(account_data.get("password"))
    confirmation = account_data.get("password_confirmation")
    if confirmation is not None and confirmation != password:
        raise ValidationError("Password confirmation does not match")

    policy_version = str(account_data.get("policy_version") or "1").strip()
    if not policy_version or len(policy_version) > 50 or _CONTROL_RE.search(policy_version):
        raise ValidationError("Password policy version is invalid")
    return {
        "login": login,
        "password": password,
        "birth_date": _normalize_birth_date(account_data.get("birth_date")),
        "policy_version": policy_version,
    }


def _positive_id(value: Any, label: str) -> int:
    if isinstance(value, bool):
        raise ValidationError(f"{label} is invalid")
    try:
        normalized = int(value)
    except (TypeError, ValueError) as error:
        raise ValidationError(f"{label} is invalid") from error
    if normalized <= 0:
        raise ValidationError(f"{label} is invalid")
    return normalized


def _actor_employee_id(actor: AccessContext | Mapping[str, Any] | int) -> int:
    if isinstance(actor, AccessContext):
        value = actor.employee_id
    elif isinstance(actor, Mapping):
        value = actor.get("employee_id")
    else:
        value = actor
    return _positive_id(value, "Actor employee id")


def _load_actor(cursor, actor: AccessContext | Mapping[str, Any] | int) -> dict[str, Any]:
    actor_id = _actor_employee_id(actor)
    cursor.execute(
        """
        SELECT employee.id, employee.company_id,
               COALESCE(employee.role, 'employee'),
               COALESCE(employee.is_dismissed, FALSE),
               company.status, company.owner_employee_id
        FROM employees employee
        JOIN companies company ON company.id = employee.company_id
        WHERE employee.id = %s
        """,
        (actor_id,),
    )
    row = cursor.fetchone()
    if not row or bool(_row_value(row, 3, "is_dismissed", default=False)):
        raise PermissionDenied("The actor is inactive or does not exist")
    employee_id = int(_row_value(row, 0, "employee_id", "id"))
    company_id = int(_row_value(row, 1, "company_id"))
    company_status = _row_value(row, 4, "company_status", "status")
    if company_status != COMPANY_ACTIVE:
        raise PermissionDenied("The company is not active")
    owner_id = _row_value(row, 5, "owner_employee_id")
    role = ROLE_OWNER if owner_id == employee_id else str(
        _row_value(row, 2, "role", default=ROLE_EMPLOYEE) or ROLE_EMPLOYEE
    )
    if role not in {ROLE_OWNER, ROLE_ADMIN}:
        raise PermissionDenied("The actor cannot manage invitations")
    return {
        "employee_id": employee_id,
        "company_id": company_id,
        "role": role,
    }


def _lock_company(cursor, company_id: int) -> dict[str, Any]:
    cursor.execute(
        """
        SELECT id, name, employee_limit, status
        FROM companies
        WHERE id = %s
        FOR UPDATE
        """,
        (company_id,),
    )
    row = cursor.fetchone()
    if not row or _row_value(row, 3, "status") != COMPANY_ACTIVE:
        raise InvalidInvitationError()
    return {
        "id": int(_row_value(row, 0, "id", "company_id")),
        "name": _row_value(row, 1, "name", "company_name"),
        "employee_limit": int(_row_value(row, 2, "employee_limit", default=0)),
        "status": _row_value(row, 3, "status"),
    }


def _write_audit(
    cursor,
    *,
    company_id: int,
    action: str,
    entity_type: str,
    entity_id: Any,
    actor_employee_id: int | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> None:
    cursor.execute(
        """
        INSERT INTO audit_log (
            company_id, actor_employee_id, action, entity_type, entity_id, metadata
        ) VALUES (%s, %s, %s, %s, %s, %s::jsonb)
        """,
        (
            company_id,
            actor_employee_id,
            action,
            entity_type,
            str(entity_id) if entity_id is not None else None,
            json.dumps(dict(metadata or {}), default=str),
        ),
    )


def _request_digest(
    token_hash: str,
    normalized: Mapping[str, Any],
) -> str:
    # Password material is deliberately excluded from persistent idempotency data.
    payload = {
        "token_proof": hashlib.sha256(("accept:" + token_hash).encode("ascii")).hexdigest(),
        "login": normalized["login"].casefold(),
        "birth_date": normalized.get("birth_date"),
        "policy_version": normalized["policy_version"],
    }
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _idempotency_digest(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValidationError("Idempotency key is invalid")
    normalized = value.strip()
    if not normalized or len(normalized) > 200 or _CONTROL_RE.search(normalized):
        raise ValidationError("Idempotency key is invalid")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _load_idempotent_result(
    cursor,
    *,
    key_hash: str | None,
    invitation_id: int,
    request_hash: str,
) -> dict[str, Any] | None:
    if key_hash is None:
        return None
    cursor.execute(
        """
        SELECT invitation_id, request_hash, response_code, response_body
        FROM idempotency_requests
        WHERE operation = 'invitation.accept' AND key_hash = %s
        FOR UPDATE
        """,
        (key_hash,),
    )
    row = cursor.fetchone()
    if not row:
        return None
    stored_invitation_id = int(_row_value(row, 0, "invitation_id"))
    stored_request_hash = _row_value(row, 1, "request_hash")
    response_code = int(_row_value(row, 2, "response_code", default=0))
    if stored_invitation_id != invitation_id or stored_request_hash != request_hash:
        raise IdempotencyConflictError("Idempotency key was reused for another request")
    if response_code != 200:
        raise IdempotencyConflictError("The previous request did not complete successfully")
    response = _json_object(_row_value(row, 3, "response_body", default={}))
    if not response:
        raise IdempotencyConflictError("The previous request result is unavailable")
    return response


def _lock_invitation(cursor, invitation_id: int, company_id: int, token_hash: str):
    cursor.execute(
        """
        SELECT invitation.id, invitation.company_id,
               invitation.email_normalized, invitation.requested_role,
               invitation.profile_data, invitation.expires_at,
               invitation.accepted_at, invitation.revoked_at,
               invitation.superseded_by_id, invitation.invited_by
        FROM company_invitations invitation
        WHERE invitation.id = %s
          AND invitation.company_id = %s
          AND invitation.token_hash = %s
        FOR UPDATE
        """,
        (invitation_id, company_id, token_hash),
    )
    return cursor.fetchone()


def _invitation_is_available(row: Any, *, now: datetime | None = None) -> bool:
    if not row:
        return False
    now = now or _utcnow_naive()
    expires_at = _row_value(row, 5, "expires_at")
    if getattr(expires_at, "tzinfo", None) is not None:
        expires_at = expires_at.astimezone(timezone.utc).replace(tzinfo=None)
    return bool(
        expires_at
        and expires_at > now
        and _row_value(row, 6, "accepted_at") is None
        and _row_value(row, 7, "revoked_at") is None
        and _row_value(row, 8, "superseded_by_id") is None
        and _row_value(row, 3, "requested_role") in {ROLE_EMPLOYEE, ROLE_ADMIN}
    )


def _catalog_value_or_none(cursor, table: str, value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        item_id = int(value)
    except (TypeError, ValueError):
        return None
    if item_id <= 0:
        return None
    if table not in {"positions", "departments"}:
        raise ValueError("Unsupported catalog")
    cursor.execute(f"SELECT id FROM {table} WHERE id = %s", (item_id,))
    return item_id if cursor.fetchone() else None


def inspect_invitation(token: str) -> dict[str, Any]:
    """Inspect a token without disclosing internal tenant identifiers or state."""
    token_hash, syntactically_valid = _token_digest(token)
    with _database() as cursor:
        cursor.execute(
            """
            SELECT invitation.email_normalized, invitation.requested_role,
                   invitation.profile_data, invitation.expires_at, company.name,
                   position.title, department.title
            FROM company_invitations invitation
            JOIN companies company ON company.id = invitation.company_id
            LEFT JOIN positions position
                   ON position.id = CASE
                       WHEN invitation.profile_data ->> 'position_id' ~ '^[0-9]+$'
                       THEN (invitation.profile_data ->> 'position_id')::INTEGER
                   END
            LEFT JOIN departments department
                   ON department.id = CASE
                       WHEN invitation.profile_data ->> 'department_id' ~ '^[0-9]+$'
                       THEN (invitation.profile_data ->> 'department_id')::INTEGER
                   END
            WHERE invitation.token_hash = %s
              AND invitation.accepted_at IS NULL
              AND invitation.revoked_at IS NULL
              AND invitation.superseded_by_id IS NULL
              AND invitation.expires_at > CURRENT_TIMESTAMP
              AND company.status = 'active'
            """,
            (token_hash,),
        )
        row = cursor.fetchone()
        if not syntactically_valid or not row:
            raise InvalidInvitationError()
        requested_role = _row_value(row, 1, "requested_role")
        if requested_role not in {ROLE_EMPLOYEE, ROLE_ADMIN}:
            raise InvalidInvitationError()
        stored_profile = _json_object(_row_value(row, 2, "profile_data", default={}))
        profile = {
            key: stored_profile[key]
            for key in ("last_name", "first_name", "middle_name", "start_date")
            if stored_profile.get(key) not in (None, "")
        }
        profile["position"] = _row_value(
            row, 5, "position", "position_title", default=None
        )
        profile["department"] = _row_value(
            row, 6, "department", "department_title", default=None
        )
        return {
            "preview_id": secrets.token_urlsafe(18),
            "company_name": _row_value(row, 4, "company_name", "name"),
            "email": _row_value(row, 0, "email", "email_normalized"),
            "profile_data": profile,
            "requested_role": requested_role,
            "expires_at": _row_value(row, 3, "expires_at"),
        }


def accept_invitation(
    token: str,
    account_data: Mapping[str, Any],
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    """Atomically turn one valid invitation reservation into an active account."""
    normalized = _normalize_account_data(account_data)
    token_hash, syntactically_valid = _token_digest(token)
    key_hash = _idempotency_digest(idempotency_key)
    request_hash = _request_digest(token_hash, normalized)
    acceptance_request_id = secrets.token_urlsafe(24)

    with _database(write=True) as cursor:
        # This untrusted lookup only establishes the lock target. No data from it
        # is returned before the locked invitation is re-read and revalidated.
        cursor.execute(
            """
            SELECT id, company_id
            FROM company_invitations
            WHERE token_hash = %s
            """,
            (token_hash,),
        )
        locator = cursor.fetchone()
        if not syntactically_valid or not locator:
            raise InvalidInvitationError()
        invitation_id = int(_row_value(locator, 0, "id", "invitation_id"))
        company_id = int(_row_value(locator, 1, "company_id"))

        company = _lock_company(cursor, company_id)
        invitation = _lock_invitation(cursor, invitation_id, company_id, token_hash)
        if invitation is None:
            raise InvalidInvitationError()

        previous = _load_idempotent_result(
            cursor,
            key_hash=key_hash,
            invitation_id=invitation_id,
            request_hash=request_hash,
        )
        if previous is not None:
            return previous
        if not _invitation_is_available(invitation):
            raise InvalidInvitationError()

        requested_role = _row_value(invitation, 3, "requested_role")
        email = str(_row_value(invitation, 2, "email_normalized"))
        profile = _json_object(_row_value(invitation, 4, "profile_data", default={}))
        invited_by = _row_value(invitation, 9, "invited_by")
        last_name = str(profile.get("last_name") or "").strip()
        first_name = str(profile.get("first_name") or "").strip()
        middle_name = str(profile.get("middle_name") or "").strip() or None
        if not last_name or not first_name:
            raise InvalidInvitationError()

        cursor.execute(
            """
            SELECT COUNT(*)
            FROM employees
            WHERE company_id = %s
              AND COALESCE(is_dismissed, FALSE) = FALSE
              AND COALESCE(role, 'employee') <> 'system_admin'
            """,
            (company_id,),
        )
        active_count = int(_row_value(cursor.fetchone(), 0, "count", "active_count", default=0))
        cursor.execute(
            """
            SELECT COUNT(*)
            FROM company_invitations
            WHERE company_id = %s
              AND accepted_at IS NULL
              AND revoked_at IS NULL
              AND superseded_by_id IS NULL
              AND expires_at > CURRENT_TIMESTAMP
            """,
            (company_id,),
        )
        reserved_count = int(
            _row_value(cursor.fetchone(), 0, "count", "reserved_count", default=0)
        )
        if active_count + reserved_count > company["employee_limit"]:
            raise SeatLimitError("The company employee limit has been reached")

        cursor.execute(
            "SELECT 1 FROM employees WHERE LOWER(BTRIM(email)) = %s LIMIT 1",
            (email.casefold(),),
        )
        if cursor.fetchone():
            raise EmailConflictError("Account credentials are already in use")
        cursor.execute(
            "SELECT 1 FROM accounts WHERE LOWER(BTRIM(login)) = %s LIMIT 1",
            (normalized["login"].casefold(),),
        )
        if cursor.fetchone():
            raise LoginConflictError("Account credentials are already in use")

        position_id = _catalog_value_or_none(cursor, "positions", profile.get("position_id"))
        department_id = _catalog_value_or_none(
            cursor, "departments", profile.get("department_id")
        )
        if position_id is None or department_id is None:
            raise InvalidInvitationError()
        start_date = profile.get("start_date") or _utcnow_naive().date().isoformat()
        try:
            start_date = date.fromisoformat(str(start_date)).isoformat()
        except ValueError:
            raise InvalidInvitationError()

        password_hash = bcrypt.hashpw(
            normalized["password"].encode("utf-8"),
            bcrypt.gensalt(rounds=12),
        ).decode("utf-8")

        cursor.execute(
            """
            INSERT INTO employees (
                last_name, first_name, middle_name, birth_date, start_date,
                position_id, department_id, email, company_id, role, is_dismissed
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, FALSE)
            RETURNING id
            """,
            (
                last_name,
                first_name,
                middle_name,
                normalized["birth_date"],
                start_date,
                position_id,
                department_id,
                email,
                company_id,
                requested_role,
            ),
        )
        employee_id = int(_row_value(cursor.fetchone(), 0, "id", "employee_id"))

        cursor.execute(
            """
            INSERT INTO accounts (
                login, password_hash, employee_id, status,
                password_changed_at, session_generation, updated_at
            ) VALUES (%s, %s, %s, 'active', CURRENT_TIMESTAMP, 0, CURRENT_TIMESTAMP)
            RETURNING id
            """,
            (normalized["login"], password_hash, employee_id),
        )
        account_id = int(_row_value(cursor.fetchone(), 0, "id", "account_id"))

        cursor.execute(
            """
            INSERT INTO company_membership_history (
                company_id, employee_id, role, membership_status,
                source_invitation_id, changed_by, reason, metadata
            ) VALUES (%s, %s, %s, 'active', %s, %s,
                      'accepted_invitation', %s::jsonb)
            """,
            (
                company_id,
                employee_id,
                requested_role,
                invitation_id,
                invited_by,
                json.dumps({"policy_version": normalized["policy_version"]}),
            ),
        )

        cursor.execute(
            """
            UPDATE company_invitations
            SET accepted_at = CURRENT_TIMESTAMP,
                accepted_employee_id = %s,
                accepted_account_id = %s,
                acceptance_request_id = %s
            WHERE id = %s AND company_id = %s
              AND accepted_at IS NULL AND revoked_at IS NULL
              AND superseded_by_id IS NULL
            RETURNING accepted_at
            """,
            (
                employee_id,
                account_id,
                acceptance_request_id,
                invitation_id,
                company_id,
            ),
        )
        accepted_row = cursor.fetchone()
        if not accepted_row:
            raise InvalidInvitationError()

        result = {
            "employee_id": employee_id,
            "account_id": account_id,
            "login": normalized["login"],
            "company_name": company["name"],
            "requested_role": requested_role,
        }
        _write_audit(
            cursor,
            company_id=company_id,
            action="employee.created_from_invitation",
            entity_type="employee",
            entity_id=employee_id,
            metadata={"invitation_id": invitation_id, "requested_role": requested_role},
        )
        _write_audit(
            cursor,
            company_id=company_id,
            action="account.created_from_invitation",
            entity_type="account",
            entity_id=account_id,
            metadata={"invitation_id": invitation_id},
        )
        _write_audit(
            cursor,
            company_id=company_id,
            action="invitation.accepted",
            entity_type="company_invitation",
            entity_id=invitation_id,
            metadata={"accepted_employee_id": employee_id},
        )

        if key_hash is not None:
            cursor.execute(
                """
                INSERT INTO idempotency_requests (
                    operation, key_hash, invitation_id, request_hash,
                    response_code, response_body, expires_at
                ) VALUES ('invitation.accept', %s, %s, %s, 200, %s::jsonb, %s)
                """,
                (
                    key_hash,
                    invitation_id,
                    request_hash,
                    json.dumps(result, default=str),
                    _utcnow_naive() + timedelta(days=DEFAULT_IDEMPOTENCY_DAYS),
                ),
            )
        return result


def _lock_admin_invitation(cursor, actor_state: Mapping[str, Any], invitation_id: int):
    company = _lock_company(cursor, int(actor_state["company_id"]))
    cursor.execute(
        """
        SELECT id, company_id, email_normalized, requested_role, profile_data,
               expires_at, accepted_at, revoked_at, superseded_by_id, invited_by,
               created_at
        FROM company_invitations
        WHERE id = %s AND company_id = %s
        FOR UPDATE
        """,
        (invitation_id, actor_state["company_id"]),
    )
    row = cursor.fetchone()
    if not row:
        raise NotFoundError("Invitation not found")
    invited_by = _row_value(row, 9, "invited_by")
    if actor_state["role"] == ROLE_ADMIN and invited_by != actor_state["employee_id"]:
        raise PermissionDenied("An administrator can manage only their own invitations")
    return company, row


def revoke_invitation(
    actor: AccessContext | Mapping[str, Any] | int,
    invitation_id: int,
) -> dict[str, Any]:
    """Revoke a same-company invitation; repeated revocation is idempotent."""
    invitation_id = _positive_id(invitation_id, "Invitation id")
    with _database(write=True) as cursor:
        actor_state = _load_actor(cursor, actor)
        _, row = _lock_admin_invitation(cursor, actor_state, invitation_id)
        if _row_value(row, 6, "accepted_at") is not None:
            raise ConflictError("Accepted invitations cannot be revoked")
        if _row_value(row, 8, "superseded_by_id") is not None:
            raise ConflictError("Superseded invitations cannot be revoked")
        revoked_at = _row_value(row, 7, "revoked_at")
        if revoked_at is None:
            cursor.execute(
                """
                UPDATE company_invitations
                SET revoked_at = CURRENT_TIMESTAMP
                WHERE id = %s AND company_id = %s AND accepted_at IS NULL
                RETURNING revoked_at
                """,
                (invitation_id, actor_state["company_id"]),
            )
            revoked_at = _row_value(cursor.fetchone(), 0, "revoked_at")
            _write_audit(
                cursor,
                company_id=actor_state["company_id"],
                actor_employee_id=actor_state["employee_id"],
                action="invitation.revoked",
                entity_type="company_invitation",
                entity_id=invitation_id,
            )
        return {"id": invitation_id, "status": "revoked", "revoked_at": revoked_at}


def resend_invitation(
    actor: AccessContext | Mapping[str, Any] | int,
    invitation_id: int,
) -> dict[str, Any]:
    """Supersede an unaccepted invitation and return its replacement token once."""
    invitation_id = _positive_id(invitation_id, "Invitation id")
    delivery_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(delivery_token.encode("utf-8")).hexdigest()
    expires_at = _utcnow_naive() + timedelta(days=DEFAULT_INVITATION_DAYS)

    with _database(write=True) as cursor:
        actor_state = _load_actor(cursor, actor)
        company, row = _lock_admin_invitation(cursor, actor_state, invitation_id)
        if _row_value(row, 6, "accepted_at") is not None:
            raise ConflictError("Accepted invitations cannot be resent")
        if _row_value(row, 8, "superseded_by_id") is not None:
            raise ConflictError("Invitation was already superseded")
        requested_role = _row_value(row, 3, "requested_role")
        if requested_role == ROLE_ADMIN and actor_state["role"] != ROLE_OWNER:
            raise PermissionDenied("Only the company owner can resend an admin invitation")
        email = _row_value(row, 2, "email_normalized")
        profile = _json_object(_row_value(row, 4, "profile_data", default={}))

        cursor.execute(
            """
            SELECT COUNT(*)
            FROM employees
            WHERE company_id = %s
              AND COALESCE(is_dismissed, FALSE) = FALSE
              AND COALESCE(role, 'employee') <> 'system_admin'
            """,
            (actor_state["company_id"],),
        )
        active_count = int(_row_value(cursor.fetchone(), 0, "count", default=0))
        cursor.execute(
            """
            SELECT COUNT(*)
            FROM company_invitations
            WHERE company_id = %s
              AND id <> %s
              AND accepted_at IS NULL AND revoked_at IS NULL
              AND superseded_by_id IS NULL
              AND expires_at > CURRENT_TIMESTAMP
            """,
            (actor_state["company_id"], invitation_id),
        )
        other_reserved_count = int(
            _row_value(cursor.fetchone(), 0, "count", default=0)
        )
        if active_count + other_reserved_count + 1 > company["employee_limit"]:
            raise SeatLimitError("The company employee limit has been reached")

        cursor.execute(
            """
            UPDATE company_invitations
            SET revoked_at = COALESCE(revoked_at, CURRENT_TIMESTAMP)
            WHERE id = %s AND company_id = %s AND accepted_at IS NULL
            """,
            (invitation_id, actor_state["company_id"]),
        )
        cursor.execute(
            """
            INSERT INTO company_invitations (
                company_id, email_normalized, requested_role, token_hash,
                invited_by, profile_data, expires_at, last_sent_at, delivery_status
            ) VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s,
                      CURRENT_TIMESTAMP, 'manual')
            RETURNING id, created_at
            """,
            (
                actor_state["company_id"],
                email,
                requested_role,
                token_hash,
                actor_state["employee_id"],
                json.dumps(profile, default=str),
                expires_at,
            ),
        )
        created = cursor.fetchone()
        new_invitation_id = int(_row_value(created, 0, "id", "invitation_id"))
        created_at = _row_value(created, 1, "created_at")
        cursor.execute(
            """
            UPDATE company_invitations
            SET superseded_by_id = %s
            WHERE id = %s AND company_id = %s
            """,
            (new_invitation_id, invitation_id, actor_state["company_id"]),
        )
        _write_audit(
            cursor,
            company_id=actor_state["company_id"],
            actor_employee_id=actor_state["employee_id"],
            action="invitation.resent",
            entity_type="company_invitation",
            entity_id=new_invitation_id,
            metadata={"supersedes_id": invitation_id},
        )
        return {
            "id": new_invitation_id,
            "supersedes_id": invitation_id,
            "email": email,
            "requested_role": requested_role,
            "profile_data": profile,
            "expires_at": expires_at,
            "created_at": created_at,
            "delivery_token": delivery_token,
        }


def cleanup_expired_invitations(batch_size: int = 100) -> int:
    """Revoke expired rows in deterministic company-before-invitation lock order."""
    if isinstance(batch_size, bool):
        raise ValidationError("batch_size is invalid")
    try:
        batch_size = int(batch_size)
    except (TypeError, ValueError) as error:
        raise ValidationError("batch_size is invalid") from error
    if not 1 <= batch_size <= 1000:
        raise ValidationError("batch_size must be between 1 and 1000")

    expired_count = 0
    with _database(write=True) as cursor:
        cursor.execute(
            """
            SELECT DISTINCT company_id
            FROM company_invitations
            WHERE accepted_at IS NULL AND revoked_at IS NULL
              AND superseded_by_id IS NULL
              AND expires_at <= CURRENT_TIMESTAMP
            ORDER BY company_id
            LIMIT %s
            """,
            (batch_size,),
        )
        company_rows = cursor.fetchall()
        company_ids = [int(_row_value(row, 0, "company_id")) for row in company_rows]
        for company_id in company_ids:
            remaining = batch_size - expired_count
            if remaining <= 0:
                break
            cursor.execute(
                "SELECT id FROM companies WHERE id = %s FOR UPDATE",
                (company_id,),
            )
            if not cursor.fetchone():
                continue
            cursor.execute(
                """
                SELECT id
                FROM company_invitations
                WHERE company_id = %s
                  AND accepted_at IS NULL AND revoked_at IS NULL
                  AND superseded_by_id IS NULL
                  AND expires_at <= CURRENT_TIMESTAMP
                ORDER BY id
                FOR UPDATE SKIP LOCKED
                LIMIT %s
                """,
                (company_id, remaining),
            )
            invitation_ids = [
                int(_row_value(row, 0, "id", "invitation_id"))
                for row in cursor.fetchall()
            ]
            if not invitation_ids:
                continue
            cursor.execute(
                """
                UPDATE company_invitations
                SET revoked_at = CURRENT_TIMESTAMP
                WHERE company_id = %s AND id = ANY(%s)
                  AND accepted_at IS NULL AND revoked_at IS NULL
                """,
                (company_id, invitation_ids),
            )
            changed = int(cursor.rowcount)
            expired_count += changed
            cursor.execute(
                """
                INSERT INTO audit_log (
                    company_id, actor_employee_id, action, entity_type, entity_id, metadata
                )
                SELECT company_id, NULL, 'invitation.expired',
                       'company_invitation', id::TEXT, '{}'::jsonb
                FROM company_invitations
                WHERE company_id = %s AND id = ANY(%s)
                """,
                (company_id, invitation_ids),
            )
    return expired_count


__all__ = [
    "InvitationServiceError",
    "InvalidInvitationError",
    "LoginConflictError",
    "EmailConflictError",
    "IdempotencyConflictError",
    "inspect_invitation",
    "accept_invitation",
    "revoke_invitation",
    "resend_invitation",
    "cleanup_expired_invitations",
]
