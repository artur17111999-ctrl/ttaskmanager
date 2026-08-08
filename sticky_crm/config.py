"""Application configuration loaded from the process environment."""

from __future__ import annotations

import os
from collections.abc import Mapping


_ALLOWED_SSL_MODES = {
    "disable",
    "allow",
    "prefer",
    "require",
    "verify-ca",
    "verify-full",
}


def load_db_config(environ: Mapping[str, str] | None = None) -> dict[str, object]:
    """Build PostgreSQL settings without keeping credentials in source control."""
    values = os.environ if environ is None else environ
    raw_port = values.get("STICKY_CRM_DB_PORT", "5432")
    try:
        port = int(raw_port)
    except (TypeError, ValueError) as error:
        raise ValueError("STICKY_CRM_DB_PORT must be an integer") from error

    sslmode = values.get("STICKY_CRM_DB_SSLMODE", "require")
    if sslmode not in _ALLOWED_SSL_MODES:
        raise ValueError("STICKY_CRM_DB_SSLMODE is invalid")

    config: dict[str, object] = {
        "host": values.get("STICKY_CRM_DB_HOST", "localhost"),
        "port": port,
        "database": values.get("STICKY_CRM_DB_NAME", "sticky_crm"),
        "user": values.get("STICKY_CRM_DB_USER", "sticky_app"),
        "sslmode": sslmode,
    }
    password = values.get("STICKY_CRM_DB_PASSWORD")
    if password:
        config["password"] = password
    ssl_root_certificate = values.get("STICKY_CRM_DB_SSLROOTCERT")
    if ssl_root_certificate:
        config["sslrootcert"] = ssl_root_certificate
    return config


DB_CONFIG = load_db_config()
