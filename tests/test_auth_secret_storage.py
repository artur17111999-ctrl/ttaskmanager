import inspect
import os
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = PROJECT_ROOT / "sticky_crm"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from auth_window import AuthWindow


class _SettingsSpy:
    def __init__(self, values=None):
        self.values = dict(values or {})
        self.read_keys = []
        self.write_keys = []
        self.removed_keys = []

    def setValue(self, key, value):
        self.write_keys.append(key)
        self.values[key] = value

    def value(self, key, default=None, type=None):
        self.read_keys.append(key)
        value = self.values.get(key, default)
        if type is bool:
            return bool(value)
        return value

    def remove(self, key):
        self.removed_keys.append(key)
        self.values.pop(key, None)


class _CheckBox:
    def __init__(self, checked=False):
        self.checked = checked

    def isChecked(self):
        return self.checked

    def setChecked(self, checked):
        self.checked = bool(checked)


class _LineEdit:
    def __init__(self, text=""):
        self.value = text

    def setText(self, text):
        self.value = text

    def text(self):
        return self.value


def _invoke_save_credentials(harness, login, password):
    parameters = inspect.signature(AuthWindow.save_credentials).parameters
    if len(parameters) == 3:
        AuthWindow.save_credentials(harness, login, password)
    else:
        AuthWindow.save_credentials(harness, login)


class AuthSecretStorageTests(unittest.TestCase):
    def test_remember_me_never_writes_password_to_qsettings(self):
        harness = type("AuthHarness", (), {})()
        harness.settings = _SettingsSpy({"password": "legacy-secret"})
        harness.remember_checkbox = _CheckBox(True)

        _invoke_save_credentials(harness, "user", "new-secret")

        self.assertEqual(harness.settings.values.get("login"), "user")
        self.assertTrue(harness.settings.values.get("remember"))
        self.assertNotIn("password", harness.settings.write_keys)
        self.assertNotIn("password", harness.settings.values)
        self.assertIn(
            "password",
            harness.settings.removed_keys,
            "An upgrade must remove passwords persisted by older clients",
        )

    def test_loading_remembered_login_purges_legacy_password_without_reading_it(self):
        harness = type("AuthHarness", (), {})()
        harness.settings = _SettingsSpy(
            {"remember": True, "login": "remembered-user", "password": "legacy-secret"}
        )
        harness.login_input = _LineEdit()
        harness.password_input = _LineEdit()
        harness.remember_checkbox = _CheckBox()

        AuthWindow.load_saved_credentials(harness)

        self.assertEqual(harness.login_input.text(), "remembered-user")
        self.assertEqual(harness.password_input.text(), "")
        self.assertNotIn("password", harness.settings.read_keys)
        self.assertNotIn("password", harness.settings.values)
        self.assertIn("password", harness.settings.removed_keys)

    def test_auth_source_has_no_password_qsettings_key_access(self):
        source = inspect.getsource(AuthWindow)
        self.assertNotRegex(
            source,
            r"(?:setValue|value)\s*\(\s*['\"]password['\"]",
        )


if __name__ == "__main__":
    unittest.main()
