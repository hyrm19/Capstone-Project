"""Test persistence using temporary folders, never the user's actual history."""

import json
import unittest
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from storage import StorageError, load_habits, save_habits


class StorageTests(unittest.TestCase):
    def setUp(self):
        # Each test gets a fresh folder that is automatically cleaned up.
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "data" / "habits.json"
        self.habit = {
            "name": "Swimming 🏊",
            "value": 2.5,
            "logged_at": datetime(2026, 11, 1, 14, 30, 15, 123456),
        }

    def test_missing_file_is_first_run(self):
        self.assertEqual(load_habits(self.path), [])
        self.assertFalse(self.path.exists())

    def test_round_trip_restores_values_and_datetime(self):
        save_habits([self.habit], self.path)
        self.assertEqual(load_habits(self.path), [self.habit])
        stored = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(stored[0]["logged_at"], self.habit["logged_at"].isoformat())

    def test_empty_history_is_valid(self):
        save_habits([], self.path)
        self.assertEqual(load_habits(self.path), [])

    def test_corrupt_history_is_reported_and_untouched(self):
        self.path.parent.mkdir()
        good = {**self.habit, "logged_at": self.habit["logged_at"].isoformat()}
        bad_records = [
            "not json", "", "{}", "[null]", "[{}]",
            json.dumps([{**good, "name": " "}]),
            json.dumps([{**good, "value": True}]),
            json.dumps([{**good, "value": -1}]),
            json.dumps([{**good, "value": "5"}]),
            json.dumps([{**good, "value": float("nan")}]),
            json.dumps([{**good, "value": float("inf")}]),
            json.dumps([{**good, "logged_at": "yesterday"}]),
            # A bad second record must not silently discard part of the history.
            json.dumps([good, {}]),
        ]
        for text in bad_records:
            with self.subTest(text=text):
                self.path.write_text(text, encoding="utf-8")
                with self.assertRaises(StorageError):
                    load_habits(self.path)
                self.assertEqual(self.path.read_text(encoding="utf-8"), text)

    def test_unreadable_file_is_not_treated_as_empty(self):
        with patch.object(Path, "read_text", side_effect=PermissionError("Access denied")):
            with self.assertRaises(StorageError):
                load_habits(self.path)

    def test_failed_replacement_preserves_old_history_and_cleans_temp_file(self):
        save_habits([self.habit], self.path)
        original = self.path.read_bytes()
        # Simulate a disk/permission problem at the final replacement step.
        with patch("storage.os.replace", side_effect=PermissionError("Access denied")):
            with self.assertRaises(StorageError):
                save_habits([self.habit, self.habit], self.path)
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])

    def test_invalid_save_preserves_old_history(self):
        save_habits([self.habit], self.path)
        original = self.path.read_bytes()
        with self.assertRaises(StorageError):
            save_habits([{**self.habit, "value": 0}], self.path)
        self.assertEqual(self.path.read_bytes(), original)
