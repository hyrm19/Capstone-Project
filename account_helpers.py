"""Technical account helpers; start with auth.py to learn the login/signup flow.

Accounts use plain-text passwords for this learning demo. This module only
validates and saves the JSON data; auth.py compares the password strings.
"""

import json
import os
import re
import threading
from pathlib import Path
from tempfile import NamedTemporaryFile


MEMBERS_FILE = Path(__file__).resolve().parent / "data" / "members.json"
BADGE_COLORS = ("#2563EB", "#7C3AED", "#047857", "#BE123C", "#B45309")
# Protect read-modify-write registration within this running app. This is not a
# multi-computer database lock; shared accounts will need a backend later.
ACCOUNT_LOCK = threading.RLock()


class AccountError(Exception):
    """An account validation or file error safe to display in the login form."""


def normalize_email(email):
    """Treat capitalization and surrounding whitespace as the same email."""
    email = email.strip().casefold()
    if len(email) > 254 or re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email) is None:
        raise AccountError("Enter a valid email address.")
    return email


class AccountFile:
    """Read and write account records; it does not decide who may log in."""

    def __init__(self, path=MEMBERS_FILE):
        # Tests supply a temporary path so they never touch real family accounts.
        self.path = Path(path)

    def load(self):
        try:
            text = self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return []
        except (OSError, UnicodeError) as error:
            raise AccountError(f"Cannot read local accounts: {error}") from error
        try:
            accounts = json.loads(text)
            if not isinstance(accounts, list):
                raise ValueError("Expected an account list.")
            seen_ids, seen_emails = set(), set()
            for account in accounts:
                if not isinstance(account, dict):
                    raise ValueError("Invalid account record.")
                # Reject damaged files rather than treating them as an empty
                # database and overwriting someone's existing accounts on signup.
                member_id = account["id"]
                if not isinstance(member_id, str) or not member_id.startswith("member-"):
                    raise ValueError("Invalid member ID.")
                if not isinstance(account["name"], str) or not 1 <= len(account["name"].strip()) <= 60:
                    raise ValueError("Invalid member name.")
                if not isinstance(account["email"], str):
                    raise ValueError("Invalid email.")
                email = normalize_email(account["email"])
                if email != account["email"] or member_id in seen_ids or email in seen_emails:
                    raise ValueError("Duplicate or invalid account identity.")
                if account["color"] not in BADGE_COLORS:
                    raise ValueError("Invalid badge color.")
                # A password must be a regular JSON string, e.g. "demo1234".
                # Missing passwords are treated as invalid data, never reset.
                password = account["password"]
                if not isinstance(password, str) or not 8 <= len(password) <= 128 or not password.strip():
                    raise ValueError("Invalid demo password.")
                seen_ids.add(member_id)
                seen_emails.add(email)
            return accounts
        except (ValueError, KeyError, TypeError, RecursionError, AccountError) as error:
            raise AccountError(
                "Local account data is damaged or unsupported. Back up and repair "
                "data/members.json before trying again; it has not been overwritten."
            ) from error

    def save(self, accounts):
        # As with activity storage, write a new file first, then replace the old
        # one. Failure must not destroy the existing account database.
        temporary_path = None
        try:
            text = json.dumps(accounts, indent=2, ensure_ascii=False)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=self.path.parent,
                prefix=".members.", suffix=".tmp", delete=False,
            ) as temporary_file:
                temporary_path = Path(temporary_file.name)
                temporary_file.write(text)
                temporary_file.flush()
                os.fsync(temporary_file.fileno())
            os.replace(temporary_path, self.path)
        except OSError as error:
            raise AccountError(f"Cannot save local accounts: {error}") from error
        finally:
            if temporary_path is not None:
                try:
                    temporary_path.unlink(missing_ok=True)
                except OSError:
                    pass
