"""Validate Airtable rows for an in-memory display; never write any files."""

from datetime import datetime, timezone
from math import isfinite

from activities import ACTIVITY_UNITS, canonical_activity


def parse_cloud_history(records):
    """Return valid activities and counts of empty, invalid, and duplicate rows."""
    result = {"habits": [], "empty": 0, "invalid": 0, "duplicates": 0}
    id_counts = {}
    # 1. Count IDs before importing anything. If two cloud rows use the same
    # LogID, skip BOTH rather than arbitrarily choosing an owner/value to trust.
    for record in records:
        fields = record.get("fields") if isinstance(record, dict) else None
        log_id = fields.get("LogID") if isinstance(fields, dict) else None
        if isinstance(log_id, str) and log_id.strip():
            id_counts[log_id] = id_counts.get(log_id, 0) + 1

    for record in records:
        fields = record.get("fields") if isinstance(record, dict) else None
        if fields == {}:
            result["empty"] += 1  # Airtable's default blank records are harmless.
            continue
        if not isinstance(fields, dict):
            result["invalid"] += 1
            continue
        log_id = fields.get("LogID")
        if isinstance(log_id, str) and id_counts.get(log_id, 0) > 1:
            result["duplicates"] += 1
            continue

        # 2. Validate a row before adding it. One bad row should not stop valid
        # records from loading, but it must never reach the dashboard's view.
        try:
            record_id = record.get("id")
            if not isinstance(record_id, str) or not record_id.startswith("rec"):
                raise ValueError
            if not isinstance(log_id, str) or not log_id.strip() or log_id != log_id.strip():
                raise ValueError
            name = fields.get("Activity")
            if not isinstance(name, str) or not name.strip():
                raise ValueError
            name = canonical_activity(name) or name.strip()
            value = fields.get("Value")
            if type(value) not in (int, float) or not isfinite(value) or value <= 0:
                raise ValueError
            timestamp = fields.get("LoggedAt")
            if not isinstance(timestamp, str):
                raise ValueError
            timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            if timestamp.tzinfo is not None:
                timestamp = timestamp.astimezone()  # Show the computer's local time.
            habit = {"log_id": log_id, "name": name, "value": value, "logged_at": timestamp}

            # Missing/unspecified units remain unknown; never assume that an old
            # Running record measured km. Explicit units must match our rules.
            unit = fields.get("Unit")
            if unit not in (None, "", "unspecified"):
                if not isinstance(unit, str) or unit != ACTIVITY_UNITS.get(name):
                    raise ValueError
                if unit == "steps" and value % 1 != 0:
                    raise ValueError
                habit["unit"] = unit

            member_id = fields.get("MemberID", "")
            if not isinstance(member_id, str) or member_id != member_id.strip():
                raise ValueError
            if member_id:
                habit["member_id"] = member_id
                member_name = fields.get("MemberName")
                if member_name is not None and not isinstance(member_name, str):
                    raise ValueError
                if member_name and member_name.strip():
                    # A display name is not an account. Keep it for timeline
                    # badges without creating a login or assigning by name.
                    habit["member_name"] = member_name.strip()

            result["habits"].append(habit)
        except (ValueError, TypeError, OverflowError, OSError):
            result["invalid"] += 1
    return result


def newest_first(habits):
    """Sort the display by event time, not by the order records were imported."""
    # Local records may have naive timestamps while Airtable records include a
    # timezone. Convert both to UTC for comparison without changing saved data.
    # For identical times, show the last saved/imported item first as before.
    return sorted(reversed(habits), key=lambda habit: habit["logged_at"].astimezone(timezone.utc), reverse=True)
