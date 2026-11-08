"""Cloud-only dashboard tests. All HTTP/data operations are mocked."""

import asyncio
import unittest
from datetime import datetime
from unittest.mock import patch

import dashboard
from airtable_api import AirtableError
from ui_helpers import TestPage, find


MEMBER = {"id": "member-alex", "name": "Alex Morgan", "email": "alex@example.com", "color": "#2563EB"}


class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.session = {"active": True}
        self.page = TestPage()
        patches = [
            patch("dashboard.get_destination", return_value={"base_id": "appTest", "table": "Habits"}),
            patch("dashboard.download_records", return_value=[]),
            patch("dashboard.upload_batch", side_effect=lambda batch, names, target: {batch[0]["log_id"]: "rec123"}),
            patch("dashboard.check_connection", return_value="Airtable connected."),
            patch("dashboard.datetime", wraps=datetime),
        ]
        self.destination, self.downloader, self.uploader, self.checker, self.clock = [p.start() for p in patches]
        for p in patches:
            self.addCleanup(p.stop)
        self.clock.now.return_value = datetime(2026, 11, 1, 12)

    def get(self, label):
        return find(self.page, label)

    def build(self, load=True):
        dashboard.build_dashboard(
            self.page, MEMBER, {MEMBER["id"]: MEMBER},
            is_session_active=lambda: self.session["active"],
            on_logout=lambda e: self.session.update(active=False),
        )
        if load:
            asyncio.run(self.page.tasks.pop(0)())

    def record(self, log_id="cloud123", **changes):
        fields = {"LogID": log_id, "MemberID": "member-alex", "MemberName": "Alex Morgan",
                  "Activity": "Steps", "Value": 2000, "Unit": "steps", "LoggedAt": "2026-11-01T10:00:00"}
        fields.update(changes)
        return {"id": "rec" + log_id, "fields": fields}

    def save(self, name="Running", value="2.5"):
        self.get("activity_name").value = name
        self.get("activity_value").value = value
        asyncio.run(self.get("save_log").on_click(None))

    def refresh(self):
        asyncio.run(self.get("refresh_airtable_history").on_click(None))

    def test_login_schedules_cloud_load_and_prevents_save_until_loaded(self):
        self.build(load=False)
        self.assertEqual(len(self.page.tasks), 1)
        self.assertTrue(self.get("save_log").disabled)
        self.assertFalse(self.get("progress_panel").visible)
        self.save()
        self.uploader.assert_not_called()
        asyncio.run(self.page.tasks.pop(0)())
        self.assertFalse(self.get("save_log").disabled)
        self.assertEqual(self.get("cloud_history_summary").value, "Cloud activities loaded: 0")

    def test_confirmed_save_goes_directly_to_cloud_then_updates_views(self):
        self.build()
        with patch("pathlib.Path.write_text", side_effect=AssertionError("No local file writes")):
            self.save("Steps", "2000")
        self.uploader.assert_called_once()
        habit = self.uploader.call_args.args[0][0]
        self.assertEqual(habit["member_id"], "member-alex")
        self.assertIn("log_id", habit)
        self.assertEqual(len(self.get("timeline_list").controls), 1)
        self.assertEqual(self.get("steps_bar").value, 0.25)
        self.assertEqual(self.get("activity_value").value, "")
        self.assertEqual(self.get("save_status").value, "Saved to Airtable.")
        self.assertEqual(self.get("save_log").height, 46)

    def test_failed_save_keeps_input_and_retries_same_log_id(self):
        self.build()
        self.uploader.side_effect = AirtableError("Connection lost")
        self.save("Water Intake", "3")
        first_id = self.uploader.call_args.args[0][0]["log_id"]
        self.assertEqual(self.get("activity_value").value, "3")
        self.assertEqual(len(self.get("timeline_list").controls), 0)
        self.assertEqual(self.get("water_bar").value, 0)
        self.assertIn("not confirmed", self.get("save_status").value)
        self.uploader.side_effect = lambda batch, names, target: {batch[0]["log_id"]: "rec123"}
        asyncio.run(self.get("save_log").on_click(None))
        self.assertEqual(self.uploader.call_args.args[0][0]["log_id"], first_id)
        self.assertEqual(self.get("water_bar").value, 3 / 8)

    def test_invalid_input_never_writes_to_cloud(self):
        self.build()
        for value in ["", "abc", "0", "-1", "nan", "inf", "1000.5"]:
            self.save("Steps", value)
            self.assertIsNotNone(self.get("activity_value").error_text)
        self.save("Unknown sport", "5")
        self.assertTrue(self.get("activity_name_error").visible)
        self.uploader.assert_not_called()

    def test_cloud_rows_update_personal_progress_and_unknown_member_badges(self):
        self.downloader.return_value = [
            self.record(), self.record("water", Activity="Water Intake", Value=3, Unit="cups"),
            self.record("remote", MemberID="member-robin", MemberName="Robin Lee"),
        ]
        self.build()
        self.assertEqual(len(self.get("timeline_list").controls), 3)
        self.assertEqual(len(self.get("personal_list").controls), 2)
        self.assertEqual(self.get("steps_bar").value, 0.25)
        self.assertEqual(self.get("water_bar").value, 0.375)
        self.assertEqual(self.get("timeline_list").controls[0].content.controls[0].content.value, "RL")

    def test_refresh_reflects_cloud_edits_and_deletions_without_duplication(self):
        self.downloader.return_value = [self.record()]
        self.build()
        self.downloader.return_value = [self.record(Value=4000)]
        self.refresh()
        self.assertEqual(len(self.get("timeline_list").controls), 1)
        self.assertEqual(self.get("steps_bar").value, 0.5)
        self.refresh()
        self.assertEqual(len(self.get("timeline_list").controls), 1)
        self.downloader.return_value = []
        self.refresh()
        self.assertEqual(len(self.get("timeline_list").controls), 0)
        self.assertEqual(self.get("steps_bar").value, 0)

    def test_failed_refresh_keeps_last_in_memory_view_but_no_offline_startup(self):
        self.downloader.return_value = [self.record()]
        self.build()
        self.downloader.side_effect = AirtableError("Offline")
        self.refresh()
        self.assertEqual(len(self.get("timeline_list").controls), 1)
        self.assertIn("Offline", self.get("cloud_history_status").value)
        other_page = TestPage()
        dashboard.build_dashboard(other_page, MEMBER, {MEMBER["id"]: MEMBER}, lambda: True, lambda e: None)
        asyncio.run(other_page.tasks.pop(0)())
        self.assertTrue(find(other_page, "save_log").disabled)
        self.assertEqual(len(find(other_page, "timeline_list").controls), 0)

    def test_empty_invalid_and_duplicate_rows_are_reported(self):
        self.downloader.return_value = [{"fields": {}}, self.record(Value=-1),
                                        self.record("dup"), self.record("dup")]
        self.build()
        self.assertEqual(len(self.get("timeline_list").controls), 0)
        self.assertIn("1 empty, 1 invalid, 2 duplicate-ID", self.get("cloud_history_status").value)

    def test_logout_blocks_old_handlers_and_ignores_inflight_results(self):
        self.build()
        def fake_upload(batch, names, destination):
            self.session["active"] = False
            return {batch[0]["log_id"]: "rec123"}
        self.uploader.side_effect = fake_upload
        self.save()
        self.assertEqual(len(self.get("timeline_list").controls), 0)
        self.save()
        self.uploader.assert_called_once()
        self.refresh()
        self.assertEqual(self.downloader.call_count, 1)

    def test_save_and_refresh_are_serialized_while_request_is_running(self):
        self.build()
        def fake_upload(batch, names, destination):
            self.assertTrue(self.get("save_log").disabled)
            self.assertTrue(self.get("refresh_airtable_history").disabled)
            self.refresh()
            return {batch[0]["log_id"]: "rec123"}
        self.uploader.side_effect = fake_upload
        self.save()
        self.assertEqual(self.downloader.call_count, 1)
        self.assertFalse(self.get("save_log").disabled)

    def test_connection_check_is_read_only(self):
        self.build()
        asyncio.run(self.get("test_airtable_connection").on_click(None))
        self.assertIn("connected", self.get("airtable_status").value)
        self.uploader.assert_not_called()
