import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = PROJECT_ROOT / "sticky_crm"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from config import load_db_config


class DatabaseConfigurationSecurityTests(unittest.TestCase):
    def test_database_password_has_no_source_default(self):
        config = load_db_config({})

        self.assertNotIn("password", config)
        self.assertEqual(config["user"], "sticky_app")
        self.assertEqual(config["database"], "sticky_crm")
        self.assertEqual(config["sslmode"], "require")

    def test_database_settings_are_loaded_from_environment(self):
        config = load_db_config(
            {
                "STICKY_CRM_DB_HOST": "db.internal",
                "STICKY_CRM_DB_PORT": "5544",
                "STICKY_CRM_DB_NAME": "sticky",
                "STICKY_CRM_DB_USER": "sticky_app",
                "STICKY_CRM_DB_PASSWORD": "runtime-secret",
                "STICKY_CRM_DB_SSLMODE": "verify-full",
                "STICKY_CRM_DB_SSLROOTCERT": "C:/certs/company-ca.pem",
            }
        )

        self.assertEqual(
            config,
            {
                "host": "db.internal",
                "port": 5544,
                "database": "sticky",
                "user": "sticky_app",
                "sslmode": "verify-full",
                "sslrootcert": "C:/certs/company-ca.pem",
                "password": "runtime-secret",
            },
        )

    def test_invalid_database_port_is_rejected_without_connection_attempt(self):
        with self.assertRaisesRegex(ValueError, "must be an integer"):
            load_db_config({"STICKY_CRM_DB_PORT": "not-a-port"})

    def test_invalid_ssl_mode_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "SSLMODE is invalid"):
            load_db_config({"STICKY_CRM_DB_SSLMODE": "trust-everything"})


if __name__ == "__main__":
    unittest.main()
