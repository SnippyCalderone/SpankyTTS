"""Offline character management, preference, and catalog diagnostics tests."""

from __future__ import annotations

from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from master_voice_library.__main__ import main
from master_voice_library.catalog import (assignment_history, catalog_summary,
                                          list_voices, voice_warnings)
from master_voice_library.db import configure_project, database, initialize_database
from master_voice_library.management import (DEFAULT_SCOPE_ID, annotate_voice,
    archive_assignment, assign_voice, create_character, create_scope,
    max_active_assignments, prefer_assignment, restore_assignment,
    set_max_active_assignments, set_tag, update_character)
from master_voice_library.providers import FixtureVoicesAdapter
from master_voice_library.sync import sync_project


def provider(*names: str, expiry: str | None = None, description: str = "Provider description"):
    return FixtureVoicesAdapter({"pages": [{"voices": [
        {"id": f"voice_{name}", "type": "prompted", "display_name": name,
         "description": description, "expire_time": expiry,
         "prompted": {"input": "Provider prompt"}}
        for name in names
    ]}]})


class ManagementTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "catalog.sqlite3"
        initialize_database(self.path)
        self.db = database(self.path)
        self.conn = self.db.__enter__()
        self.addCleanup(lambda: self.db.__exit__(None, None, None))
        configure_project(self.conn, "project-a", "Project A", "GEMINI_TEST")
        sync_project(self.conn, "project-a", provider("one", "two", "three", "four"))
        self.character_id = create_character(self.conn, DEFAULT_SCOPE_ID, "Mara")
        self.voices = {row["provider_voice_id"]: row["id"] for row in
                       self.conn.execute("SELECT provider_voice_id, id FROM voices")}

    def test_limit_and_exactly_one_preferred(self):
        one = assign_voice(self.conn, self.character_id, self.voices["voice_one"], role="dialogue")
        two = assign_voice(self.conn, self.character_id, self.voices["voice_two"], slot=3)
        three = assign_voice(self.conn, self.character_id, self.voices["voice_three"])
        active = assignment_history(self.conn, self.character_id, active_only=True)
        self.assertEqual({item["slot_number"] for item in active}, {1, 2, 3})
        self.assertEqual([item["id"] for item in active if item["is_preferred"]], [one])
        self.assertEqual(next(item for item in active if item["id"] == one)["role"], "dialogue")
        with self.assertRaises(ValueError):
            assign_voice(self.conn, self.character_id, self.voices["voice_four"])
        prefer_assignment(self.conn, two)
        active = assignment_history(self.conn, self.character_id, active_only=True)
        self.assertEqual([item["id"] for item in active if item["is_preferred"]], [two])
        self.assertEqual(len(active), 3)
        self.assertNotEqual(three, two)

    def test_configurable_limit_rejects_existing_higher_slot(self):
        one = assign_voice(self.conn, self.character_id, self.voices["voice_one"], slot=3)
        with self.assertRaises(ValueError):
            set_max_active_assignments(self.conn, 2)
        self.assertEqual(max_active_assignments(self.conn), 3)
        archive_assignment(self.conn, one)
        set_max_active_assignments(self.conn, 2)
        self.assertEqual(max_active_assignments(self.conn), 2)
        with self.assertRaises(ValueError):
            assign_voice(self.conn, self.character_id, self.voices["voice_two"], slot=3)

    def test_archive_preferred_requires_explicit_successor_and_restore_keeps_history(self):
        first = assign_voice(self.conn, self.character_id, self.voices["voice_one"])
        second = assign_voice(self.conn, self.character_id, self.voices["voice_two"])
        with self.assertRaises(ValueError):
            archive_assignment(self.conn, first)
        self.assertEqual(len(assignment_history(self.conn, self.character_id, active_only=True)), 2)
        archive_assignment(self.conn, first, next_preferred_id=second)
        restored = restore_assignment(self.conn, first)
        history = assignment_history(self.conn, self.character_id)
        self.assertEqual(len(history), 3)
        self.assertIsNotNone(next(item for item in history if item["id"] == first)["archived_at"])
        self.assertEqual(next(item for item in history if item["id"] == restored)["restored_from_id"], first)
        self.assertEqual([item["id"] for item in history if item["is_preferred"]], [second])
        with self.assertRaises(ValueError):
            restore_assignment(self.conn, first)

    def test_restore_into_empty_character_becomes_preferred(self):
        first = assign_voice(self.conn, self.character_id, self.voices["voice_one"])
        archive_assignment(self.conn, first)
        restored = restore_assignment(self.conn, first)
        active = assignment_history(self.conn, self.character_id, active_only=True)
        self.assertEqual([(item["id"], item["is_preferred"]) for item in active], [(restored, 1)])

    def test_scope_isolation_and_character_metadata(self):
        one = create_scope(self.conn, "series", "north", "North series")
        two = create_scope(self.conn, "series", "south", "South series")
        north = create_character(self.conn, one, "Ari")
        south = create_character(self.conn, two, "Ari")
        self.assertNotEqual(north, south)
        with self.assertRaises(Exception):
            create_character(self.conn, one, " ari ")
        update_character(self.conn, north, name="Aria", description="Lead", notes="Local note")
        row = self.conn.execute("SELECT name, description, notes FROM characters WHERE id=?", (north,)).fetchone()
        self.assertEqual(tuple(row), ("Aria", "Lead", "Local note"))

    def test_local_metadata_tags_and_assignments_survive_sync_and_missing_voice(self):
        voice_id = self.voices["voice_one"]
        annotate_voice(self.conn, voice_id, name="My Mara voice",
                       description="Local description", notes="Keep this")
        set_tag(self.conn, "voice", voice_id, "Warm", attached=True)
        set_tag(self.conn, "character", self.character_id, "Main cast", attached=True)
        assignment_id = assign_voice(self.conn, self.character_id, voice_id)
        sync_project(self.conn, "project-a", provider("one", "two", "three", "four",
                                                     description="Provider changed"))
        row = self.conn.execute(
            """SELECT v.id, v.description, a.user_name, a.user_description, a.notes
               FROM voices v JOIN voice_annotations a ON a.voice_id=v.id WHERE v.id=?""",
            (voice_id,),
        ).fetchone()
        self.assertEqual(tuple(row), (voice_id, "Provider changed", "My Mara voice",
                                      "Local description", "Keep this"))
        sync_project(self.conn, "project-a", provider("two", "three", "four"))
        self.assertEqual(self.conn.execute("SELECT availability FROM voices WHERE id=?", (voice_id,)).fetchone()[0],
                         "unavailable")
        active = assignment_history(self.conn, self.character_id, active_only=True)
        self.assertEqual((active[0]["id"], active[0]["is_preferred"]), (assignment_id, 1))
        self.assertIn("unavailable", active[0]["warnings"])
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM voice_tags WHERE voice_id=?", (voice_id,)).fetchone()[0], 1)

    def test_expiration_warning_does_not_switch_preferred(self):
        first = assign_voice(self.conn, self.character_id, self.voices["voice_one"])
        assign_voice(self.conn, self.character_id, self.voices["voice_two"])
        past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        sync_project(self.conn, "project-a", provider("one", "two", "three", "four", expiry=past))
        active = assignment_history(self.conn, self.character_id, active_only=True)
        self.assertEqual([item["id"] for item in active if item["is_preferred"]], [first])
        self.assertIn("reported_expiration_passed", active[0]["warnings"])

    def test_warning_boundaries_and_summary(self):
        now = datetime(2026, 10, 23, tzinfo=timezone.utc)
        self.assertEqual(voice_warnings("available", (now + timedelta(days=31)).isoformat(), now=now), [])
        self.assertIn("expires_within_30_days",
                      voice_warnings("available", (now + timedelta(days=30)).isoformat(), now=now))
        self.assertIn("reported_expiration_passed",
                      voice_warnings("available", now.isoformat(), now=now))
        self.assertIn("expiration_unparseable", voice_warnings("available", "bad", now=now))
        self.assertIn("4 total", catalog_summary(self.conn, "project-a"))
        self.assertEqual(len(list_voices(self.conn, "project-a")), 4)

    def test_management_cli_never_opens_google_client(self):
        output = StringIO()
        commands = [
            ["voices", "summary"],
            ["voices", "annotate", "--catalog-id", self.voices["voice_one"], "--name", "Custom"],
            ["characters", "add", "--name", "Second"],
            ["tags", "add", "--name", "Warm"],
            ["assignments", "add", "--character-id", self.character_id,
             "--catalog-id", self.voices["voice_one"]],
            ["assignments", "list", "--character-id", self.character_id],
        ]
        with patch("master_voice_library.__main__.GoogleVoicesAdapter",
                   side_effect=AssertionError("Google client opened")):
            for command in commands:
                with redirect_stdout(output):
                    self.assertEqual(main(["--db", str(self.path), *command]), 0)
        self.assertIn("Custom", json.dumps(list_voices(self.conn, "project-a")))

    def test_cli_archive_restore_tags_and_history(self):
        first = assign_voice(self.conn, self.character_id, self.voices["voice_one"])
        second = assign_voice(self.conn, self.character_id, self.voices["voice_two"])
        commands = [
            ["voices", "tag", "add", "--catalog-id", self.voices["voice_one"], "--tag", "Warm"],
            ["characters", "tag", "add", "--character-id", self.character_id, "--tag", "Lead"],
            ["assignments", "archive", "--assignment-id", first, "--next-preferred", second],
            ["assignments", "restore", "--assignment-id", first],
            ["assignments", "history", "--character-id", self.character_id],
        ]
        with patch("master_voice_library.__main__.GoogleVoicesAdapter",
                   side_effect=AssertionError("Google client opened")):
            for command in commands:
                with redirect_stdout(StringIO()):
                    self.assertEqual(main(["--db", str(self.path), *command]), 0)
        self.assertEqual(len(assignment_history(self.conn, self.character_id)), 3)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM voice_tags").fetchone()[0], 1)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM character_tags").fetchone()[0], 1)


if __name__ == "__main__":
    unittest.main()
