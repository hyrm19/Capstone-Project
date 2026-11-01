"""The activity names and units understood by this version of VitalityHub."""

from datetime import datetime

# These are demonstration targets for the school project, not health advice.
# Keeping goals in one place makes them easy to change or personalize later.
DEMO_STEP_GOAL = 8000
DEMO_WATER_GOAL = 8

# Keep one shared mapping so the form and file validation agree on each unit.
# A dictionary connects an activity name (key) to its measurement unit (value).
ACTIVITY_UNITS = {
    "Running": "km",
    "Swimming": "minutes",
    "Cycling": "km",
    "Yoga": "minutes",
    "Gym": "minutes",
    "Water Intake": "cups",
    "Steps": "steps",
}


def canonical_activity(text):
    """Return the standard spelling of a supported activity, or None."""
    # Accept typed names as well as clicked suggestions. Surrounding spaces and
    # capitalization should not matter: " running " becomes "Running".
    # Unknown names are rejected because we cannot choose their unit reliably.
    normalized = (text or "").strip().casefold()
    return next(
        (name for name in ACTIVITY_UNITS if name.casefold() == normalized),
        None,
    )


def daily_totals(habits, member_id, today=None):
    """Add one member's explicitly measured steps and cups for a local date."""
    # An optional date makes this helper easy to test without changing the
    # computer's clock. Normal app calls use the computer's current local date.
    if today is None:
        today = datetime.now().date()
    totals = {"steps": 0, "cups": 0.0}
    for habit in habits:
        # Never treat an old unassigned activity as belonging to a demo member.
        if member_id is None or habit.get("member_id") != member_id:
            continue
        timestamp = habit["logged_at"]
        # Our app saves local timestamps without timezone information. If a file
        # contains a timezone-aware timestamp, convert it to this computer's local
        # timezone before checking its date, so midnight is handled consistently.
        local_date = (
            timestamp.astimezone().date()
            if timestamp.tzinfo is not None else timestamp.date()
        )
        if local_date != today:
            continue

        # Check BOTH name and unit. A legacy entry named "Steps" without an
        # explicit unit is ambiguous and must not silently change the totals.
        # Each entry is an amount to ADD, not a replacement daily counter.
        if habit["name"] == "Steps" and habit.get("unit") == "steps":
            totals["steps"] += int(habit["value"])
        elif habit["name"] == "Water Intake" and habit.get("unit") == "cups":
            totals["cups"] += habit["value"]
    return totals
