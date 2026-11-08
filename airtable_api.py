"""Airtable connection checks, activity uploads, and paginated downloads."""

import os
import time
from datetime import timezone
from pathlib import Path
from urllib.parse import quote

import requests
from dotenv import dotenv_values


ENV_FILE = Path(__file__).resolve().parent / ".env"
HABIT_FIELDS = ["LogID", "MemberID", "MemberName", "Activity", "Value", "Unit", "LoggedAt"]
MEMBER_FIELDS = ["id", "name", "email", "password", "color"]


class AirtableError(Exception):
    """A safe, readable error for the Cloud Status tab (never contains a token)."""


def read_settings(env_path=ENV_FILE):
    """Read private connection settings. Never print or save the returned token."""
    # Read settings on EACH check so editing .env does not require a restart.
    # dotenv_values returns a dictionary without changing global environment
    # variables. Real environment variables, if set, take priority over the file.
    try:
        settings = dotenv_values(env_path, interpolate=False)
    except (OSError, UnicodeError):
        raise AirtableError("Cannot read .env. Check the file and its permissions.") from None

    token = (os.getenv("AIRTABLE_TOKEN") or settings.get("AIRTABLE_TOKEN") or "").strip()
    base_id = (os.getenv("AIRTABLE_BASE_ID") or settings.get("AIRTABLE_BASE_ID") or "").strip()
    table = (os.getenv("AIRTABLE_TABLE_NAME") or settings.get("AIRTABLE_TABLE_NAME") or "Habits").strip()
    members_table = (os.getenv("AIRTABLE_MEMBERS_TABLE") or settings.get("AIRTABLE_MEMBERS_TABLE") or "Members").strip()
    if not token or not base_id:
        raise AirtableError("Set AIRTABLE_TOKEN and AIRTABLE_BASE_ID in your private .env file.")
    if not base_id.startswith("app") or not base_id.isalnum():
        raise AirtableError("AIRTABLE_BASE_ID must be the base ID beginning with app, not a URL.")
    if not table:
        raise AirtableError("Set AIRTABLE_TABLE_NAME to your table name, such as Habits.")

    # quote() makes names containing spaces safe to use inside a URL.
    url = f"https://api.airtable.com/v0/{base_id}/{quote(table, safe='')}"
    return {"token": token, "base_id": base_id, "table": table, "url": url, "members_table": members_table}


def get_destination(env_path=ENV_FILE):
    """Return just the public target, for tracking which table received a log."""
    settings = read_settings(env_path)
    return {"base_id": settings["base_id"], "table": settings["table"]}


def read_response(response):
    """Validate HTTP/JSON responses without exposing headers or private bodies."""
    if response.status_code != 200:
        messages = {
            401: "Token rejected. Check AIRTABLE_TOKEN in .env.",
            # Airtable also uses 403 when the base/table does not exist or is
            # not visible to this token. Do not blame the password or imply
            # that missing token scopes are the only possible cause.
            403: "Access denied or table not found. Check the table name, Base ID, token record scopes, and base access.",
            404: "Base or table not found. Check the Base ID, table name, and token access.",
            422: "Check the Airtable column names/types. For Habits, LogID must have no duplicate values.",
            429: "Too many requests. Wait a moment before trying again.",
        }
        message = messages.get(response.status_code, "Airtable is unavailable or returned an unexpected response.")
        raise AirtableError(f"{message} (HTTP {response.status_code})")
    try:
        data = response.json()
    except ValueError:
        raise AirtableError("Airtable returned an unreadable response. Please try again.") from None
    if not isinstance(data, dict) or not isinstance(data.get("records"), list):
        raise AirtableError("Airtable returned an unexpected response. Please try again.")
    return data


def check_connection(env_path=ENV_FILE):
    """Try reading one record; an empty but accessible table is also a success."""
    settings = read_settings(env_path)
    try:
        # GET only reads. This function NEVER sends account passwords, creates
        # records, or modifies the displayed history. maxRecords limits the read to one.
        # The token belongs in the authorization header, never the URL or UI.
        response = requests.get(
            settings["url"],
            headers={"Authorization": f"Bearer {settings['token']}"},
            params={"maxRecords": 1},
            timeout=15,
            allow_redirects=False,
        )
    except requests.Timeout:
        raise AirtableError("Airtable took too long to respond. Please try again.") from None
    except requests.RequestException:
        # Do not show raw exceptions or response bodies: they can contain
        # private request details. The user only needs an actionable explanation.
        raise AirtableError("Network error. Check your internet connection and try again.") from None

    read_response(response)

    # Do not display record contents. A successful empty list proves read access
    # just as well as a populated one. Write permissions are NOT tested here.
    return "Airtable connected. Read access verified; no records were changed."


def upload_batch(habits, member_names, destination, env_path=ENV_FILE):
    """Create/update up to ten logs by LogID; return {LogID: Airtable record ID}."""
    settings = read_settings(env_path)
    # If .env was edited partway through uploading, stop rather than splitting
    # history across two tables or recording success against the wrong target.
    if destination != {"base_id": settings["base_id"], "table": settings["table"]}:
        raise AirtableError("Airtable destination changed. Please start the upload again.")
    if not 1 <= len(habits) <= 10:
        raise AirtableError("An upload batch must contain between 1 and 10 activities.")

    records = []
    expected_ids = set()
    for habit in habits:
        log_id = habit.get("log_id")
        if not isinstance(log_id, str) or not log_id.strip() or log_id in expected_ids:
            raise AirtableError("Every activity needs its own LogID before uploading.")
        expected_ids.add(log_id)
        # Explicitly choose the ONLY seven fields we send. Never upload an entire
        # account dictionary, which could contain a plain-text demo password.
        # Convert local times to UTC so Airtable does not shift the event's time.
        fields = {
            "LogID": log_id,
            "MemberID": habit.get("member_id", ""),
            "MemberName": member_names.get(habit.get("member_id"), "Unassigned"),
            "Activity": habit["name"],
            "Value": habit["value"],
            "Unit": habit.get("unit", "unspecified"),
            "LoggedAt": habit["logged_at"].astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        }
        records.append({"fields": fields})

    try:
        # "Upsert" means update a matching LogID, or create it if not found.
        # Repeating the SAME request after a timeout therefore does not create
        # another row. LogID must be a normal text field in your Airtable table.
        response = requests.patch(
            settings["url"],
            headers={"Authorization": f"Bearer {settings['token']}"},
            json={"performUpsert": {"fieldsToMergeOn": ["LogID"]}, "records": records},
            timeout=15,
            allow_redirects=False,
        )
    except requests.RequestException:
        # A timeout does not prove failure: the server might already have saved
        # a row. Reusing the in-memory draft LogID makes an in-session retry safe.
        raise AirtableError("Upload interrupted. Some records may have reached Airtable; retry using the same LogIDs.") from None

    uploaded = {}
    for record in read_response(response)["records"]:
        if not isinstance(record, dict) or not isinstance(record.get("fields"), dict):
            raise AirtableError("Unexpected upload response. Keep the app open to retry the same LogID.")
        log_id = record["fields"].get("LogID")
        record_id = record.get("id")
        if (
            not isinstance(log_id, str) or log_id not in expected_ids or log_id in uploaded
            or not isinstance(record_id, str) or not record_id.startswith("rec")
        ):
            raise AirtableError("Unexpected upload response. Keep the app open to retry the same LogID.")
        uploaded[log_id] = record_id
    if set(uploaded) != expected_ids:
        raise AirtableError("Airtable did not confirm every activity. Keep the app open to retry the same LogID.")
    return uploaded


def download_records(destination, env_path=ENV_FILE):
    """Read all activity pages. Airtable is the only history database now."""
    settings = read_settings(env_path)
    if destination != {"base_id": settings["base_id"], "table": settings["table"]}:
        raise AirtableError("Airtable destination changed. Please refresh again.")
    return fetch_records(settings, HABIT_FIELDS)


def fetch_records(settings, fields):
    """Read every page of a table using only the requested column names."""
    records = []
    offset = None
    seen_offsets = set()
    while True:
        # Airtable returns at most 100 records per page. Its next-page offset
        # means we must ask again; reading only page one would lose old history.
        params = {
            "pageSize": 100,
            # Request only this operation's columns, not unrelated table data.
            "fields[]": fields,
        }
        if offset is not None:
            params["offset"] = offset
        try:
            response = requests.get(
                settings["url"],
                headers={"Authorization": f"Bearer {settings['token']}"},
                params=params, timeout=15, allow_redirects=False,
            )
        except requests.RequestException:
            # If ANY page fails, do not return a misleading partial history.
            # The caller keeps its last in-memory view, never a partial result.
            raise AirtableError("Download interrupted. The current view was not changed; please refresh again.") from None
        data = read_response(response)
        records.extend(data["records"])
        offset = data.get("offset")
        if offset is None:
            return records
        if not isinstance(offset, str) or not offset or offset in seen_offsets:
            raise AirtableError("Airtable returned an invalid page reference. Please refresh again.")
        seen_offsets.add(offset)
        # This function runs in a worker thread. A short pause between pages
        # respects Airtable's request limit without freezing the interface.
        time.sleep(0.25)


def member_settings(env_path=ENV_FILE):
    """Use the same base and token but point to the separate Members table."""
    settings = read_settings(env_path)
    table = settings["members_table"]
    if not table or table == settings["table"]:
        raise AirtableError("Use a separate Members table for accounts, not the Habits table.")
    settings["url"] = f"https://api.airtable.com/v0/{settings['base_id']}/{quote(table, safe='')}"
    return settings


def read_accounts(env_path=ENV_FILE):
    """Read demo accounts into memory only. Never print or save this response."""
    settings = member_settings(env_path)
    try:
        records = fetch_records(settings, MEMBER_FIELDS)
    except AirtableError as error:
        # A successful Habits connection does not prove that Members exists.
        # Identify the failing operation without exposing tokens or account data.
        raise AirtableError(
            "Cannot load the account table configured by AIRTABLE_MEMBERS_TABLE. "
            f"{error} Confirm that this account table exists in the same base."
        ) from None
    accounts = []
    for record in records:
        fields = record.get("fields") if isinstance(record, dict) else None
        if fields == {}:
            continue  # Ignore Airtable's blank starter rows.
        if not isinstance(fields, dict):
            raise AirtableError("An account row has invalid fields in Members.")
        # Only the five account columns are used; API metadata is not an account.
        accounts.append({key: fields.get(key) for key in MEMBER_FIELDS})
    return accounts


def create_account(account, env_path=ENV_FILE):
    """Create a NEW demo account. Never upsert by email and overwrite a user."""
    settings = member_settings(env_path)
    fields = {key: account[key] for key in MEMBER_FIELDS}
    try:
        response = requests.post(
            settings["url"], headers={"Authorization": f"Bearer {settings['token']}"},
            json={"records": [{"fields": fields}]}, timeout=15, allow_redirects=False,
        )
    except requests.RequestException:
        raise AirtableError(
            "Signup was not confirmed. It may already have reached Airtable. "
            "Try logging in before registering again."
        ) from None
    records = read_response(response)["records"]
    if len(records) != 1 or not isinstance(records[0], dict) or records[0].get("fields") != fields:
        raise AirtableError("Signup was not confirmed. Check the Members text fields, then try logging in.")
    return account
