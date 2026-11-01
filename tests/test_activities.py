"""Check daily calculations independently of Flet and JSON file handling."""

import unittest
from datetime import date, datetime, timedelta, timezone

from activities import daily_totals


class DailyTotalsTests(unittest.TestCase):
    def record(self, name="Steps", value=2000, unit="steps", member_id="demo-alex", timestamp=None):
        return {
            "name": name,
            "value": value,
            "unit": unit,
            "member_id": member_id,
            "logged_at": timestamp or datetime(2026, 11, 1, 12),
        }

    def test_only_requested_member_date_name_and_unit_are_counted(self):
        records = [
            self.record(),
            self.record(value=500),
            self.record("Water Intake", 1.5, "cups"),
            self.record(member_id="demo-jamie"),
            self.record(member_id=None),
            self.record(timestamp=datetime(2026, 10, 31, 23, 59)),
            self.record(timestamp=datetime(2026, 11, 2, 0, 0)),
            self.record(unit=None),
            self.record("Running", 5, "km"),
        ]
        self.assertEqual(
            daily_totals(records, "demo-alex", date(2026, 11, 1)),
            {"steps": 2500, "cups": 1.5},
        )

    def test_no_entries_and_no_selected_member_have_zero_totals(self):
        self.assertEqual(daily_totals([], "demo-alex"), {"steps": 0, "cups": 0})
        self.assertEqual(daily_totals([self.record(member_id=None)], None), {"steps": 0, "cups": 0})

    def test_local_day_boundaries_are_inclusive_at_start_and_exclusive_at_end(self):
        records = [
            self.record(value=1, timestamp=datetime(2026, 11, 1, 0, 0)),
            self.record(value=2, timestamp=datetime(2026, 11, 1, 23, 59, 59)),
            self.record(value=4, timestamp=datetime(2026, 11, 2, 0, 0)),
        ]
        self.assertEqual(daily_totals(records, "demo-alex", date(2026, 11, 1))["steps"], 3)

    def test_timezone_aware_timestamp_uses_computers_local_date(self):
        # Express local midnight in another timezone. Its written date differs,
        # but conversion back to this computer's timezone identifies the right day.
        local_start = datetime(2026, 11, 1, 0, 0).astimezone()
        other_zone = timezone(local_start.utcoffset() - timedelta(hours=1))
        timestamp = local_start.astimezone(other_zone)
        records = [self.record(timestamp=timestamp)]
        self.assertEqual(daily_totals(records, "demo-alex", date(2026, 11, 1))["steps"], 2000)
