"""SQLite schema and project configuration for the voice catalog."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import re
import sqlite3
from typing import Iterator


DEFAULT_DB = Path(__file__).resolve().parent / "data" / "library.sqlite3"
MIGRATIONS = Path(__file__).resolve().parent / "migrations"
PROVIDER = "google_gemini"
ENV_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def latest_version() -> int:
    scripts = sorted(MIGRATIONS.glob("[0-9][0-9][0-9][0-9]_*.sql"))
    versions = [int(path.name[:4]) for path in scripts]
    if versions != list(range(1, len(versions) + 1)):
        raise RuntimeError("Migration versions must be consecutive from 0001")
    return len(scripts)


def migrate(conn: sqlite3.Connection) -> int:
    scripts = sorted(MIGRATIONS.glob("[0-9][0-9][0-9][0-9]_*.sql"))
    latest_version()
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    if version > len(scripts):
        raise RuntimeError("Database schema is newer than this package")
    for path in scripts[version:]:
        try:
            conn.executescript(path.read_text(encoding="utf-8"))
        except Exception:
            conn.rollback()
            raise
    return conn.execute("PRAGMA user_version").fetchone()[0]


def _voice_identities(conn: sqlite3.Connection) -> list[tuple[str, str, str, str]]:
    exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='voices'"
    ).fetchone()
    if not exists:
        return []
    return conn.execute(
        """SELECT p.provider, p.project_id, v.provider_voice_id, v.id
           FROM voices v JOIN provider_projects p ON p.id=v.provider_project_id
           ORDER BY p.provider, p.project_id, v.provider_voice_id"""
    ).fetchall()


def backup_database(path: Path) -> Path:
    """Copy and verify an existing database before an explicit migration."""
    path = Path(path).resolve()
    source = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
    try:
        if source.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RuntimeError("Source database failed integrity check")
        original = _voice_identities(source)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        backup_path = path.with_name(f"{path.stem}.pre_migration_{stamp}{path.suffix}")
        if backup_path.exists():
            raise RuntimeError("Migration backup path already exists")
        target = sqlite3.connect(backup_path)
        try:
            source.backup(target)
        finally:
            target.close()
        copy = sqlite3.connect(backup_path.as_uri() + "?mode=ro", uri=True)
        try:
            copy.execute("PRAGMA foreign_keys=ON")
            if copy.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise RuntimeError("Migration backup failed integrity check")
            if copy.execute("PRAGMA foreign_key_check").fetchall():
                raise RuntimeError("Migration backup failed foreign key check")
            if _voice_identities(copy) != original:
                raise RuntimeError("Migration backup changed voice identities")
        finally:
            copy.close()
        return backup_path
    finally:
        source.close()


def initialize_database(path: Path = DEFAULT_DB) -> tuple[int, Path | None]:
    """Create or explicitly migrate the catalog, backing up existing older schemas."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    backup_path = None
    if path.exists():
        source = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
        try:
            current = source.execute("PRAGMA user_version").fetchone()[0]
        finally:
            source.close()
        if current < latest_version():
            backup_path = backup_database(path)
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        return migrate(conn), backup_path
    finally:
        conn.close()


@contextmanager
def database(path: Path = DEFAULT_DB, *, readonly: bool = False) -> Iterator[sqlite3.Connection]:
    path = Path(path)
    mode = "ro" if readonly else "rw"
    conn = sqlite3.connect(path.resolve().as_uri() + f"?mode={mode}", uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        if version != latest_version():
            raise RuntimeError(f"Catalog schema is version {version}; run init for version {latest_version()}")
        yield conn
    finally:
        conn.close()


def configure_project(conn: sqlite3.Connection, project_id: str, label: str,
                      credential_env: str) -> None:
    if not project_id.strip() or not label.strip() or not ENV_NAME.fullmatch(credential_env):
        raise ValueError("Project ID, label, and a valid credential environment variable are required")
    now = utc_now()
    with conn:
        conn.execute(
            """INSERT INTO provider_projects
               (provider, project_id, label, credential_env, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(provider, project_id) DO UPDATE SET
                 label=excluded.label, credential_env=excluded.credential_env,
                 updated_at=excluded.updated_at""",
            (PROVIDER, project_id.strip(), label.strip(), credential_env, now, now),
        )


def project_by_id(conn: sqlite3.Connection, project_id: str) -> sqlite3.Row:
    row = conn.execute(
        "SELECT * FROM provider_projects WHERE provider=? AND project_id=?",
        (PROVIDER, project_id),
    ).fetchone()
    if row is None:
        raise ValueError("Unknown Google project; configure it before syncing")
    return row
