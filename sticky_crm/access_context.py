"""Immutable user access context shared by application windows."""

from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from typing import Any, ClassVar, Optional


@dataclass(frozen=True)
class AccessContext(Mapping[str, Any]):
    """Authenticated user data with dict-compatible read access.

    ``principal_trusted`` remains false for the current direct database login.
    A future server API may set it only after validating a server-side session.
    """

    account_id: int
    employee_id: int
    last_name: str
    first_name: str
    middle_name: Optional[str]
    email: str
    full_name: str
    company_id: Optional[int] = None
    company_name: Optional[str] = None
    role: str = "employee"
    status: str = "active"
    company_status: Optional[str] = None
    principal_trusted: bool = False
    session_generation: int = 0

    _KEYS: ClassVar[tuple[str, ...]] = (
        "account_id",
        "employee_id",
        "last_name",
        "first_name",
        "middle_name",
        "email",
        "full_name",
        "company_id",
        "company_name",
        "role",
        "status",
        "company_status",
        "principal_trusted",
        "session_generation",
    )

    def __getitem__(self, key: str) -> Any:
        if key not in self._KEYS:
            raise KeyError(key)
        return getattr(self, key)

    def __iter__(self) -> Iterator[str]:
        return iter(self._KEYS)

    def __len__(self) -> int:
        return len(self._KEYS)

    def to_dict(self) -> dict[str, Any]:
        """Return a detached mutable copy for serialization or legacy APIs."""
        return {key: self[key] for key in self}


def coerce_access_context(user_data: Mapping[str, Any]) -> AccessContext:
    """Convert legacy login dictionaries without breaking existing callers."""
    if isinstance(user_data, AccessContext):
        return user_data

    last_name = str(user_data.get("last_name") or "")
    first_name = str(user_data.get("first_name") or "")
    middle_name = user_data.get("middle_name") or None
    full_name = str(user_data.get("full_name") or "").strip()
    if not full_name:
        full_name = " ".join(
            value for value in (last_name, first_name, middle_name) if value
        ).strip()

    company_id = user_data.get("company_id")

    return AccessContext(
        account_id=int(user_data.get("account_id") or 0),
        employee_id=int(user_data["employee_id"]),
        last_name=last_name,
        first_name=first_name,
        middle_name=middle_name,
        email=str(user_data.get("email") or ""),
        full_name=full_name,
        company_id=int(company_id) if company_id is not None else None,
        company_name=user_data.get("company_name"),
        role=str(user_data.get("role") or "employee"),
        status=str(user_data.get("status") or "active"),
        company_status=user_data.get("company_status"),
        principal_trusted=bool(user_data.get("principal_trusted", False)),
        session_generation=int(user_data.get("session_generation") or 0),
    )
