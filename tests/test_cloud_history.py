"""Test row validation and safe history merging without network or data files."""

import unittest
from datetime import datetime, timezone

from cloud_history import newest_first, parse_cloud_history


class CloudHistoryTests(unittest.TestCase):
    destination = {"base_id": "appExample", "table": "Habits"}

    def record(self, **fields):
        values = {
            "LogID": "log123", "Activity": "Steps", "Value": 2000, "Unit": "steps",
            "MemberID": "member-alex", "MemberName": "Alex Morgan",
            "LoggedAt": "2026-11-01T10:00:00Z",
        }
        values.update(fields)
        return {"id": "rec123", "fields": values}

    def parse(self, records):
        return parse_cloud_history(records)

    def test_valid_record_preserves_identity_quantity_and_instant_but_no_password(self):
        parsed = self.parse([self.record(password="must-not-import", email="private@example.com")])
        habit = parsed["habits"][0]
        self.assertEqual(habit["log_id"], "log123")
        self.assertEqual(habit["member_id"], "member-alex")
        self.assertEqual(habit["member_name"], "Alex Morgan")
        self.assertEqual(habit["value"], 2000)
        self.assertEqual(habit["logged_at"].astimezone(timezone.utc), datetime(2026, 11, 1, 10, tzinfo=timezone.utc))
        self.assertNotIn("airtable_upload", habit)  # No local upload tracking file.
        self.assertNotIn("password", habit)
        self.assertNotIn("email", habit)

    def test_empty_and_invalid_rows_are_counted_without_stopping_valid_rows(self):
        records = [{"id": "recEmpty", "fields": {}}, None, self.record(LogID="valid")]
        for fields in [
            {"LogID": ""}, {"Value": True}, {"Value": -1}, {"Value": "5"},
            {"Value": float("nan")}, {"Value": float("inf")}, {"Value": 1.5},
            {"LoggedAt": "yesterday"}, {"Unit": "km"}, {"MemberID": []},
            {"MemberName": 12}, {"LogID": " spaced "},
        ]:
            records.append(self.record(LogID="invalid" + str(len(records)), **fields) if "LogID" not in fields else self.record(**fields))
        parsed = self.parse(records)
        self.assertEqual(len(parsed["habits"]), 1)
        self.assertEqual(parsed["empty"], 1)
        self.assertEqual(parsed["invalid"], 13)

    def test_duplicate_cloud_ids_are_all_skipped_even_if_owners_differ(self):
        parsed = self.parse([self.record(), self.record(MemberID="member-jamie")])
        self.assertEqual(parsed["habits"], [])
        self.assertEqual(parsed["duplicates"], 2)

    def test_unspecified_units_and_missing_owners_are_not_guessed(self):
        record = self.record(Activity="Running", Unit="unspecified", MemberID="")
        parsed = self.parse([record])
        habit = parsed["habits"][0]
        self.assertNotIn("unit", habit)
        self.assertNotIn("member_id", habit)
        self.assertNotIn("member_name", habit)

    def test_mixed_local_and_cloud_timestamps_sort_by_instant_not_import_order(self):
        local = {"name": "local", "logged_at": datetime(2026, 11, 1, 12).astimezone()}
        older = {"name": "older", "logged_at": datetime(2026, 10, 1, 12, tzinfo=timezone.utc)}
        later = {"name": "later", "logged_at": datetime(2026, 12, 1, 12)}
        self.assertEqual([h["name"] for h in newest_first([local, later, older])], ["later", "local", "older"])
