"""Version 1 to version 2 migration and rollback tests."""

from __future__ import annotations

from contextlib import redirect_stderr
from io import StringIO
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from master_voice_library.__main__ import main
from master_voice_library.db import (MIGRATIONS, configure_project, database,
                                     initialize_database)
from master_voice_library.providers import FixtureVoicesAdapter
from master_voice_library.sync import sync_project


def make_v1(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript((MIGRATIONS / "0001_initial.sql").read_text(encoding="utf-8"))
    configure_project(conn, "project-a", "Project A", "GEMINI_TEST")
    fixture = FixtureVoicesAdapter({"pages": [{"voices": [
        {"id": "voice_one", "type": "prompted", "display_name": "One"},
        {"id": "voice_two", "type": "replicated", "display_name": "Two"},
    ]}]})
    sync_project(conn, "project-a", fixture)
    conn.close()


def voice_rows(path: Path) -> list[tuple]:
    conn = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    try:
        return conn.execute("SELECT * FROM voices ORDER BY id").fetchall()
    finally:
        conn.close()


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "catalog.sqlite3"
        make_v1(self.path)

    def test_read_only_open_does_not_auto_migrate(self):
        with self.assertRaisesRegex(RuntimeError, "run init"):
            with database(self.path, readonly=True):
                pass
        with redirect_stderr(StringIO()):
            self.assertEqual(main(["--db", str(self.path), "voices", "summary"]), 1)
        conn = sqlite3.connect(self.path)
        self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], 1)
        conn.close()
        self.assertEqual(len(list(Path(self.temp.name).glob("*pre_migration*"))), 0)

    def test_additive_migration_creates_verified_backup_and_preserves_voices(self):
        before = voice_rows(self.path)
        version, backup = initialize_database(self.path)
        self.assertEqual(version, 2)
        self.assertIsNotNone(backup)
        self.assertEqual(voice_rows(self.path), before)
        self.assertEqual(voice_rows(backup), before)
        with database(self.path, readonly=True) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM character_scopes").fetchone()[0], 1)
            self.assertEqual(conn.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            self.assertEqual(conn.execute("PRAGMA foreign_key_check").fetchall(), [])
        _, second_backup = initialize_database(self.path)
        self.assertIsNone(second_backup)

    def test_failed_migration_rolls_back_and_leaves_backup(self):
        before = voice_rows(self.path)
        scripts = Path(self.temp.name) / "scripts"
        scripts.mkdir()
        (scripts / "0001_initial.sql").write_text(
            (MIGRATIONS / "0001_initial.sql").read_text(encoding="utf-8"), encoding="utf-8")
        (scripts / "0002_broken.sql").write_text(
            "BEGIN IMMEDIATE; CREATE TABLE half_created (id INTEGER); "
            "SELECT missing_column FROM voices; PRAGMA user_version=2; COMMIT;",
            encoding="utf-8")
        with patch("master_voice_library.db.MIGRATIONS", scripts):
            with self.assertRaises(sqlite3.Error):
                initialize_database(self.path)
        conn = sqlite3.connect(self.path)
        self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], 1)
        self.assertIsNone(conn.execute(
            "SELECT 1 FROM sqlite_master WHERE name='half_created'").fetchone())
        conn.close()
        self.assertEqual(voice_rows(self.path), before)
        self.assertEqual(len(list(Path(self.temp.name).glob("*pre_migration*"))), 1)


class ExistingCatalogMigrationTests(unittest.TestCase):
    @unittest.skipUnless(os.environ.get("M0C_V1_CATALOG"),
                         "Set M0C_V1_CATALOG to a version 1 catalog backup")
    def test_existing_16_voice_catalog_copy(self):
        source_path = Path(os.environ["M0C_V1_CATALOG"])
        with tempfile.TemporaryDirectory() as temp:
            copy_path = Path(temp) / "existing_catalog_copy.sqlite3"
            source = sqlite3.connect(source_path.resolve().as_uri() + "?mode=ro", uri=True)
            target = sqlite3.connect(copy_path)
            try:
                self.assertEqual(source.execute("PRAGMA user_version").fetchone()[0], 1)
                source.backup(target)
            finally:
                target.close()
                source.close()
            before = voice_rows(copy_path)
            self.assertEqual(len(before), 16)
            version, backup = initialize_database(copy_path)
            self.assertEqual(version, 2)
            self.assertEqual(voice_rows(copy_path), before)
            self.assertEqual(voice_rows(backup), before)
            with database(copy_path, readonly=True) as conn:
                self.assertEqual(conn.execute("PRAGMA integrity_check").fetchone()[0], "ok")
                self.assertEqual(conn.execute("PRAGMA foreign_key_check").fetchall(), [])


if __name__ == "__main__":
    unittest.main()
