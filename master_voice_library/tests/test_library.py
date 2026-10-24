"""Offline catalog, synchronization, and SDK adapter tests."""

from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from master_voice_library.__main__ import main
from master_voice_library.db import configure_project, database, initialize_database
from master_voice_library.providers import (
    FixtureVoicesAdapter, GoogleVoicesAdapter, VoiceMetadata, VoicePage,
)
from master_voice_library.sync import SyncError, sync_project


def voice(name: str, prompt: str = "A steady voice") -> dict:
    return {"id": f"voice_{name}", "type": "prompted", "display_name": name,
            "prompted": {"input": prompt}, "model": "gemini-3.8-flash-tts"}


def fixture(*pages: list[dict]) -> FixtureVoicesAdapter:
    return FixtureVoicesAdapter({"pages": [
        {"voices": values, "next_page_token": f"page_{index + 1}" if index + 1 < len(pages) else None}
        for index, values in enumerate(pages)
    ]})


class FailingProvider:
    def __init__(self):
        self.calls = 0

    def list_page(self, page_token, page_size):
        self.calls += 1
        if self.calls == 1:
            return VoicePage((VoiceMetadata("voice_new", "prompted"),), "next")
        raise RuntimeError("simulated network failure")

    def get_voice(self, voice_id):
        raise AssertionError("sync must not retrieve each voice")

    def create(self, **kwargs):
        raise AssertionError("provider write attempted")

    def delete(self, **kwargs):
        raise AssertionError("provider write attempted")


class LibraryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "catalog.sqlite3"
        initialize_database(self.path)
        self.db = database(self.path)
        self.conn = self.db.__enter__()
        self.addCleanup(lambda: self.db.__exit__(None, None, None))
        configure_project(self.conn, "project-a", "Project A", "GEMINI_A")

    def rows(self, project="project-a"):
        return self.conn.execute(
            """SELECT v.* FROM voices v JOIN provider_projects p
               ON p.id=v.provider_project_id WHERE p.project_id=?
               ORDER BY v.provider_voice_id""", (project,),
        ).fetchall()

    def test_first_import_and_repeat_keep_identity_without_duplicates(self):
        self.assertEqual(self.conn.execute("PRAGMA user_version").fetchone()[0], 2)
        first = sync_project(self.conn, "project-a", fixture([voice("one")]))
        original = self.rows()[0]
        second = sync_project(self.conn, "project-a", fixture([voice("one")]))
        self.assertEqual((first["voices"], second["voices"]), (1, 1))
        self.assertEqual(len(self.rows()), 1)
        self.assertEqual(self.rows()[0]["id"], original["id"])
        self.assertEqual(self.rows()[0]["prompted_input"], "A steady voice")
        self.assertEqual(self.conn.execute("SELECT count(*) FROM voice_lineage").fetchone()[0], 1)
        self.assertEqual(self.conn.execute("SELECT count(*) FROM provider_sync_runs WHERE status='complete'").fetchone()[0], 2)

    def test_pagination_and_duplicate_across_pages(self):
        result = sync_project(self.conn, "project-a", fixture([voice("one")], [voice("one"), voice("two")]))
        self.assertEqual((result["pages"], result["voices"], result["duplicates"]), (2, 2, 1))
        self.assertEqual([row["provider_voice_id"] for row in self.rows()], ["voice_one", "voice_two"])

    def test_separate_projects_with_same_provider_voice_id(self):
        configure_project(self.conn, "project-b", "Project B", "GEMINI_B")
        sync_project(self.conn, "project-a", fixture([voice("shared", "A prompt")]))
        sync_project(self.conn, "project-b", fixture([voice("shared", "B prompt")]))
        self.assertNotEqual(self.rows("project-a")[0]["id"], self.rows("project-b")[0]["id"])
        self.assertEqual(self.rows("project-a")[0]["prompted_input"], "A prompt")
        self.assertEqual(self.rows("project-b")[0]["prompted_input"], "B prompt")

    def test_failed_scan_preserves_voices_and_availability(self):
        sync_project(self.conn, "project-a", fixture([voice("old")]))
        original_id = self.rows()[0]["id"]
        with self.assertRaises(SyncError):
            sync_project(self.conn, "project-a", FailingProvider())
        self.assertEqual([(r["id"], r["availability"]) for r in self.rows()],
                         [(original_id, "available")])
        run = self.conn.execute("SELECT * FROM provider_sync_runs ORDER BY rowid DESC LIMIT 1").fetchone()
        self.assertEqual((run["status"], run["page_count"], run["error_class"]),
                         ("failed", 1, "RuntimeError"))

    def test_repeated_page_token_is_incomplete_and_preserves_catalog(self):
        sync_project(self.conn, "project-a", fixture([voice("old")]))

        class LoopingProvider:
            def list_page(self, page_token, page_size):
                return VoicePage((), "loop")

        with self.assertRaises(SyncError):
            sync_project(self.conn, "project-a", LoopingProvider())
        self.assertEqual(self.rows()[0]["availability"], "available")

    def test_missing_marked_only_after_complete_scan_and_history_retained(self):
        sync_project(self.conn, "project-a", fixture([voice("old"), voice("keep")]))
        old_id = next(row["id"] for row in self.rows() if row["provider_voice_id"] == "voice_old")
        # Simulate a future assignment table to verify that stable catalog IDs stay referenced.
        self.conn.execute("CREATE TABLE test_assignment (voice_id TEXT REFERENCES voices(id))")
        self.conn.execute("INSERT INTO test_assignment VALUES (?)", (old_id,))
        self.conn.commit()
        sync_project(self.conn, "project-a", fixture([voice("keep")]))
        old = next(row for row in self.rows() if row["provider_voice_id"] == "voice_old")
        self.assertEqual((old["id"], old["availability"]), (old_id, "unavailable"))
        self.assertEqual(self.conn.execute("SELECT voice_id FROM test_assignment").fetchone()[0], old_id)
        self.assertEqual(self.conn.execute("SELECT count(*) FROM voice_lineage WHERE child_voice_id=?", (old_id,)).fetchone()[0], 1)
        sync_project(self.conn, "project-a", fixture([voice("old"), voice("keep")]))
        self.assertEqual(next(r for r in self.rows() if r["id"] == old_id)["availability"], "available")

    def test_conflicting_duplicate_fails_without_catalog_changes(self):
        sync_project(self.conn, "project-a", fixture([voice("old")]))
        with self.assertRaises(SyncError):
            sync_project(self.conn, "project-a", fixture([voice("one", "first")], [voice("one", "second")]))
        self.assertEqual(len(self.rows()), 1)
        self.assertEqual(self.rows()[0]["availability"], "available")

    def test_fixture_cli_makes_no_network_client(self):
        sample = Path(__file__).resolve().parents[1] / "fixtures" / "sample_voices.json"
        output = StringIO()
        with patch("master_voice_library.__main__.GoogleVoicesAdapter", side_effect=AssertionError("network client opened")):
            with redirect_stdout(output):
                code = main(["--db", str(self.path), "sync", "--project-id", "project-a",
                             "--fixture", str(sample)])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output.getvalue())["voices"], 1)


class GoogleAdapterTests(unittest.TestCase):
    def test_sdk_adapter_only_uses_list_and_get(self):
        class ReadOnlyVoices:
            def __init__(self):
                self.calls = []

            def list(self, **kwargs):
                self.calls.append(("list", kwargs))
                return type("Response", (), {"voices": [voice("one")], "next_page_token": "next"})()

            def get(self, **kwargs):
                self.calls.append(("get", kwargs))
                return voice("one")

            def create(self, **kwargs):
                raise AssertionError("provider write attempted")

            def delete(self, **kwargs):
                raise AssertionError("provider write attempted")

        adapter = object.__new__(GoogleVoicesAdapter)
        fake = ReadOnlyVoices()
        adapter._client = type("Client", (), {"voices": fake})()
        page = adapter.list_page(None, 100)
        details = adapter.get_voice("voice_one")
        self.assertEqual((page.next_page_token, details.provider_voice_id), ("next", "voice_one"))
        self.assertEqual([name for name, _ in fake.calls], ["list", "get"])
        self.assertEqual(fake.calls[0][1]["type_"], ["prompted", "replicated"])


if __name__ == "__main__":
    unittest.main()
