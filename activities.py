"""The activity names and units understood by this version of VitalityHub."""

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
