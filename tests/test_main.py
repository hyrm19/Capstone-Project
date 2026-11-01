"""Exercise Flet controls and click handlers without opening a desktop window."""

import unittest
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

import flet as ft

import dashboard as app
from storage import StorageError, load_habits, save_habits

# Dashboard tests receive already-authenticated public profiles. Separate portal
# tests below exercise real registration, password checking, and session control.
TEST_MEMBERS = {
    "member-alex": {"id": "member-alex", "name": "Alex Morgan", "email": "alex@example.com", "color": "#2563EB"},
    "member-jamie": {"id": "member-jamie", "name": "Jamie Morgan", "email": "jamie@example.com", "color": "#7C3AED"},
    "member-sam": {"id": "member-sam", "name": "Sam Morgan", "email": "sam@example.com", "color": "#047857"},
}


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
        # Freeze only the app's clock, not the operating system clock. Tests for
        # "today" should keep the same results even when run around midnight.
        clock = patch("dashboard.datetime", wraps=datetime)
        self.clock = clock.start()
        self.clock.now.return_value = datetime(2026, 11, 1, 12, 0)
        self.addCleanup(clock.stop)
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "habits.json"
        # Redirect the interface's storage calls into the temporary folder.
        loader = patch("dashboard.load_habits", side_effect=lambda: load_habits(self.path))
        saver = patch("dashboard.save_habits", side_effect=lambda habits: save_habits(habits, self.path))
        self.loader = loader.start()
        self.saver = saver.start()
        self.addCleanup(loader.stop)
        self.addCleanup(saver.stop)

    def build_app(self, member_id="member-alex"):
        if hasattr(self, "session"):
            self.session["active"] = False
        session = {"active": True}
        self.session = session
        page = TestPage()
        app.build_dashboard(
            page, TEST_MEMBERS[member_id], TEST_MEMBERS,
            is_session_active=lambda: session["active"],
            on_logout=lambda e: session.update(active=False),
        )
        row = page.controls[-1]
        form = row.controls[0].content.controls
        self.value = next(control for control in form if isinstance(control, ft.TextField))
        activity_input = next(control for control in form if isinstance(control, ft.Column))
        self.name = activity_input.controls[1]
        self.name_error = activity_input.controls[2]
        self.button = next(control for control in form if isinstance(control, ft.Button))
        self.status = form[-2]
        self.assertFalse(any(isinstance(control, ft.Dropdown) for control in form))
        # Tabs contains a Column holding the labels followed by the page views.
        # Follow that structure instead of expecting the old standalone panel.
        self.tabs = row.controls[1]
        self.tab_bar, self.tab_views = self.tabs.content.controls
        self.timeline, self.personal, self.cloud = self.tab_views.controls
        self.empty, self.entries = self.timeline.content.controls[-2:]
        self.personal_summary = self.personal.content.controls[5]
        self.daily_progress = self.personal.content.controls[6]
        self.progress_date = self.daily_progress.controls[0]
        self.steps_label, self.steps_bar = self.daily_progress.controls[2:4]
        self.water_label, self.water_bar = self.daily_progress.controls[4:6]
        self.personal_empty, self.personal_entries = self.personal.content.controls[-2:]
        self.cloud_health = self.cloud.content.controls[5]
        self.cloud_summary = self.cloud.content.controls[6]

    def enter_activity(self, name="Running", value="2.5"):
        self.name.value = name
        self.value.value = value
        self.button.on_click(None)

    def select_member(self, member_id):
        # Simulate logging out then opening a new authenticated dashboard, not
        # an editable member selector. Portal tests verify actual login/logout.
        self.build_app(member_id)

    def card_name(self, card):
        # A card is a Row containing a badge and a Column of activity details.
        return card.content.controls[1].controls[1].value

    def card_value(self, card):
        return card.content.controls[1].controls[2].value

    def test_daily_progress_updates_after_saves_and_member_changes(self):
        self.build_app()
        self.assertEqual(self.steps_bar.value, 0)
        self.assertEqual(self.water_bar.value, 0)
        self.enter_activity("Steps", "2000")
        self.enter_activity("Water Intake", "3")
        self.assertEqual(self.steps_bar.value, 0.25)
        self.assertEqual(self.water_bar.value, 0.375)
        self.assertEqual(self.steps_label.value, "Steps: 2,000 / 8,000 (25%)")
        self.assertEqual(self.water_label.value, "Water: 3 / 8 cups (37.5%)")
        self.select_member("member-jamie")
        self.assertEqual(self.steps_bar.value, 0)
        self.assertEqual(self.water_bar.value, 0)
        self.enter_activity("Water Intake", "1.5")
        self.assertEqual(self.water_bar.value, 1.5 / 8)
        self.select_member("member-alex")
        self.assertEqual(self.water_bar.value, 0.375)
        # A new launch derives the same totals from saved entries, not counters.
        self.build_app()
        self.assertEqual(self.steps_bar.value, 0.25)
        self.assertEqual(self.water_bar.value, 0.375)

    def test_daily_progress_caps_bars_but_preserves_above_goal_totals(self):
        self.build_app()
        self.enter_activity("Steps", "8000")
        self.enter_activity("Steps", "4000")
        self.enter_activity("Water Intake", "10")
        self.assertEqual(self.steps_bar.value, 1)
        self.assertEqual(self.water_bar.value, 1)
        self.assertEqual(self.steps_label.value, "Steps: 12,000 / 8,000 (150%)")
        self.assertEqual(self.water_label.value, "Water: 10 / 8 cups (125%)")

    def test_daily_progress_refreshes_date_on_tab_navigation(self):
        self.build_app()
        self.enter_activity("Steps", "2000")
        self.clock.now.return_value = datetime(2026, 11, 2, 0, 1)
        self.tabs.selected_index = 1
        self.tabs.on_change(None)
        self.assertEqual(self.steps_bar.value, 0)
        self.assertIn("02 Nov 2026", self.progress_date.value)
        # History is not deleted just because the day changed.
        self.assertEqual(len(self.personal_entries.controls), 1)

    def test_failed_save_does_not_change_daily_progress(self):
        self.build_app()
        self.enter_activity("Water Intake", "2")
        with patch("dashboard.save_habits", side_effect=StorageError("Disk full")):
            self.enter_activity("Water Intake", "3")
        self.assertEqual(self.water_bar.value, 0.25)
        self.assertEqual(self.water_label.value, "Water: 2 / 8 cups (25%)")

    def test_old_or_unitless_steps_are_not_included_in_daily_progress(self):
        records = [
            {"name": "Steps", "value": 5000, "logged_at": datetime(2026, 10, 31),
             "member_id": "member-alex", "unit": "steps"},
            {"name": "Steps", "value": 6000, "logged_at": datetime(2026, 11, 1),
             "member_id": "member-alex"},
        ]
        save_habits(records, self.path)
        self.build_app()
        self.assertEqual(self.steps_bar.value, 0)
        self.assertEqual(len(self.personal_entries.controls), 2)

    def test_autocomplete_suggestions_and_selection_update_units(self):
        self.build_app()
        self.assertIsInstance(self.name, ft.AutoComplete)
        self.assertEqual([s.value for s in self.name.suggestions], list(app.ACTIVITY_UNITS))
        for suggestion in self.name.suggestions:
            with self.subTest(activity=suggestion.value):
                self.name.on_select(SimpleNamespace(selection=suggestion))
                self.assertEqual(self.name.value, suggestion.value)
                self.assertEqual(self.value.label, f"Value ({app.ACTIVITY_UNITS[suggestion.value]})")

    def test_typed_activity_changes_unit_and_rejects_unknown_names(self):
        self.build_app()
        self.name.value = " running "
        self.name.on_change(None)
        self.assertEqual(self.value.label, "Value (km)")
        self.name.value = "yoga"
        self.name.on_change(None)
        self.assertEqual(self.value.label, "Value (minutes)")
        self.enter_activity("yoga", "15.5")
        self.assertEqual(self.card_name(self.entries.controls[0]), "Yoga")
        self.assertEqual(self.card_value(self.entries.controls[0]), "Value: 15.5 minutes")
        self.assertEqual(self.value.label, "Value (choose an activity first)")
        self.enter_activity("An unknown sport", "5")
        self.assertTrue(self.name_error.visible)
        self.assertEqual(len(load_habits(self.path)), 1)

    def test_each_activity_saves_and_displays_its_unit(self):
        self.build_app()
        for name, unit in app.ACTIVITY_UNITS.items():
            with self.subTest(name=name):
                self.enter_activity(name, "5")
                self.assertEqual(self.card_value(self.entries.controls[0]), f"Value: 5 {unit}")
                self.assertEqual(self.card_value(self.personal_entries.controls[0]), f"Value: 5 {unit}")
                self.assertEqual(load_habits(self.path)[-1]["unit"], unit)
        # A fresh page must display the stored unit, not lose it on restart.
        self.build_app()
        self.assertEqual(self.card_value(self.entries.controls[0]), "Value: 5 steps")

    def test_steps_require_whole_numbers_but_cups_allow_fractions(self):
        self.build_app()
        self.enter_activity("Steps", "1000.5")
        self.assertIn("whole number", self.value.error_text)
        self.saver.assert_not_called()
        self.enter_activity("Steps", "1000")
        self.enter_activity("Water Intake", "1.5")
        self.assertEqual(len(load_habits(self.path)), 2)

    def test_legacy_units_remain_unspecified_after_new_save(self):
        # Even a standard old name is ambiguous: old Running could mean minutes.
        legacy = {"name": "Running", "value": 5, "logged_at": datetime(2026, 11, 1)}
        save_habits([legacy], self.path)
        self.build_app()
        self.assertIn("unit unspecified", self.card_value(self.entries.controls[0]))
        self.enter_activity("Running", "2.5")
        self.assertEqual(self.card_value(self.entries.controls[0]), "Value: 2.5 km")
        self.assertNotIn("unit", load_habits(self.path)[0])

    def test_saved_entries_survive_reopening_newest_first(self):
        self.build_app()
        self.enter_activity()
        self.enter_activity("Yoga", "20")
        self.assertEqual(self.name.value, "")
        self.assertEqual(self.value.value, "")
        # Rebuilding the page simulates a new launch that reads the JSON file.
        self.build_app()
        names = [self.card_name(card) for card in self.entries.controls]
        self.assertEqual(names, ["Yoga", "Running"])
        self.assertTrue(self.entries.visible)
        self.assertFalse(self.empty.visible)

    def test_tab_controller_has_three_distinct_matching_views(self):
        self.build_app()
        self.assertIsInstance(self.tabs, ft.Tabs)
        self.assertIsInstance(self.tab_bar, ft.TabBar)
        self.assertIsInstance(self.tab_views, ft.TabBarView)
        self.assertEqual(self.tabs.length, 3)
        self.assertEqual(len(self.tab_bar.tabs), self.tabs.length)
        self.assertEqual(len(self.tab_views.controls), self.tabs.length)
        self.assertEqual(
            [tab.label for tab in self.tab_bar.tabs],
            ["Family Timeline", "Personal", "Cloud Status"],
        )
        self.assertEqual(len({id(view) for view in self.tab_views.controls}), 3)
        self.assertIn("not connected", self.cloud.content.controls[1].value)
        self.assertIn("alex@example.com", self.personal.content.controls[2].value)

    def test_save_updates_other_tabs_without_resetting_selection(self):
        self.build_app()
        # Simulate the controller's selected index while viewing Cloud Status.
        # Native click/animation behavior still needs a visual desktop check.
        self.tabs.selected_index = 2
        self.enter_activity()
        self.assertEqual(self.tabs.selected_index, 2)
        self.assertEqual(self.personal_summary.value, "Activities for Alex Morgan: 1")
        self.assertEqual(self.cloud_summary.value, "Activities loaded on this device: 1")
        self.assertIn("saved successfully", self.cloud_health.value)
        self.assertEqual(len(self.entries.controls), 1)

    def test_members_have_distinct_badges_and_personal_histories(self):
        self.build_app()
        self.enter_activity("Running", "5")
        self.select_member("member-jamie")
        self.assertTrue(self.personal_empty.visible)
        self.assertFalse(self.personal_entries.visible)
        self.assertTrue(self.daily_progress.visible)
        self.enter_activity("Yoga", "20")
        self.assertEqual(len(self.entries.controls), 2)
        self.assertEqual([self.card_name(c) for c in self.personal_entries.controls], ["Yoga"])
        jamie_badge = self.entries.controls[0].content.controls[0]
        alex_badge = self.entries.controls[1].content.controls[0]
        self.assertIsInstance(jamie_badge, ft.CircleAvatar)
        self.assertEqual(jamie_badge.content.value, "JM")
        self.assertEqual(alex_badge.content.value, "AM")
        self.assertNotEqual(jamie_badge.bgcolor, alex_badge.bgcolor)
        # Separate controls are required even when both tabs show the same entry.
        self.assertIsNot(self.entries.controls[0], self.personal_entries.controls[0])
        self.select_member("member-alex")
        self.assertEqual([self.card_name(c) for c in self.personal_entries.controls], ["Running"])
        self.assertEqual(len(self.entries.controls), 2)
        self.assertEqual(self.personal.content.controls[1].controls[1].value, "Alex Morgan")

    def test_member_ownership_survives_reopening_and_does_not_change_on_selection(self):
        self.build_app()
        self.select_member("member-sam")
        self.enter_activity()
        original = self.path.read_bytes()
        self.select_member("member-alex")
        self.assertEqual(self.path.read_bytes(), original)
        self.build_app()
        self.assertEqual(load_habits(self.path)[0]["member_id"], "member-sam")
        self.assertTrue(self.personal_empty.visible)
        self.select_member("member-sam")
        self.assertEqual(len(self.personal_entries.controls), 1)
        self.assertEqual(self.entries.controls[0].content.controls[0].content.value, "SM")

    def test_legacy_and_unknown_owners_are_not_assigned_to_demo_members(self):
        legacy = {"name": "Old activity", "value": 5, "logged_at": datetime(2026, 11, 1)}
        unknown = {**legacy, "name": "Unknown activity", "member_id": "retired-member"}
        save_habits([legacy, unknown], self.path)
        self.build_app()
        self.assertEqual(self.entries.controls[1].content.controls[1].controls[0].value, "Unassigned")
        self.assertEqual(self.entries.controls[0].content.controls[1].controls[0].value, "Unknown member")
        self.assertEqual(self.entries.controls[1].content.controls[0].content.value, "?")
        for member_id in TEST_MEMBERS:
            self.select_member(member_id)
            self.assertEqual(len(self.personal_entries.controls), 0)
        self.enter_activity()
        loaded = load_habits(self.path)
        self.assertNotIn("member_id", loaded[0])
        self.assertEqual(loaded[1]["member_id"], "retired-member")

    def test_ended_session_cannot_save_from_old_button(self):
        self.build_app()
        self.session["active"] = False
        self.enter_activity()
        self.saver.assert_not_called()

    def test_invalid_inputs_do_not_write_a_file(self):
        self.build_app()
        for value in ["", "abc", "0", "-1", "nan", "inf"]:
            self.enter_activity(value=value)
            self.assertIsNotNone(self.value.error_text)
        self.enter_activity(name="   ", value="5")
        self.assertTrue(self.name_error.visible)
        self.saver.assert_not_called()
        self.assertFalse(self.path.exists())

    def test_save_failure_preserves_form_and_allows_retry(self):
        self.build_app()
        with patch("dashboard.save_habits", side_effect=StorageError("Disk full")):
            self.enter_activity()
        self.assertEqual(self.name.value, "Running")
        self.assertEqual(self.value.value, "2.5")
        self.assertEqual(len(self.entries.controls), 0)
        self.assertIn("not saved", self.status.value)
        self.assertIn("Last save failed", self.cloud_health.value)
        self.assertEqual(self.cloud_summary.value, "Activities loaded on this device: 0")
        self.button.on_click(None)
        self.assertEqual(len(load_habits(self.path)), 1)
        self.assertIn("saved successfully", self.cloud_health.value)

    def test_corrupt_history_blocks_saving_and_stays_untouched(self):
        self.path.write_text("broken history", encoding="utf-8")
        self.build_app()
        self.assertTrue(self.button.disabled)
        self.assertTrue(self.status.visible)
        self.assertFalse(self.empty.visible)
        self.assertIn("unavailable", self.cloud_summary.value)
        self.assertIn("needs attention", self.cloud_health.value)
        self.assertFalse(self.personal_entries.visible)
        self.assertFalse(self.daily_progress.visible)
        self.assertTrue(self.timeline.content.controls[2].visible)
        self.assertTrue(self.cloud.content.controls[-1].visible)
        self.enter_activity()
        self.saver.assert_not_called()
        self.assertEqual(self.path.read_text(encoding="utf-8"), "broken history")
