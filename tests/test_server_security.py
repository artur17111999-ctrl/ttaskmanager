import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace


PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = PROJECT_ROOT / "sticky_crm"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from server_security import (
    AuthenticationRequired,
    ChatMembership,
    ClientUpgradeRequired,
    PermissionDenied,
    ResourceNotFound,
    SessionRecord,
    TrustedPrincipal,
    authenticate_session,
    digest_session_token,
    require_chat_permission,
    require_supported_client_version,
)


TOKEN = "s" * 43
NOW = datetime(2026, 8, 6, 12, 0, tzinfo=timezone.utc)


def _session(**overrides):
    values = {
        "session_id": "session-public-id",
        "token_hash": digest_session_token(TOKEN),
        "account_id": 10,
        "employee_id": 20,
        "company_id": 30,
        "role": "company_admin",
        "session_generation": 4,
        "current_session_generation": 4,
        "expires_at": NOW + timedelta(minutes=15),
    }
    values.update(overrides)
    return SessionRecord(**values)


class SessionSecurityTests(unittest.TestCase):
    def test_active_session_derives_trusted_principal(self):
        principal = authenticate_session(TOKEN, _session(), now=NOW)

        self.assertTrue(principal.principal_trusted)
        self.assertEqual(principal.employee_id, 20)
        self.assertEqual(principal.company_id, 30)

    def test_invalid_and_revoked_sessions_share_public_error(self):
        candidates = (
            ("x" * 43, _session()),
            (TOKEN, _session(revoked_at=NOW)),
            (TOKEN, _session(expires_at=NOW)),
            (TOKEN, _session(current_session_generation=5)),
            (TOKEN, _session(employee_status="dismissed")),
            (TOKEN, _session(company_status="blocked")),
        )
        for token, record in candidates:
            with self.subTest(record=record), self.assertRaisesRegex(
                AuthenticationRequired, "^Authentication required$"
            ):
                authenticate_session(token, record, now=NOW)

    def test_token_digest_is_domain_separated_and_contains_no_raw_token(self):
        digest = digest_session_token(TOKEN)

        self.assertEqual(len(digest), 64)
        self.assertNotIn(TOKEN, digest)

    def test_trusted_principal_cannot_be_constructed_from_request_values(self):
        with self.assertRaisesRegex(AuthenticationRequired, "^Authentication required$"):
            TrustedPrincipal(
                session_id="client-value",
                account_id=10,
                employee_id=20,
                company_id=30,
                role="company_owner",
                session_generation=4,
            )


class VersionGateTests(unittest.TestCase):
    def test_supported_client_is_accepted(self):
        require_supported_client_version("1.4.0", "1.3.9")

    def test_old_or_malformed_client_uses_one_public_error(self):
        for version in ("1.3.8", "1.4", "latest", ""):
            with self.subTest(version=version), self.assertRaisesRegex(
                ClientUpgradeRequired, "^Client update required$"
            ):
                require_supported_client_version(version, "1.3.9")


class ChatPermissionTests(unittest.TestCase):
    def setUp(self):
        self.principal = authenticate_session(TOKEN, _session(), now=NOW)

    def test_active_member_can_read_and_send(self):
        membership = ChatMembership(30, 20, "active", "member")

        require_chat_permission(self.principal, membership, "chat.read")
        require_chat_permission(self.principal, membership, "message.send")

    def test_admin_role_does_not_grant_access_without_membership(self):
        with self.assertRaisesRegex(ResourceNotFound, "^Resource not found$"):
            require_chat_permission(self.principal, None, "chat.read")

    def test_cross_tenant_and_other_employee_are_hidden_as_not_found(self):
        memberships = (
            ChatMembership(31, 20, "active", "owner"),
            ChatMembership(30, 21, "active", "owner"),
            ChatMembership(30, 20, "left", "owner"),
        )
        for membership in memberships:
            with self.subTest(membership=membership), self.assertRaisesRegex(
                ResourceNotFound, "^Resource not found$"
            ):
                require_chat_permission(self.principal, membership, "chat.read")

    def test_read_only_member_cannot_send(self):
        membership = ChatMembership(30, 20, "active", "read_only")

        with self.assertRaisesRegex(PermissionDenied, "^Permission denied$"):
            require_chat_permission(self.principal, membership, "message.send")

    def test_untrusted_principal_is_rejected(self):
        untrusted = SimpleNamespace(
            principal_trusted=False,
            employee_id=20,
            company_id=30,
            role="company_admin",
        )

        with self.assertRaisesRegex(AuthenticationRequired, "^Authentication required$"):
            require_chat_permission(
                untrusted,
                ChatMembership(30, 20, "active"),
                "chat.read",
            )


if __name__ == "__main__":
    unittest.main()
