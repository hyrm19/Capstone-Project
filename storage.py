"""Read and write local activities without depending on the Flet interface."""

import json
import math
import os
from datetime import datetime
from pathlib import Path
from tempfile import NamedTemporaryFile

from activities import ACTIVITY_UNITS


# Anchor the path to this source file, not the terminal's current directory.
# Starting the app from another directory will still use the same data file.
DATA_FILE = Path(__file__).resolve().parent / "data" / "habits.json"


class StorageError(Exception):
    """A readable error that the interface can display without crashing."""


def _decode_habits(records):
    """Validate JSON data and turn timestamp strings back into datetime objects."""
    if not isinstance(records, list):
        raise ValueError("The saved data must be a list of activities.")

    habits = []
    for record in records:
        if not isinstance(record, dict):
            raise ValueError("Each activity must be an object.")

        name = record.get("name")
        value = record.get("value")
        timestamp = record.get("logged_at")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("An activity has a missing or invalid name.")
        # bool is a subclass of int in Python, but true/false are not quantities.
        if (
            type(value) not in (int, float)
            or not math.isfinite(value)
            or value <= 0
        ):
            raise ValueError("An activity has an invalid numeric value.")
        if not isinstance(timestamp, str):
            raise ValueError("An activity has a missing or invalid timestamp.")

        habit = {
            "name": name.strip(),
            "value": value,
            "logged_at": datetime.fromisoformat(timestamp),
        }
        # Older files have no member_id, so keep those entries unassigned.
        # If an ID is present, preserve it even if this app does not recognize
        # that member. Never guess ownership from the currently selected member.
        if "member_id" in record:
            member_id = record["member_id"]
            if not isinstance(member_id, str) or not member_id.strip():
                raise ValueError("An activity has an invalid member ID.")
            habit["member_id"] = member_id
        # Unit is optional for backward compatibility. Never infer it from an
        # old activity name: "Running: 5" might have meant minutes, not km.
        if "unit" in record:
            unit = record["unit"]
            if not isinstance(unit, str) or unit != ACTIVITY_UNITS.get(habit["name"]):
                raise ValueError("An activity has an invalid or mismatched unit.")
            if unit == "steps" and value % 1 != 0:
                raise ValueError("Steps must be a whole number.")
            habit["unit"] = unit
        habits.append(habit)
    # Validate the entire file rather than silently skipping damaged entries.
    # Otherwise a later save could accidentally erase the entries we skipped.
    return habits


def load_habits(path=DATA_FILE):
    """Return saved activities; a missing file means this is the first run."""
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return []
    except (OSError, UnicodeError) as error:
        raise StorageError(f"Cannot read {path}: {error}") from error

    try:
        return _decode_habits(json.loads(text))
    except (ValueError, OverflowError, RecursionError) as error:
        raise StorageError(f"Invalid data in {path}: {error}") from error


def save_habits(habits, path=DATA_FILE):
    """Save the full list, replacing the old file only after writing succeeds."""
    path = Path(path)
    temporary_path = None
    try:
        # JSON cannot store datetime objects directly. ISO text keeps the date
        # and time precise and can be restored with datetime.fromisoformat().
        records = [
            {
                "name": habit["name"],
                "value": habit["value"],
                "logged_at": habit["logged_at"].isoformat(),
                # Add the optional key only when it exists. This lets old and
                # new entries live together without changing historical owners.
                **({"member_id": habit["member_id"]} if "member_id" in habit else {}),
                # Preserve explicit units only; leave historical entries alone.
                **({"unit": habit["unit"]} if "unit" in habit else {}),
            }
            for habit in habits
        ]
        _decode_habits(records)
        text = json.dumps(records, indent=2, ensure_ascii=False, allow_nan=False)
        path.parent.mkdir(parents=True, exist_ok=True)

        # Write beside the destination so the final replacement is on the same
        # filesystem. Never empty the original file before the new one is ready.
        with NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent,
            prefix=f".{path.name}.", suffix=".tmp", delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            temporary_file.write(text)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())

        # The temporary file must be closed before replacing a file on Windows.
        os.replace(temporary_path, path)
    except (OSError, ValueError, TypeError, KeyError, AttributeError, OverflowError) as error:
        raise StorageError(f"Cannot save activities to {path}: {error}") from error
    finally:
        # Clean up a leftover temporary file if writing or replacing failed.
        # A cleanup error must not hide the original, more useful error.
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass
