"""Framework-neutral security primitives for the future server API."""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import FrozenSet, Optional


SESSION_TOKEN_BYTES = 32
_TOKEN_DOMAIN = b"sticky-crm/session/v1\0"
_ACTIVE = "active"
_CLIENT_VERSION_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")


class AuthenticationRequired(RuntimeError):
    """Public authentication failure without account-enumeration details."""


class ClientUpgradeRequired(RuntimeError):
    """Raised when a client is older than the server's minimum version."""


class ResourceNotFound(RuntimeError):
    """Used for both absent and inaccessible resources to avoid IDOR disclosure."""


class PermissionDenied(RuntimeError):
    """Raised for a visible resource when the requested action is not permitted."""


@dataclass(frozen=True)
class SessionRecord:
    """Server-loaded session and lifecycle state; never built from request JSON."""

    session_id: str
    token_hash: str
    account_id: int
    employee_id: int
    company_id: int
    role: str
    session_generation: int
    current_session_generation: int
    expires_at: datetime
    account_status: str = _ACTIVE
    employee_status: str = _ACTIVE
    company_status: str = _ACTIVE
    revoked_at: Optional[datetime] = None


@dataclass(frozen=True, init=False)
class TrustedPrincipal:
    """Identity accepted only after server-side session validation."""

    session_id: str
    account_id: int
    employee_id: int
    company_id: int
    role: str
    session_generation: int

    def __init__(self, *args, **kwargs) -> None:
        raise AuthenticationRequired("Authentication required")

    @property
    def principal_trusted(self) -> bool:
        return True


@dataclass(frozen=True)
class ChatMembership:
    """Chat and membership facts loaded in one tenant-scoped server query."""

    chat_company_id: int
    employee_id: int
    membership_status: str
    member_role: str = "member"
    permissions: FrozenSet[str] = frozenset()


def _trusted_principal_from_session(record: SessionRecord) -> TrustedPrincipal:
    principal = object.__new__(TrustedPrincipal)
    object.__setattr__(principal, "session_id", record.session_id)
    object.__setattr__(principal, "account_id", record.account_id)
    object.__setattr__(principal, "employee_id", record.employee_id)
    object.__setattr__(principal, "company_id", record.company_id)
    object.__setattr__(principal, "role", record.role)
    object.__setattr__(principal, "session_generation", record.session_generation)
    return principal


def generate_session_token() -> str:
    """Return a high-entropy secret that must be shown to the client only once."""
    return secrets.token_urlsafe(SESSION_TOKEN_BYTES)


def digest_session_token(token: str) -> str:
    """Hash a bearer secret for persistent lookup without storing the raw token."""
    if not isinstance(token, str) or not 32 <= len(token) <= 512:
        raise AuthenticationRequired("Authentication required")
    return hashlib.sha256(_TOKEN_DOMAIN + token.encode("utf-8")).hexdigest()


def authenticate_session(
    token: str,
    record: SessionRecord,
    *,
    now: Optional[datetime] = None,
) -> TrustedPrincipal:
    """Validate a server-loaded session and derive the only trusted principal."""
    try:
        candidate_hash = digest_session_token(token)
    except (AuthenticationRequired, UnicodeError):
        candidate_hash = hashlib.sha256(_TOKEN_DOMAIN + b"invalid-token-probe").hexdigest()

    expected_hash = str(record.token_hash or "")
    token_matches = hmac.compare_digest(candidate_hash, expected_hash)
    current_time = now or datetime.now(timezone.utc)
    expires_at = _as_aware_utc(record.expires_at)
    is_active = (
        token_matches
        and record.revoked_at is None
        and expires_at > _as_aware_utc(current_time)
        and record.session_generation == record.current_session_generation
        and record.account_status == _ACTIVE
        and record.employee_status == _ACTIVE
        and record.company_status == _ACTIVE
        and record.account_id > 0
        and record.employee_id > 0
        and record.company_id > 0
    )
    if not is_active:
        raise AuthenticationRequired("Authentication required")

    return _trusted_principal_from_session(record)


def require_supported_client_version(value: str, minimum: str) -> None:
    """Enforce a server-controlled minimum desktop/API client version."""
    current_version = _parse_version(value)
    minimum_version = _parse_version(minimum)
    if current_version < minimum_version:
        raise ClientUpgradeRequired("Client update required")


def require_chat_permission(
    principal: TrustedPrincipal,
    membership: Optional[ChatMembership],
    permission: str,
) -> None:
    """Authorize one chat operation without granting admins implicit message access."""
    if not isinstance(principal, TrustedPrincipal):
        raise AuthenticationRequired("Authentication required")
    if (
        membership is None
        or membership.chat_company_id != principal.company_id
        or membership.employee_id != principal.employee_id
        or membership.membership_status != _ACTIVE
    ):
        raise ResourceNotFound("Resource not found")

    allowed = set(membership.permissions)
    if membership.member_role in {"member", "moderator", "owner"}:
        allowed.update({"chat.read", "message.send"})
    elif membership.member_role == "read_only":
        allowed.add("chat.read")
    if membership.member_role in {"moderator", "owner"}:
        allowed.update({"chat.manage_members", "chat.pin_message"})
    if membership.member_role == "owner":
        allowed.add("chat.archive")

    if permission not in allowed:
        raise PermissionDenied("Permission denied")


def _parse_version(value: str) -> tuple[int, int, int]:
    match = _CLIENT_VERSION_RE.fullmatch(str(value or ""))
    if not match:
        raise ClientUpgradeRequired("Client update required")
    return tuple(int(part) for part in match.groups())


def _as_aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
