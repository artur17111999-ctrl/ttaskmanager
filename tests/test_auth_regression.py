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

from auth_window import AuthWindow


REQUIRED_ACCESS_CONTEXT_FIELDS = {
    "account_id",
    "employee_id",
    "full_name",
    "company_id",
    "company_name",
    "role",
}


class _TextInput:
    def __init__(self, value):
        self._value = value

    def text(self):
        return self._value


class _ErrorLabel:
    def __init__(self):
        self.visible = None

    def setVisible(self, visible):
        self.visible = visible


class _AuthHarness:
    def __init__(self, login="user", password="secret"):
        self.login_input = _TextInput(login)
        self.password_input = _TextInput(password)
        self.error_label = _ErrorLabel()
        self.user_data = None
        self.accepted = False
        self.saved_credentials = None
        self.error = None

    def save_credentials(self, login, password):
        self.saved_credentials = (login, password)

    def accept(self):
        self.accepted = True

    def show_error(self, message):
        self.error = message
        self.error_label.setVisible(True)


class AuthWindowRegressionTests(unittest.TestCase):
    def test_successful_login_preserves_complete_access_context(self):
        context = {
            "account_id": 11,
            "employee_id": 22,
            "last_name": "Иванов",
            "first_name": "Иван",
            "middle_name": None,
            "email": "ivanov@example.test",
            "full_name": "Иванов Иван",
            "company_id": 33,
            "company_name": "Компания A",
            "role": "employee",
        }
        harness = _AuthHarness()

        with patch("db.check_user", return_value=(True, context)) as check_user:
            AuthWindow.handle_login(harness)

        check_user.assert_called_once_with("user", "secret")
        self.assertTrue(harness.accepted)
        self.assertEqual(harness.user_data, context)
        self.assertEqual(harness.saved_credentials, ("user", "secret"))
        self.assertTrue(REQUIRED_ACCESS_CONTEXT_FIELDS.issubset(harness.user_data))

    def test_failed_login_does_not_accept_or_save_credentials(self):
        harness = _AuthHarness()

        with patch("db.check_user", return_value=(False, "Доступ запрещен")):
            AuthWindow.handle_login(harness)

        self.assertFalse(harness.accepted)
        self.assertIsNone(harness.user_data)
        self.assertIsNone(harness.saved_credentials)
        self.assertEqual(harness.error, "Доступ запрещен")

    def test_empty_credentials_do_not_call_database(self):
        harness = _AuthHarness(login="", password="")

        with patch("db.check_user") as check_user:
            AuthWindow.handle_login(harness)

        check_user.assert_not_called()
        self.assertFalse(harness.accepted)
        self.assertEqual(harness.error, "Заполните все поля")


if __name__ == "__main__":
    unittest.main()

