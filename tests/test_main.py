"""Exercise Flet controls and click handlers without opening a desktop window."""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import flet as ft

import main as app
from storage import StorageError, load_habits, save_habits


class TestPage:
    # main() only needs these methods and ordinary page attributes in these tests.
    # A lightweight substitute lets tests inspect controls without a running UI.
    def __init__(self):
        self.controls = []

    def add(self, *controls):
        self.controls.extend(controls)

    def update(self):
        pass


class AppTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "habits.json"
        # Redirect the interface's storage calls into the temporary folder.
        loader = patch("main.load_habits", side_effect=lambda: load_habits(self.path))
        saver = patch("main.save_habits", side_effect=lambda habits: save_habits(habits, self.path))
        self.loader = loader.start()
        self.saver = saver.start()
        self.addCleanup(loader.stop)
        self.addCleanup(saver.stop)

    def build_app(self):
        page = TestPage()
        app.main(page)
        row = page.controls[-1]
        form = row.controls[0].content.controls
        self.name, self.value = [control for control in form if isinstance(control, ft.TextField)]
        self.button = next(control for control in form if isinstance(control, ft.Button))
        self.status = form[4]
        self.empty, self.entries = row.controls[1].controls[1].content.controls

    def enter_activity(self, name="Running", value="2.5"):
        self.name.value = name
        self.value.value = value
        self.button.on_click(None)

    def test_saved_entries_survive_reopening_newest_first(self):
        self.build_app()
        self.enter_activity()
        self.enter_activity("Yoga", "20")
        self.assertEqual(self.name.value, "")
        self.assertEqual(self.value.value, "")
        # Rebuilding the page simulates a new launch that reads the JSON file.
        self.build_app()
        names = [card.content.controls[0].value for card in self.entries.controls]
        self.assertEqual(names, ["Yoga", "Running"])
        self.assertTrue(self.entries.visible)
        self.assertFalse(self.empty.visible)

    def test_invalid_inputs_do_not_write_a_file(self):
        self.build_app()
        for value in ["", "abc", "0", "-1", "nan", "inf"]:
            self.enter_activity(value=value)
            self.assertIsNotNone(self.value.error_text)
        self.enter_activity(name="   ", value="5")
        self.assertIsNotNone(self.name.error_text)
        self.saver.assert_not_called()
        self.assertFalse(self.path.exists())

    def test_save_failure_preserves_form_and_allows_retry(self):
        self.build_app()
        with patch("main.save_habits", side_effect=StorageError("Disk full")):
            self.enter_activity()
        self.assertEqual(self.name.value, "Running")
        self.assertEqual(self.value.value, "2.5")
        self.assertEqual(len(self.entries.controls), 0)
        self.assertIn("not saved", self.status.value)
        self.button.on_click(None)
        self.assertEqual(len(load_habits(self.path)), 1)

    def test_corrupt_history_blocks_saving_and_stays_untouched(self):
        self.path.write_text("broken history", encoding="utf-8")
        self.build_app()
        self.assertTrue(self.button.disabled)
        self.assertTrue(self.status.visible)
        self.assertFalse(self.empty.visible)
        self.enter_activity()
        self.saver.assert_not_called()
        self.assertEqual(self.path.read_text(encoding="utf-8"), "broken history")
