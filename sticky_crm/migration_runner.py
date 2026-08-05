"""Explicit CLI runner for managed database migrations (version 010 and newer)."""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import psycopg2

try:
    from .config import DB_CONFIG
except ImportError:  # Support direct execution from the sticky_crm directory.
    from config import DB_CONFIG


MANAGED_FROM_VERSION = 10
MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"
MIGRATION_FILE_RE = re.compile(r"^(\d{3,})_[A-Za-z0-9][A-Za-z0-9_-]*\.sql$")
DOLLAR_QUOTE_RE = re.compile(r"\$(?:[A-Za-z_][A-Za-z0-9_]*)?\$")
ADVISORY_LOCK_KEYS = (0x53544352, 0x4D494752)  # "STCR", "MIGR"


class MigrationError(RuntimeError):
    """Raised when migration files or database history are unsafe to use."""


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    checksum: str
    sql: str
    path: Path


@dataclass(frozen=True)
class AppliedMigration:
    version: int
    name: str
    checksum: str
    applied_at: datetime


def _skip_quoted(sql: str, start: int, quote: str) -> int:
    index = start + 1
    while index < len(sql):
        if sql[index] == "\\":
            index += 2
            continue
        if sql[index] == quote:
            if index + 1 < len(sql) and sql[index + 1] == quote:
                index += 2
                continue
            return index + 1
        index += 1
    raise MigrationError("Unterminated quoted string or identifier in migration SQL")


def _top_level_statements(sql: str) -> list[str]:
    """Split SQL while ignoring semicolons inside comments, quotes, and DO bodies."""
    statements: list[str] = []
    current: list[str] = []
    index = 0

    while index < len(sql):
        if sql.startswith("--", index):
            newline = sql.find("\n", index + 2)
            if newline == -1:
                break
            current.append("\n")
            index = newline + 1
            continue

        if sql.startswith("/*", index):
            depth = 1
            index += 2
            while index < len(sql) and depth:
                if sql.startswith("/*", index):
                    depth += 1
                    index += 2
                elif sql.startswith("*/", index):
                    depth -= 1
                    index += 2
                else:
                    index += 1
            if depth:
                raise MigrationError("Unterminated block comment in migration SQL")
            current.append(" ")
            continue

        if sql[index] in ("'", '"'):
            end = _skip_quoted(sql, index, sql[index])
            current.append(sql[index:end])
            index = end
            continue

        if sql[index] == "$":
            match = DOLLAR_QUOTE_RE.match(sql, index)
            if match:
                delimiter = match.group(0)
                end = sql.find(delimiter, match.end())
                if end == -1:
                    raise MigrationError(
                        f"Unterminated dollar-quoted block {delimiter} in migration SQL"
                    )
                end += len(delimiter)
                current.append(sql[index:end])
                index = end
                continue

        if sql[index] == ";":
            statement = "".join(current).strip()
            if statement:
                statements.append(statement)
            current = []
            index += 1
            continue

        current.append(sql[index])
        index += 1

    statement = "".join(current).strip()
    if statement:
        statements.append(statement)
    return statements


def _validate_atomic_sql(migration: Migration) -> None:
    forbidden_prefixes = (
        "BEGIN",
        "START TRANSACTION",
        "COMMIT",
        "ROLLBACK",
        "SAVEPOINT",
        "RELEASE SAVEPOINT",
        "PREPARE TRANSACTION",
        "VACUUM",
        "CREATE DATABASE",
        "DROP DATABASE",
        "CREATE TABLESPACE",
        "DROP TABLESPACE",
        "ALTER SYSTEM",
    )

    statements = _top_level_statements(migration.sql)
    if not statements:
        raise MigrationError(f"Migration is empty: {migration.name}")

    for statement in statements:
        normalized = " ".join(statement.split()).upper()
        if any(
            normalized == prefix or normalized.startswith(prefix + " ")
            for prefix in forbidden_prefixes
        ):
            raise MigrationError(
                f"Migration {migration.name} contains transaction-unsafe statement: "
                f"{normalized[:80]}"
            )
        if " CONCURRENTLY " in f" {normalized} ":
            raise MigrationError(
                f"Migration {migration.name} uses CONCURRENTLY and cannot be atomic"
            )


def discover_migrations() -> list[Migration]:
    if not MIGRATIONS_DIR.is_dir():
        raise MigrationError(f"Migration directory not found: {MIGRATIONS_DIR}")

    migrations: list[Migration] = []
    seen_versions: set[int] = set()
    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        match = MIGRATION_FILE_RE.fullmatch(path.name)
        if not match:
            continue

        version = int(match.group(1))
        if version < MANAGED_FROM_VERSION:
            continue
        if version in seen_versions:
            raise MigrationError(f"Duplicate migration version: {version:03d}")

        raw = path.read_bytes()
        try:
            sql = raw.decode("utf-8-sig")
        except UnicodeDecodeError as error:
            raise MigrationError(f"Migration is not UTF-8: {path.name}") from error

        migration = Migration(
            version=version,
            name=path.name,
            checksum=hashlib.sha256(raw).hexdigest(),
            sql=sql,
            path=path,
        )
        _validate_atomic_sql(migration)
        migrations.append(migration)
        seen_versions.add(version)

    if not migrations:
        raise MigrationError(
            f"No managed migrations found from version {MANAGED_FROM_VERSION:03d}"
        )

    migrations.sort(key=lambda item: item.version)
    for expected, migration in enumerate(migrations, start=MANAGED_FROM_VERSION):
        if migration.version != expected:
            raise MigrationError(
                f"Missing migration version {expected:03d} before {migration.name}"
            )
    return migrations


def _schema_migrations_exists(cursor) -> bool:
    cursor.execute("SELECT to_regclass('public.schema_migrations')")
    return cursor.fetchone()[0] is not None


def _load_applied(cursor) -> dict[int, AppliedMigration]:
    if not _schema_migrations_exists(cursor):
        return {}

    cursor.execute(
        """
        SELECT version, name, checksum, applied_at
        FROM public.schema_migrations
        WHERE version >= %s
        ORDER BY version
        """,
        (MANAGED_FROM_VERSION,),
    )
    return {
        row[0]: AppliedMigration(
            version=row[0],
            name=row[1],
            checksum=row[2],
            applied_at=row[3],
        )
        for row in cursor.fetchall()
    }


def _verify_history(
    migrations: list[Migration], applied: dict[int, AppliedMigration]
) -> list[Migration]:
    files_by_version = {migration.version: migration for migration in migrations}

    for version, record in applied.items():
        migration = files_by_version.get(version)
        if migration is None:
            raise MigrationError(
                f"Applied migration {version:03d} is missing from disk"
            )
        if record.name != migration.name:
            raise MigrationError(
                f"Migration {version:03d} name changed: "
                f"database={record.name!r}, file={migration.name!r}"
            )
        if record.checksum != migration.checksum:
            raise MigrationError(
                f"Migration {migration.name} checksum changed after it was applied"
            )

    pending: list[Migration] = []
    pending_seen = False
    for migration in migrations:
        if migration.version in applied:
            if pending_seen:
                raise MigrationError(
                    f"Applied migration {migration.name} appears after a pending version"
                )
        else:
            pending_seen = True
            pending.append(migration)
    return pending


def _print_status(
    migrations: list[Migration], applied: dict[int, AppliedMigration]
) -> None:
    for migration in migrations:
        record = applied.get(migration.version)
        if record:
            timestamp = record.applied_at.isoformat()
            print(f"[applied] {migration.name} at {timestamp}")
        else:
            print(f"[pending] {migration.name}")


def check_migrations() -> None:
    migrations = discover_migrations()
    connection = psycopg2.connect(**DB_CONFIG)
    try:
        connection.set_session(readonly=True, autocommit=False)
        with connection.cursor() as cursor:
            applied = _load_applied(cursor)
        pending = _verify_history(migrations, applied)
        _print_status(migrations, applied)
        print(
            f"Migration history is consistent; {len(pending)} migration(s) pending. "
            "No database changes were made."
        )
        connection.rollback()
    finally:
        connection.close()


def _acquire_lock(connection) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT pg_try_advisory_lock(%s, %s)",
            ADVISORY_LOCK_KEYS,
        )
        acquired = cursor.fetchone()[0]
    connection.commit()
    if not acquired:
        raise MigrationError("Another migration runner holds the advisory lock")


def _release_lock(connection) -> None:
    connection.rollback()
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT pg_advisory_unlock(%s, %s)",
            ADVISORY_LOCK_KEYS,
        )
        released = cursor.fetchone()[0]
    connection.commit()
    if not released:
        print("Warning: advisory lock was not held by this session", file=sys.stderr)


def _ensure_history_table(connection) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS public.schema_migrations (
                version INTEGER PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                checksum VARCHAR(64) NOT NULL,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT ck_schema_migrations_managed_version
                    CHECK (version >= 10),
                CONSTRAINT ck_schema_migrations_checksum
                    CHECK (checksum ~ '^[0-9a-f]{64}$')
            )
            """
        )
    connection.commit()


def apply_migrations() -> None:
    migrations = discover_migrations()
    connection = psycopg2.connect(**DB_CONFIG)
    lock_acquired = False
    try:
        _acquire_lock(connection)
        lock_acquired = True
        _ensure_history_table(connection)

        with connection.cursor() as cursor:
            applied = _load_applied(cursor)
        pending = _verify_history(migrations, applied)

        if not pending:
            _print_status(migrations, applied)
            print("No pending migrations.")
            return

        for migration in pending:
            print(f"Applying {migration.name} ...", flush=True)
            try:
                with connection.cursor() as cursor:
                    cursor.execute(migration.sql)
                    cursor.execute(
                        """
                        INSERT INTO public.schema_migrations
                            (version, name, checksum)
                        VALUES (%s, %s, %s)
                        """,
                        (migration.version, migration.name, migration.checksum),
                    )
                connection.commit()
            except Exception as error:
                connection.rollback()
                raise MigrationError(
                    f"Migration {migration.name} failed; its transaction was rolled back"
                ) from error
            print(f"Applied {migration.name}")

        print(f"Applied {len(pending)} migration(s) successfully.")
    finally:
        if lock_acquired and not connection.closed:
            try:
                _release_lock(connection)
            except psycopg2.Error as error:
                print(f"Warning: failed to release advisory lock: {error}", file=sys.stderr)
        connection.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Check or explicitly apply Sticky CRM migrations 010 and newer."
    )
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument(
        "--check",
        action="store_true",
        help="Read migration state and verify checksums without changing the database.",
    )
    action.add_argument(
        "--apply",
        action="store_true",
        help="Acquire the migration lock and apply all pending migrations.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.check:
            check_migrations()
        else:
            apply_migrations()
        return 0
    except (MigrationError, OSError, psycopg2.Error) as error:
        print(f"Migration error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
