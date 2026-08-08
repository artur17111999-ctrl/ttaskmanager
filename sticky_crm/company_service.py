"""Actor-aware company management service.

The current desktop application connects directly to PostgreSQL, so an employee id
is not a complete security boundary yet.  This module still avoids trusting tenant
and role values supplied by UI code: every operation reloads them from the database
before authorizing or changing data.
"""

from __future__ import annotations

import hashlib
import json
import re
import secrets
from collections.abc import Mapping
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlsplit

from access_context import AccessContext
from db import get_connection


ROLE_EMPLOYEE = "employee"
ROLE_ADMIN = "company_admin"
ROLE_OWNER = "company_owner"
ROLE_SYSTEM_ADMIN = "system_admin"

COMPANY_ACTIVE = "active"
DEFAULT_EMPLOYEE_LIMIT = 15
DEFAULT_INVITATION_DAYS = 7
MAX_INVITATION_DAYS = 30

_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
_INN_RE = re.compile(r"^(?:\d{10}|\d{12})$")
_KPP_RE = re.compile(r"^\d{9}$")

_COMPANY_EDIT_FIELDS = {
    "name",
    "inn",
    "kpp",
    "legal_address",
    "actual_address",
    "contact_email",
    "website_url",
}
_COMPANY_REQUIRED_FIELDS = {"name", "inn"}
_CLIENT_OWNERSHIP_FIELDS = {
    "company_id",
    "owner_employee_id",
    "employee_limit",
    "plan_code",
    "status",
    "task_catalog_version",
}
_INVITATION_FIELDS = {
    "email",
    "requested_role",
    "role",
    "expires_in_days",
    "last_name",
    "first_name",
    "middle_name",
    "start_date",
    "position_id",
    "department_id",
}


class CompanyServiceError(RuntimeError):
    """Base error suitable for translating into a UI error message."""


class PermissionDenied(CompanyServiceError):
    """The current actor does not have the required permission."""


class ValidationError(CompanyServiceError):
    """Input data is invalid or contains a client-controlled tenant field."""


class SeatLimitError(CompanyServiceError):
    """The company's active and reserved seats reached its limit."""


class ConflictError(CompanyServiceError):
    """The write conflicts with current database state."""


class NotFoundError(CompanyServiceError):
    """The requested same-company object does not exist or is not visible."""


@contextmanager
def _database(*, write: bool = False):
    connection = get_connection()
    if connection is None:
        raise CompanyServiceError("Database connection is unavailable")

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
        if getattr(error, "pgcode", None) == "23505":
            raise ConflictError("The record already exists") from error
        if getattr(error, "pgcode", None) == "23503":
            raise ConflictError("The record is referenced by another object") from error
        raise CompanyServiceError(str(error)) from error
    finally:
        if cursor is not None:
            cursor.close()
        connection.close()


def _actor_employee_id(actor: AccessContext | Mapping[str, Any] | int) -> int:
    if isinstance(actor, bool):
        raise ValidationError("Actor employee id is invalid")
    if isinstance(actor, int):
        employee_id = actor
    elif isinstance(actor, AccessContext):
        employee_id = actor.employee_id
    elif isinstance(actor, Mapping):
        employee_id = actor.get("employee_id")
    else:
        raise ValidationError("Actor must be an AccessContext or employee id")

    try:
        employee_id = int(employee_id)
    except (TypeError, ValueError) as error:
        raise ValidationError("Actor employee id is invalid") from error
    if employee_id <= 0:
        raise ValidationError("Actor employee id is invalid")
    return employee_id


def _row_value(row, index: int, *keys: str, default=None):
    if row is None:
        return default
    if isinstance(row, Mapping):
        for key in keys:
            if key in row:
                return row[key]
        return default
    return row[index]


def _row_dict(row, columns: tuple[str, ...]) -> dict[str, Any]:
    if isinstance(row, Mapping):
        return dict(row)
    return dict(zip(columns, row))


def _positive_employee_id(value: Any) -> int:
    if isinstance(value, bool):
        raise ValidationError("Employee id is invalid")
    try:
        value = int(value)
    except (TypeError, ValueError) as error:
        raise ValidationError("Employee id is invalid") from error
    if value <= 0:
        raise ValidationError("Employee id is invalid")
    return value


def _load_actor(cursor, actor: AccessContext | Mapping[str, Any] | int, *, lock=False):
    actor_id = _actor_employee_id(actor)
    lock_clause = " FOR UPDATE OF employee" if lock else ""
    cursor.execute(
        f"""
        SELECT employee.id,
               employee.company_id,
               COALESCE(employee.role, 'employee'),
               COALESCE(employee.is_dismissed, FALSE),
               company.status,
               company.owner_employee_id
        FROM employees employee
        LEFT JOIN companies company ON company.id = employee.company_id
        WHERE employee.id = %s
        {lock_clause}
        """,
        (actor_id,),
    )
    row = cursor.fetchone()
    is_dismissed = bool(_row_value(row, 3, "is_dismissed", default=False)) if row else False
    if not row or is_dismissed:
        raise PermissionDenied("The actor is inactive or does not exist")

    employee_id = _row_value(row, 0, "employee_id", "id")
    company_id = _row_value(row, 1, "company_id")
    stored_role = _row_value(row, 2, "role", default=ROLE_EMPLOYEE)
    company_status = _row_value(row, 4, "company_status", "status")
    owner_employee_id = _row_value(row, 5, "owner_employee_id")
    role = ROLE_OWNER if owner_employee_id == employee_id else str(stored_role or ROLE_EMPLOYEE)
    actor_state = {
        "employee_id": employee_id,
        "company_id": company_id,
        "role": role,
        "company_status": company_status,
        "owner_employee_id": owner_employee_id,
    }
    if company_id is not None and company_status != COMPANY_ACTIVE:
        raise PermissionDenied("The company is not active")
    return actor_state


def _require_company(actor_state: Mapping[str, Any]) -> int:
    company_id = actor_state.get("company_id")
    if company_id is None:
        raise PermissionDenied("The actor is not assigned to a company")
    return int(company_id)


def _require_role(actor_state: Mapping[str, Any], *roles: str) -> None:
    if actor_state.get("role") not in roles:
        raise PermissionDenied("The actor does not have permission for this action")


def _clean_optional(value: Any, *, max_length: int | None = None) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    if not cleaned:
        return None
    if max_length is not None and len(cleaned) > max_length:
        raise ValidationError(f"Value exceeds {max_length} characters")
    return cleaned


def _normalize_email(value: Any, *, required: bool = False) -> str | None:
    email = _clean_optional(value, max_length=320)
    if email is None:
        if required:
            raise ValidationError("Email is required")
        return None
    email = email.casefold()
    if not _EMAIL_RE.fullmatch(email):
        raise ValidationError("Email has an invalid format")
    return email


def _normalize_company_data(data: Mapping[str, Any], *, partial: bool) -> dict[str, Any]:
    if not isinstance(data, Mapping):
        raise ValidationError("Company data must be a mapping")
    forbidden = _CLIENT_OWNERSHIP_FIELDS.intersection(data)
    if forbidden:
        raise ValidationError(
            "Client-controlled company fields are forbidden: " + ", ".join(sorted(forbidden))
        )
    unknown = set(data).difference(_COMPANY_EDIT_FIELDS)
    if unknown:
        raise ValidationError("Unknown company fields: " + ", ".join(sorted(unknown)))
    if not partial:
        missing = _COMPANY_REQUIRED_FIELDS.difference(data)
        if missing:
            raise ValidationError("Missing company fields: " + ", ".join(sorted(missing)))

    result: dict[str, Any] = {}
    if "name" in data:
        name = _clean_optional(data["name"], max_length=255)
        if name is None:
            raise ValidationError("Company name is required")
        result["name"] = name
    if "inn" in data:
        inn = _clean_optional(data["inn"], max_length=12)
        if inn is None or not _INN_RE.fullmatch(inn):
            raise ValidationError("INN must contain 10 or 12 digits")
        result["inn"] = inn
    if "kpp" in data:
        kpp = _clean_optional(data["kpp"], max_length=9)
        if kpp is not None and not _KPP_RE.fullmatch(kpp):
            raise ValidationError("KPP must contain 9 digits")
        result["kpp"] = kpp
    for field in ("legal_address", "actual_address"):
        if field in data:
            result[field] = _clean_optional(data[field])
    if "contact_email" in data:
        result["contact_email"] = _normalize_email(data["contact_email"])
    if "website_url" in data:
        website = _clean_optional(data["website_url"], max_length=500)
        if website is not None:
            parsed = urlsplit(website)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise ValidationError("Website URL must use http or https")
        result["website_url"] = website
    return result


def _normalize_invitation_profile(data: Mapping[str, Any]) -> dict[str, Any]:
    profile: dict[str, Any] = {}
    for field in ("last_name", "first_name", "middle_name"):
        if field in data:
            value = _clean_optional(data[field], max_length=255)
            if field in {"last_name", "first_name"} and data[field] is not None and value is None:
                raise ValidationError(f"{field} cannot be blank")
            profile[field] = value

    if "start_date" in data:
        raw_date = _clean_optional(data["start_date"], max_length=10)
        if raw_date is not None:
            try:
                raw_date = date.fromisoformat(raw_date).isoformat()
            except ValueError as error:
                raise ValidationError("start_date must use YYYY-MM-DD format") from error
        profile["start_date"] = raw_date

    for field in ("position_id", "department_id"):
        if field not in data:
            continue
        value = data[field]
        if value is None or value == "":
            profile[field] = None
            continue
        try:
            value = int(value)
        except (TypeError, ValueError) as error:
            raise ValidationError(f"{field} must be an integer") from error
        if value <= 0:
            raise ValidationError(f"{field} must be positive")
        profile[field] = value
    for field in ("last_name", "first_name"):
        if not profile.get(field):
            raise ValidationError(f"{field} is required for a new employee")
    return profile


_COMPANY_COLUMNS = (
    "id",
    "name",
    "inn",
    "kpp",
    "legal_address",
    "actual_address",
    "contact_email",
    "website_url",
    "status",
    "owner_employee_id",
    "employee_limit",
    "plan_code",
    "task_catalog_version",
    "created_at",
    "updated_at",
    "owner_name",
)


def _company_from_row(row) -> dict[str, Any]:
    company = _row_dict(row, _COMPANY_COLUMNS)
    version = company.get("row_version", company.get("updated_at"))
    company["row_version"] = version
    company.setdefault("updated_at", version)
    return company


def _select_company(cursor, actor_id: int, *, lock: bool = False):
    lock_clause = " FOR UPDATE OF company" if lock else ""
    cursor.execute(
        f"""
        SELECT company.id, company.name, company.inn, company.kpp,
               company.legal_address, company.actual_address,
               company.contact_email, company.website_url, company.status,
               company.owner_employee_id, company.employee_limit,
               company.plan_code, company.task_catalog_version,
               company.created_at, company.updated_at,
               CONCAT_WS(' ', owner.last_name, owner.first_name,
                         NULLIF(owner.middle_name, '')) AS owner_name
        FROM companies company
        LEFT JOIN employees owner ON owner.id = company.owner_employee_id
        WHERE company.id = (
            SELECT employee.company_id FROM employees employee WHERE employee.id = %s
        )
        {lock_clause}
        """,
        (actor_id,),
    )
    row = cursor.fetchone()
    return _company_from_row(row) if row else None


def _write_audit(
    cursor,
    actor_state: Mapping[str, Any],
    action: str,
    entity_type: str,
    entity_id: Any,
    *,
    old_values: Mapping[str, Any] | None = None,
    new_values: Mapping[str, Any] | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> None:
    cursor.execute(
        """
        INSERT INTO audit_log (
            company_id, actor_employee_id, action, entity_type, entity_id,
            old_values, new_values, metadata
        ) VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb)
        """,
        (
            actor_state.get("company_id"),
            actor_state["employee_id"],
            action,
            entity_type,
            str(entity_id) if entity_id is not None else None,
            json.dumps(old_values, default=str) if old_values is not None else None,
            json.dumps(new_values, default=str) if new_values is not None else None,
            json.dumps(metadata or {}, default=str),
        ),
    )


def _close_membership(cursor, company_id: int, employee_id: int, status: str) -> None:
    cursor.execute(
        """
        UPDATE company_membership_history
        SET membership_status = %s, ended_at = clock_timestamp()
        WHERE company_id = %s AND employee_id = %s AND ended_at IS NULL
        """,
        (status, company_id, employee_id),
    )


def _open_membership(
    cursor,
    company_id: int,
    employee_id: int,
    role: str,
    actor_id: int,
    reason: str,
) -> None:
    cursor.execute(
        """
        INSERT INTO company_membership_history (
            company_id, employee_id, role, membership_status, changed_by, reason
        ) VALUES (%s, %s, %s, 'active', %s, %s)
        """,
        (company_id, employee_id, role, actor_id, reason),
    )


def _lock_company_and_usage(
    cursor,
    company_id: int,
    *,
    revoke_expired: bool = False,
) -> dict[str, int]:
    cursor.execute(
        """
        SELECT employee_limit, status
        FROM companies
        WHERE id = %s
        FOR UPDATE
        """,
        (company_id,),
    )
    company_row = cursor.fetchone()
    company_status = _row_value(company_row, 1, "status") if company_row else None
    if not company_row or company_status != COMPANY_ACTIVE:
        raise PermissionDenied("The company is not active")

    if revoke_expired:
        cursor.execute(
            """
            UPDATE company_invitations
            SET revoked_at = CURRENT_TIMESTAMP
            WHERE company_id = %s
              AND accepted_at IS NULL
              AND revoked_at IS NULL
              AND expires_at <= CURRENT_TIMESTAMP
            """,
            (company_id,),
        )

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
    active_row = cursor.fetchone()
    active_count = int(_row_value(active_row, 0, "active_count", "count", default=0))
    cursor.execute(
        """
        SELECT COUNT(*)
        FROM company_invitations
        WHERE company_id = %s
          AND accepted_at IS NULL
          AND revoked_at IS NULL
          AND expires_at > CURRENT_TIMESTAMP
        """,
        (company_id,),
    )
    reserved_row = cursor.fetchone()
    reserved_count = int(
        _row_value(reserved_row, 0, "reserved_count", "count", default=0)
    )
    limit = int(_row_value(company_row, 0, "employee_limit", default=DEFAULT_EMPLOYEE_LIMIT))
    result = {
        "employee_limit": limit,
        "active_count": active_count,
        "reserved_count": reserved_count,
        "used_count": active_count + reserved_count,
        "available_count": max(0, limit - active_count - reserved_count),
    }
    # Compatibility aliases keep the service convenient for current and future UI.
    result.update(
        limit=result["employee_limit"],
        current_count=result["active_count"],
        free_count=result["available_count"],
    )
    return result


def get_company(actor: AccessContext | Mapping[str, Any] | int) -> dict[str, Any] | None:
    """Return the actor-owned company, or ``None`` during no-company onboarding."""
    with _database() as cursor:
        actor_state = _load_actor(cursor, actor)
        if actor_state["company_id"] is None:
            return None
        _require_role(actor_state, ROLE_OWNER)
        company = _select_company(cursor, actor_state["employee_id"])
        if company is None:
            raise NotFoundError("Company not found")
        return company


def create_company(
    actor: AccessContext | Mapping[str, Any] | int,
    company_data: Mapping[str, Any],
) -> dict[str, Any]:
    """Create a company and atomically make the no-company actor its owner."""
    values = _normalize_company_data(company_data, partial=False)
    actor_id = _actor_employee_id(actor)
    with _database(write=True) as cursor:
        actor_state = _load_actor(cursor, actor_id, lock=True)
        if actor_state["company_id"] is not None:
            raise ConflictError("The actor already belongs to a company")
        if actor_state["role"] == ROLE_SYSTEM_ADMIN:
            raise PermissionDenied("System administrators require a server-side target context")

        cursor.execute(
            """
            INSERT INTO companies (
                name, inn, kpp, legal_address, actual_address, contact_email,
                website_url, owner_employee_id, employee_limit, plan_code
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'default')
            RETURNING id, name, inn, kpp, legal_address, actual_address,
                      contact_email, website_url, status, owner_employee_id,
                      employee_limit, plan_code, task_catalog_version,
                      created_at, updated_at
            """,
            (
                values["name"],
                values["inn"],
                values.get("kpp"),
                values.get("legal_address"),
                values.get("actual_address"),
                values.get("contact_email"),
                values.get("website_url"),
                actor_id,
                DEFAULT_EMPLOYEE_LIMIT,
            ),
        )
        inserted_company = cursor.fetchone()
        company_id = int(_row_value(inserted_company, 0, "id", "company_id"))
        company = _company_from_row(inserted_company)
        company.setdefault("employee_limit", DEFAULT_EMPLOYEE_LIMIT)
        company.setdefault("plan_code", "default")
        cursor.execute(
            """
            UPDATE employees
            SET company_id = %s, role = 'company_owner', is_dismissed = FALSE
            WHERE id = %s AND company_id IS NULL
            """,
            (company_id, actor_id),
        )
        if cursor.rowcount != 1:
            raise ConflictError("The actor company assignment changed concurrently")

        # A self-chat may be created before the user creates their first company.
        # It is safe to attach only that user's orphaned self-chat to the new tenant.
        cursor.execute(
            """
            UPDATE chats AS chat
            SET company_id = %s
            WHERE chat.is_self = TRUE
              AND chat.company_id IS NULL
              AND EXISTS (
                  SELECT 1
                  FROM chat_members member
                  WHERE member.chat_id = chat.id
                    AND member.employee_id = %s
              )
            """,
            (company_id, actor_id),
        )

        created_actor = dict(actor_state)
        created_actor.update(company_id=company_id, role=ROLE_OWNER, owner_employee_id=actor_id)
        _open_membership(cursor, company_id, actor_id, ROLE_OWNER, actor_id, "company_created")
        _write_audit(
            cursor,
            created_actor,
            "company.created",
            "company",
            company_id,
            new_values={**values, "employee_limit": DEFAULT_EMPLOYEE_LIMIT, "plan_code": "default"},
        )
        return _select_company(cursor, actor_id) or company


def update_company(
    actor: AccessContext | Mapping[str, Any] | int,
    patch: Mapping[str, Any],
    row_version: Any = None,
) -> dict[str, Any]:
    """Update owner-managed company details with optimistic locking."""
    values = _normalize_company_data(patch, partial=True)
    if not values:
        return get_company(actor)

    with _database(write=True) as cursor:
        actor_state = _load_actor(cursor, actor)
        _require_company(actor_state)
        _require_role(actor_state, ROLE_OWNER)
        current = _select_company(cursor, actor_state["employee_id"], lock=True)
        if current is None:
            raise NotFoundError("Company not found")
        expected_version = current["updated_at"] if row_version is None else row_version

        assignments = [f"{field} = %s" for field in values]
        params = list(values.values())
        params.extend((actor_state["company_id"], expected_version))
        cursor.execute(
            f"""
            UPDATE companies
            SET {', '.join(assignments)}, updated_at = clock_timestamp()
            WHERE id = %s AND updated_at = %s
            """,
            tuple(params),
        )
        if cursor.rowcount != 1:
            raise ConflictError("Company details were changed by another session")
        _write_audit(
            cursor,
            actor_state,
            "company.updated",
            "company",
            actor_state["company_id"],
            old_values={field: current[field] for field in values},
            new_values=values,
        )
        updated = _select_company(cursor, actor_state["employee_id"])
        if updated is None:
            raise NotFoundError("Company not found")
        return updated


def get_company_usage(actor: AccessContext | Mapping[str, Any] | int) -> dict[str, int]:
    """Return active, reserved, available and total seat counts."""
    with _database() as cursor:
        actor_state = _load_actor(cursor, actor)
        company_id = _require_company(actor_state)
        _require_role(actor_state, ROLE_OWNER, ROLE_ADMIN)
        return _lock_company_and_usage(cursor, company_id)


def create_invitation(
    actor: AccessContext | Mapping[str, Any] | int,
    employee_data: Mapping[str, Any],
) -> dict[str, Any]:
    """Reserve one seat and return a one-time delivery token.

    Only ``token_hash`` is stored.  ``delivery_token`` is returned once so a caller
    can deliver it through a future mail transport; it cannot be recovered later.
    """
    if not isinstance(employee_data, Mapping):
        raise ValidationError("Employee invitation data must be a mapping")
    if "company_id" in employee_data:
        raise ValidationError("company_id cannot be supplied by the client")
    unknown = set(employee_data).difference(_INVITATION_FIELDS)
    if unknown:
        raise ValidationError("Unknown invitation fields: " + ", ".join(sorted(unknown)))
    email = _normalize_email(employee_data.get("email"), required=True)
    if (
        "role" in employee_data
        and "requested_role" in employee_data
        and employee_data["role"] != employee_data["requested_role"]
    ):
        raise ValidationError("role and requested_role cannot conflict")
    requested_role = str(
        employee_data.get("requested_role", employee_data.get("role", ROLE_EMPLOYEE))
    ).strip()
    if requested_role not in {ROLE_EMPLOYEE, ROLE_ADMIN}:
        raise ValidationError("Invitation role must be employee or company_admin")
    try:
        expires_in_days = int(employee_data.get("expires_in_days", DEFAULT_INVITATION_DAYS))
    except (TypeError, ValueError) as error:
        raise ValidationError("Invitation lifetime is invalid") from error
    if not 1 <= expires_in_days <= MAX_INVITATION_DAYS:
        raise ValidationError(f"Invitation lifetime must be 1-{MAX_INVITATION_DAYS} days")
    profile_data = _normalize_invitation_profile(employee_data)
    if profile_data.get("position_id") is None:
        raise ValidationError("position_id is required for a new employee")
    if profile_data.get("department_id") is None:
        raise ValidationError("department_id is required for a new employee")

    delivery_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(delivery_token.encode("utf-8")).hexdigest()
    expires_at = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=expires_in_days)

    with _database(write=True) as cursor:
        actor_state = _load_actor(cursor, actor)
        company_id = _require_company(actor_state)
        _require_role(actor_state, ROLE_OWNER, ROLE_ADMIN)
        if requested_role == ROLE_ADMIN and actor_state["role"] != ROLE_OWNER:
            raise PermissionDenied("Only the company owner can invite an administrator")

        cursor.execute(
            "SELECT 1 FROM positions WHERE id = %s",
            (profile_data["position_id"],),
        )
        if not cursor.fetchone():
            raise ValidationError("The selected position does not exist")
        cursor.execute(
            "SELECT 1 FROM departments WHERE id = %s",
            (profile_data["department_id"],),
        )
        if not cursor.fetchone():
            raise ValidationError("The selected department does not exist")

        usage = _lock_company_and_usage(cursor, company_id, revoke_expired=True)
        if usage["used_count"] >= usage["employee_limit"]:
            raise SeatLimitError("The company employee limit has been reached")

        cursor.execute(
            """
            SELECT 1 FROM employees WHERE LOWER(BTRIM(email)) = %s LIMIT 1
            """,
            (email,),
        )
        if cursor.fetchone():
            raise ConflictError("Invitation cannot be created for this email")
        cursor.execute(
            """
            SELECT 1
            FROM company_invitations
            WHERE company_id = %s AND email_normalized = %s
              AND accepted_at IS NULL AND revoked_at IS NULL
            """,
            (company_id, email),
        )
        if cursor.fetchone():
            raise ConflictError("Invitation cannot be created for this email")

        cursor.execute(
            """
            INSERT INTO company_invitations (
                company_id, email_normalized, requested_role, token_hash,
                invited_by, expires_at, profile_data
            ) VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb)
            RETURNING id, created_at, profile_data
            """,
            (
                company_id,
                email,
                requested_role,
                token_hash,
                actor_state["employee_id"],
                expires_at,
                json.dumps(profile_data, default=str),
            ),
        )
        invitation_row = cursor.fetchone()
        invitation_id = _row_value(invitation_row, 0, "id", "invitation_id")
        created_at = _row_value(invitation_row, 1, "created_at")
        _write_audit(
            cursor,
            actor_state,
            "employee.invited",
            "company_invitation",
            invitation_id,
            new_values={"email": email, "requested_role": requested_role, "expires_at": expires_at},
            metadata={"profile_data": profile_data},
        )
        return {
            "id": invitation_id,
            "company_id": company_id,
            "email": email,
            "requested_role": requested_role,
            "expires_at": expires_at,
            "created_at": created_at,
            "profile_data": profile_data,
            "delivery_token": delivery_token,
        }


_EMPLOYEE_COLUMNS = (
    "id",
    "full_name",
    "position",
    "department",
    "email",
    "role",
    "is_dismissed",
    "start_date",
)


def list_company_employees(
    actor: AccessContext | Mapping[str, Any] | int,
    filters: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """List employees from the actor's database-derived company only."""
    filters = filters or {}
    if not isinstance(filters, Mapping):
        raise ValidationError("Employee filters must be a mapping")
    if "company_id" in filters:
        raise ValidationError("company_id cannot be supplied by the client")
    unknown = set(filters).difference({"search", "role", "status"})
    if unknown:
        raise ValidationError("Unknown employee filters: " + ", ".join(sorted(unknown)))

    search = _clean_optional(filters.get("search"), max_length=255)
    role = _clean_optional(filters.get("role"), max_length=50)
    if role is not None and role not in {ROLE_EMPLOYEE, ROLE_ADMIN, ROLE_OWNER}:
        raise ValidationError("Unknown employee role filter")
    status = str(filters.get("status", "all")).strip().casefold()
    if status not in {"all", "active", "dismissed", "pending"}:
        raise ValidationError(
            "Employee status filter must be all, active, dismissed or pending"
        )

    with _database() as cursor:
        actor_state = _load_actor(cursor, actor)
        company_id = _require_company(actor_state)
        clauses = ["employee.company_id = %s"]
        params: list[Any] = [company_id]
        if search:
            clauses.append(
                "(employee.last_name ILIKE %s OR employee.first_name ILIKE %s "
                "OR COALESCE(employee.middle_name, '') ILIKE %s "
                "OR COALESCE(employee.email, '') ILIKE %s)"
            )
            params.extend([f"%{search}%"] * 4)
        if role:
            clauses.append("employee.role = %s")
            params.append(role)
        if status == "active":
            clauses.append("COALESCE(employee.is_dismissed, FALSE) = FALSE")
        elif status == "dismissed":
            clauses.append("COALESCE(employee.is_dismissed, FALSE) = TRUE")

        employees: list[dict[str, Any]] = []
        if status != "pending":
            cursor.execute(
                f"""
                SELECT employee.id,
                       CONCAT_WS(' ', employee.last_name, employee.first_name,
                                 NULLIF(employee.middle_name, '')),
                       position.title,
                       department.title,
                       employee.email,
                       CASE WHEN company.owner_employee_id = employee.id
                            THEN 'company_owner'
                            ELSE COALESCE(employee.role, 'employee') END,
                       COALESCE(employee.is_dismissed, FALSE),
                       employee.start_date
                FROM employees employee
                JOIN companies company ON company.id = employee.company_id
                LEFT JOIN positions position ON position.id = employee.position_id
                LEFT JOIN departments department ON department.id = employee.department_id
                WHERE {' AND '.join(clauses)}
                ORDER BY employee.is_dismissed, employee.last_name, employee.first_name, employee.id
                """,
                tuple(params),
            )
            employees = [_row_dict(row, _EMPLOYEE_COLUMNS) for row in cursor.fetchall()]

        if actor_state["role"] not in {ROLE_OWNER, ROLE_ADMIN} or status in {
            "active",
            "dismissed",
        }:
            return employees

        invitation_clauses = [
            "invitation.company_id = %s",
            "invitation.accepted_at IS NULL",
            "invitation.revoked_at IS NULL",
            "invitation.expires_at > CURRENT_TIMESTAMP",
        ]
        invitation_params: list[Any] = [company_id]
        if search:
            invitation_clauses.append(
                "(invitation.email_normalized ILIKE %s "
                "OR COALESCE(invitation.profile_data->>'last_name', '') ILIKE %s "
                "OR COALESCE(invitation.profile_data->>'first_name', '') ILIKE %s "
                "OR COALESCE(invitation.profile_data->>'middle_name', '') ILIKE %s)"
            )
            invitation_params.extend([f"%{search}%"] * 4)
        if role:
            invitation_clauses.append("invitation.requested_role = %s")
            invitation_params.append(role)
        cursor.execute(
            f"""
            SELECT invitation.id AS invitation_id,
                   invitation.email_normalized,
                   invitation.requested_role,
                   invitation.profile_data,
                   invitation.expires_at,
                   invitation.created_at,
                   invitation.invited_by,
                   position.title,
                   department.title
            FROM company_invitations invitation
            LEFT JOIN positions position
              ON position.id = CASE
                   WHEN invitation.profile_data->>'position_id' ~ '^[0-9]+$'
                   THEN (invitation.profile_data->>'position_id')::INTEGER
                 END
            LEFT JOIN departments department
              ON department.id = CASE
                   WHEN invitation.profile_data->>'department_id' ~ '^[0-9]+$'
                   THEN (invitation.profile_data->>'department_id')::INTEGER
                 END
            WHERE {' AND '.join(invitation_clauses)}
            ORDER BY invitation.created_at DESC
            """,
            tuple(invitation_params),
        )
        invitation_columns = (
            "invitation_id",
            "email_normalized",
            "requested_role",
            "profile_data",
            "expires_at",
            "created_at",
            "invited_by",
            "position",
            "department",
        )
        for raw_row in cursor.fetchall():
            invitation = _row_dict(raw_row, invitation_columns)
            profile = invitation.get("profile_data") or {}
            if isinstance(profile, str):
                try:
                    profile = json.loads(profile)
                except (TypeError, ValueError):
                    profile = {}
            full_name = " ".join(
                str(profile.get(field) or "").strip()
                for field in ("last_name", "first_name", "middle_name")
            ).strip()
            employees.append(
                {
                    "id": None,
                    "employee_id": None,
                    "invitation_id": invitation.get("invitation_id"),
                    "invited_by": invitation.get("invited_by"),
                    "full_name": full_name,
                    "position": invitation.get("position"),
                    "department": invitation.get("department"),
                    "email": invitation.get("email_normalized"),
                    "requested_role": invitation.get("requested_role"),
                    "role": invitation.get("requested_role"),
                    "status": "pending",
                    "is_dismissed": False,
                    "start_date": profile.get("start_date"),
                    "expires_at": invitation.get("expires_at"),
                    "created_at": invitation.get("created_at"),
                }
            )
        return employees


def _select_target_employee(cursor, actor_id: int, employee_id: int, *, lock=True):
    lock_clause = " FOR UPDATE OF target" if lock else ""
    cursor.execute(
        f"""
        SELECT target.id, target.company_id,
               CASE WHEN company.owner_employee_id = target.id
                    THEN 'company_owner' ELSE COALESCE(target.role, 'employee') END,
               COALESCE(target.is_dismissed, FALSE), target.email,
               company.owner_employee_id
        FROM employees target
        JOIN companies company ON company.id = target.company_id
        WHERE target.id = %s
          AND target.company_id = (
              SELECT actor.company_id FROM employees actor WHERE actor.id = %s
          )
        {lock_clause}
        """,
        (employee_id, actor_id),
    )
    row = cursor.fetchone()
    if not row:
        raise NotFoundError("Employee not found")
    return {
        "employee_id": _row_value(row, 0, "employee_id", "id"),
        "company_id": _row_value(row, 1, "company_id"),
        "role": _row_value(row, 2, "role", default=ROLE_EMPLOYEE),
        "is_dismissed": bool(_row_value(row, 3, "is_dismissed", default=False)),
        "email": _row_value(row, 4, "email"),
        "owner_employee_id": _row_value(row, 5, "owner_employee_id"),
    }


def dismiss_employee(
    actor: AccessContext | Mapping[str, Any] | int,
    employee_id: int,
) -> dict[str, Any]:
    """Dismiss a same-company non-owner and revoke their pending invitations."""
    employee_id = _positive_employee_id(employee_id)
    with _database(write=True) as cursor:
        actor_state = _load_actor(cursor, actor)
        _require_company(actor_state)
        _require_role(actor_state, ROLE_OWNER, ROLE_ADMIN)
        target = _select_target_employee(cursor, actor_state["employee_id"], employee_id)
        if target["employee_id"] == actor_state["employee_id"]:
            raise PermissionDenied("An administrator cannot dismiss their own account")
        if target["role"] == ROLE_OWNER:
            raise PermissionDenied("Company ownership must be transferred before dismissal")
        if target["is_dismissed"]:
            raise ConflictError("Employee is already dismissed")

        completed_statuses = (
            "done",
            "completed",
            "\u0432\u044b\u043f\u043e\u043b\u043d\u0435\u043d\u0430",
            "\u0432\u044b\u043f\u043e\u043b\u043d\u0435\u043d\u043e",
            "\u0437\u0430\u0432\u0435\u0440\u0448\u0435\u043d\u0430",
            "\u0437\u0430\u0432\u0435\u0440\u0448\u0435\u043d\u043e",
        )
        cursor.execute(
            """
            SELECT COUNT(*)
            FROM tasks
            WHERE company_id = %s
              AND executor_id = %s
              AND LOWER(BTRIM(COALESCE(status, ''))) NOT IN (%s, %s, %s, %s, %s, %s)
            """,
            (actor_state["company_id"], employee_id, *completed_statuses),
        )
        active_tasks = int(
            _row_value(cursor.fetchone(), 0, "active_count", "count", default=0)
        )
        if active_tasks:
            raise ConflictError(
                "Employee has active assigned tasks; reassign them before dismissal"
            )

        cursor.execute(
            """
            UPDATE employees SET is_dismissed = TRUE, role = 'employee'
            WHERE id = %s AND company_id = %s AND is_dismissed = FALSE
            """,
            (employee_id, actor_state["company_id"]),
        )
        if cursor.rowcount != 1:
            raise ConflictError("Employee state changed concurrently")
        if target["email"]:
            cursor.execute(
                """
                UPDATE company_invitations SET revoked_at = CURRENT_TIMESTAMP
                WHERE company_id = %s AND email_normalized = LOWER(BTRIM(%s))
                  AND accepted_at IS NULL AND revoked_at IS NULL
                """,
                (actor_state["company_id"], target["email"]),
            )
        _close_membership(cursor, actor_state["company_id"], employee_id, "dismissed")
        _write_audit(
            cursor,
            actor_state,
            "employee.dismissed",
            "employee",
            employee_id,
            old_values={"role": target["role"], "is_dismissed": False},
            new_values={"role": ROLE_EMPLOYEE, "is_dismissed": True},
            metadata={"session_revocation": "login_blocked_by_is_dismissed"},
        )
        return {**target, "role": ROLE_EMPLOYEE, "is_dismissed": True}


def restore_employee(
    actor: AccessContext | Mapping[str, Any] | int,
    employee_id: int,
) -> dict[str, Any]:
    """Restore a dismissed employee as a regular employee if a seat is free."""
    employee_id = _positive_employee_id(employee_id)
    with _database(write=True) as cursor:
        actor_state = _load_actor(cursor, actor)
        company_id = _require_company(actor_state)
        _require_role(actor_state, ROLE_OWNER)
        usage = _lock_company_and_usage(cursor, company_id)
        if usage["used_count"] >= usage["employee_limit"]:
            raise SeatLimitError("The company employee limit has been reached")
        target = _select_target_employee(cursor, actor_state["employee_id"], employee_id)
        if not target["is_dismissed"]:
            raise ConflictError("Employee is already active")

        cursor.execute(
            """
            UPDATE employees SET is_dismissed = FALSE, role = 'employee'
            WHERE id = %s AND company_id = %s AND is_dismissed = TRUE
            """,
            (employee_id, company_id),
        )
        if cursor.rowcount != 1:
            raise ConflictError("Employee state changed concurrently")
        _open_membership(cursor, company_id, employee_id, ROLE_EMPLOYEE, actor_state["employee_id"], "restored")
        _write_audit(
            cursor,
            actor_state,
            "employee.restored",
            "employee",
            employee_id,
            old_values={"is_dismissed": True},
            new_values={"role": ROLE_EMPLOYEE, "is_dismissed": False},
        )
        return {**target, "role": ROLE_EMPLOYEE, "is_dismissed": False}


def assign_company_role(
    actor: AccessContext | Mapping[str, Any] | int,
    employee_id: int,
    role: str,
) -> dict[str, Any]:
    """Assign or remove delegated company_admin; ownership is handled separately."""
    employee_id = _positive_employee_id(employee_id)
    role = str(role).strip()
    if role not in {ROLE_EMPLOYEE, ROLE_ADMIN}:
        raise ValidationError("Only employee and company_admin can be assigned")

    with _database(write=True) as cursor:
        actor_state = _load_actor(cursor, actor)
        company_id = _require_company(actor_state)
        _require_role(actor_state, ROLE_OWNER)
        target = _select_target_employee(cursor, actor_state["employee_id"], employee_id)
        if target["role"] == ROLE_OWNER:
            raise PermissionDenied("The owner role can only be changed by ownership transfer")
        if target["is_dismissed"]:
            raise ConflictError("A dismissed employee cannot receive a role")
        if target["role"] == role:
            return target

        cursor.execute(
            """UPDATE employees SET role = %s WHERE id = %s AND company_id = %s""",
            (role, employee_id, company_id),
        )
        if cursor.rowcount != 1:
            raise ConflictError("Employee state changed concurrently")
        _close_membership(cursor, company_id, employee_id, "active")
        _open_membership(cursor, company_id, employee_id, role, actor_state["employee_id"], "role_changed")
        _write_audit(
            cursor,
            actor_state,
            "employee.role_changed",
            "employee",
            employee_id,
            old_values={"role": target["role"]},
            new_values={"role": role},
        )
        return {**target, "role": role}


def transfer_company_ownership(
    actor: AccessContext | Mapping[str, Any] | int,
    employee_id: int,
) -> dict[str, Any]:
    """Atomically transfer ownership to an active same-company employee."""
    employee_id = _positive_employee_id(employee_id)
    with _database(write=True) as cursor:
        actor_state = _load_actor(cursor, actor, lock=True)
        company_id = _require_company(actor_state)
        _require_role(actor_state, ROLE_OWNER)
        if employee_id == actor_state["employee_id"]:
            raise ConflictError("The selected employee already owns the company")

        cursor.execute("SELECT id FROM companies WHERE id = %s FOR UPDATE", (company_id,))
        if not cursor.fetchone():
            raise NotFoundError("Company not found")
        target = _select_target_employee(cursor, actor_state["employee_id"], employee_id)
        if target["is_dismissed"]:
            raise ConflictError("Ownership cannot be transferred to a dismissed employee")

        previous_owner_id = actor_state["employee_id"]
        cursor.execute(
            """UPDATE employees SET role = 'company_admin' WHERE id = %s AND company_id = %s""",
            (previous_owner_id, company_id),
        )
        cursor.execute(
            """UPDATE employees SET role = 'company_owner' WHERE id = %s AND company_id = %s""",
            (employee_id, company_id),
        )
        if cursor.rowcount != 1:
            raise ConflictError("Employee state changed concurrently")
        cursor.execute(
            """
            UPDATE companies
            SET owner_employee_id = %s, updated_at = clock_timestamp()
            WHERE id = %s AND owner_employee_id = %s
            """,
            (employee_id, company_id, previous_owner_id),
        )
        if cursor.rowcount != 1:
            raise ConflictError("Company ownership changed concurrently")

        _close_membership(cursor, company_id, previous_owner_id, "active")
        _open_membership(
            cursor, company_id, previous_owner_id, ROLE_ADMIN,
            previous_owner_id, "ownership_transferred",
        )
        _close_membership(cursor, company_id, employee_id, "active")
        _open_membership(
            cursor, company_id, employee_id, ROLE_OWNER,
            previous_owner_id, "ownership_received",
        )
        _write_audit(
            cursor,
            actor_state,
            "company.ownership_transferred",
            "company",
            company_id,
            old_values={"owner_employee_id": previous_owner_id},
            new_values={"owner_employee_id": employee_id},
        )
        return {
            "company_id": company_id,
            "previous_owner_employee_id": previous_owner_id,
            "owner_employee_id": employee_id,
        }


__all__ = [
    "CompanyServiceError",
    "PermissionDenied",
    "ValidationError",
    "SeatLimitError",
    "ConflictError",
    "NotFoundError",
    "get_company",
    "create_company",
    "update_company",
    "get_company_usage",
    "create_invitation",
    "list_company_employees",
    "dismiss_employee",
    "restore_employee",
    "assign_company_role",
    "transfer_company_ownership",
]
