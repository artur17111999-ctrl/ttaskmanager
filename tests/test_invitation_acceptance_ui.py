import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = PROJECT_ROOT / "sticky_crm"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QDialog, QLineEdit

import auth_window
import invitation_accept_dialog
from invitation_accept_dialog import InvitationAcceptDialog


class _SettingsStub:
    def __init__(self):
        self.values = {}

    def remove(self, key):
        self.values.pop(key, None)

    def value(self, key, default=None, type=None):
        value = self.values.get(key, default)
        return bool(value) if type is bool else value

    def setValue(self, key, value):
        self.values[key] = value


class InvitationAcceptanceUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def tearDown(self):
        self.app.processEvents()

    def _dialog(self):
        dialog = InvitationAcceptDialog()
        self.addCleanup(dialog.deleteLater)
        self.addCleanup(dialog.close)
        return dialog

    def test_auth_window_exposes_invitation_action_without_login(self):
        with patch.object(auth_window, "QSettings", return_value=_SettingsStub()):
            window = auth_window.AuthWindow()
        try:
            self.assertIn("приглаш", window.invitation_button.text().casefold())
            self.assertTrue(window.invitation_button.isEnabled())
            self.assertEqual(window.invitation_button.objectName(), "acceptInvitationButton")
        finally:
            window.close()
            window.deleteLater()

    def test_auth_action_opens_dialog_and_prefills_only_created_login(self):
        class _AcceptedDialog:
            created_login = "new.user"

            def __init__(self, parent):
                self.parent = parent

            def exec(self):
                return QDialog.Accepted

        with patch.object(auth_window, "QSettings", return_value=_SettingsStub()):
            window = auth_window.AuthWindow()
        try:
            window.password_input.setText("must-be-cleared")
            with patch.object(auth_window, "InvitationAcceptDialog", _AcceptedDialog):
                window.open_invitation()
            self.assertEqual(window.login_input.text(), "new.user")
            self.assertEqual(window.password_input.text(), "")
        finally:
            window.close()
            window.deleteLater()

    def test_dialog_constructs_with_masked_secret_fields(self):
        dialog = self._dialog()

        self.assertEqual(dialog.objectName(), "invitationAcceptDialog")
        self.assertEqual(dialog.token_input.echoMode(), QLineEdit.Password)
        self.assertEqual(dialog.password_input.echoMode(), QLineEdit.Password)
        self.assertEqual(
            dialog.password_confirmation_input.echoMode(), QLineEdit.Password
        )
        self.assertTrue(dialog.preview_frame.isHidden())
        self.assertTrue(dialog.account_frame.isHidden())
        self.assertTrue(dialog.accept_button.isHidden())

    def test_successful_inspection_hides_token_and_reveals_safe_preview(self):
        dialog = self._dialog()
        raw_token = "A" * 43
        preview = {
            "company_name": "Acme",
            "email": "new@example.test",
            "requested_role": "employee",
            "expires_at": "2026-08-12T12:00:00",
            "preview_id": "safe-preview",
            "profile_data": {
                "last_name": "Иванов",
                "first_name": "Иван",
                "position": "Инженер",
                "department": "ИТ",
            },
        }
        dialog.token_input.setText(raw_token)

        with patch.object(
            invitation_accept_dialog, "inspect_invitation", return_value=preview
        ) as inspect:
            dialog._inspect()

        inspect.assert_called_once_with(raw_token)
        self.assertEqual(dialog.token_input.text(), "")
        self.assertTrue(dialog.token_frame.isHidden())
        self.assertFalse(dialog.preview_frame.isHidden())
        self.assertFalse(dialog.account_frame.isHidden())
        self.assertEqual(dialog.company_value.text(), "Acme")
        self.assertEqual(dialog.email_value.text(), "new@example.test")
        self.assertNotIn("company_id", dialog._preview)
        self.assertNotIn("employee_limit", dialog._preview)

    def test_invalid_invitation_states_have_one_public_message(self):
        dialog = self._dialog()
        messages = []
        error_type = invitation_accept_dialog.InvalidInvitationError

        for token_state in ("unknown", "expired", "revoked", "accepted"):
            dialog.token_input.setText(f"valid-shape-{token_state}")
            with patch.object(
                invitation_accept_dialog,
                "inspect_invitation",
                side_effect=error_type(),
            ):
                dialog._inspect()
            messages.append(dialog.error_label.text())

        self.assertEqual(len(set(messages)), 1)
        self.assertEqual(
            messages[0], invitation_accept_dialog.INVALID_INVITATION_MESSAGE
        )
        self.assertNotRegex(messages[0].casefold(), r"expired|revoked|accepted|unknown")

    def test_accept_request_cannot_supply_company_or_role(self):
        dialog = self._dialog()
        raw_token = "B" * 43
        dialog._token = raw_token
        dialog._idempotency_key = "request-key"
        dialog.login_input.setText("new.user")
        dialog.password_input.setText("StrongPassword!234")
        dialog.password_confirmation_input.setText("StrongPassword!234")
        dialog.consent_checkbox.setChecked(True)

        with patch.object(
            invitation_accept_dialog,
            "accept_invitation",
            return_value={"login": "new.user"},
        ) as accept, patch.object(invitation_accept_dialog.QMessageBox, "information"):
            dialog._accept_invitation()

        accept.assert_called_once()
        token, account_data = accept.call_args.args
        self.assertEqual(token, raw_token)
        self.assertEqual(account_data["login"], "new.user")
        self.assertIn("password", account_data)
        for forbidden in (
            "company_id",
            "role",
            "requested_role",
            "owner_employee_id",
            "employee_limit",
            "is_dismissed",
            "status",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, account_data)
        self.assertEqual(accept.call_args.kwargs["idempotency_key"], "request-key")

    def test_closing_dialog_clears_in_memory_secrets(self):
        dialog = self._dialog()
        dialog._token = "sensitive-token"
        dialog._idempotency_key = "request-key"
        dialog.token_input.setText("sensitive-token")
        dialog.password_input.setText("SensitivePassword!234")
        dialog.password_confirmation_input.setText("SensitivePassword!234")

        dialog.done(QDialog.Rejected)

        self.assertIsNone(dialog._token)
        self.assertIsNone(dialog._idempotency_key)
        self.assertEqual(dialog.token_input.text(), "")
        self.assertEqual(dialog.password_input.text(), "")
        self.assertEqual(dialog.password_confirmation_input.text(), "")


if __name__ == "__main__":
    unittest.main()
