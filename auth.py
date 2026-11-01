"""Local accounts for the desktop demo; no passwords are stored as plain text."""

import hashlib
import hmac
import json
import os
import re
import secrets
import threading
from pathlib import Path
from tempfile import NamedTemporaryFile
from uuid import uuid4


MEMBERS_FILE = Path(__file__).resolve().parent / "data" / "members.json"
PASSWORD_ITERATIONS = 600_000
BADGE_COLORS = ("#2563EB", "#7C3AED", "#047857", "#BE123C", "#B45309")
# Protect read-modify-write registration within this running app. This is not a
# multi-computer database lock; shared accounts will need a backend later.
_ACCOUNT_LOCK = threading.RLock()


class AccountError(Exception):
    """An account validation or file error safe to display in the login form."""


def normalize_email(email):
    """Treat capitalization and surrounding whitespace as the same email."""
    email = email.strip().casefold()
    if len(email) > 254 or re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email) is None:
        raise AccountError("Enter a valid email address.")
    return email


def public_member(account):
    # Password hashes and salts must stay inside this module, not in UI controls.
    return {key: account[key] for key in ("id", "name", "email", "color")}


class AccountStore:
    """Read, register, and verify local accounts in an ignored JSON file."""

    def __init__(self, path=MEMBERS_FILE):
        # Tests supply a temporary path so they never touch real family accounts.
        self.path = Path(path)

    def _load(self):
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
                # Store and verify the algorithm parameters explicitly. Do not
                # accept arbitrary costs from an edited file (which could freeze
                # login with billions of iterations).
                if account["algorithm"] != "pbkdf2_sha256" or account["iterations"] != PASSWORD_ITERATIONS:
                    raise ValueError("Unsupported password hash settings.")
                for key, length in (("salt", 32), ("password_hash", 64)):
                    if not isinstance(account[key], str) or re.fullmatch(rf"[0-9a-f]{{{length}}}", account[key]) is None:
                        raise ValueError("Invalid password hash data.")
                seen_ids.add(member_id)
                seen_emails.add(email)
            return accounts
        except (ValueError, KeyError, TypeError, RecursionError, AccountError) as error:
            raise AccountError(
                "Local account data is damaged or unsupported. Back up and repair "
                "data/members.json before trying again; it has not been overwritten."
            ) from error

    def _save(self, accounts):
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

    def members(self):
        """Return only display-safe member details, never password information."""
        with _ACCOUNT_LOCK:
            return [public_member(account) for account in self._load()]

    def register(self, name, email, password):
        name = name.strip()
        if not 1 <= len(name) <= 60:
            raise AccountError("Enter a display name between 1 and 60 characters.")
        email = normalize_email(email)
        # Do not strip passwords: spaces can be deliberate characters. Reject
        # entirely blank passwords and keep a reasonable bound on input size.
        if not 8 <= len(password) <= 128 or not password.strip():
            raise AccountError("Use a password of 8–128 characters, not just spaces.")
        with _ACCOUNT_LOCK:
            accounts = self._load()
            if any(account["email"] == email for account in accounts):
                raise AccountError("An account with this email already exists.")
            # A salt is a different random value for every account. Two people
            # using the same password will still have different stored hashes.
            # PBKDF2 is a one-way password derivation algorithm, not encryption:
            # login repeats the calculation rather than decrypting a password.
            # The repeated work makes offline guessing harder if hashes leak.
            salt = secrets.token_bytes(16)
            digest = hashlib.pbkdf2_hmac(
                "sha256", password.encode("utf-8"), salt, PASSWORD_ITERATIONS
            )
            account = {
                "id": f"member-{uuid4().hex}",
                "name": name,
                "email": email,
                "color": BADGE_COLORS[len(accounts) % len(BADGE_COLORS)],
                "algorithm": "pbkdf2_sha256",
                "iterations": PASSWORD_ITERATIONS,
                "salt": salt.hex(),
                "password_hash": digest.hex(),
            }
            self._save(accounts + [account])
            return public_member(account)

    def authenticate(self, email, password):
        # Use the same generic message for a missing email and a wrong password.
        invalid = "Incorrect email or password."
        try:
            email = normalize_email(email)
        except AccountError:
            raise AccountError(invalid) from None
        if not 1 <= len(password) <= 128:
            raise AccountError(invalid)
        with _ACCOUNT_LOCK:
            accounts = self._load()
        account = next((a for a in accounts if a["email"] == email), None)
        # Perform the hash calculation even for an unknown email, avoiding a
        # fast missing-account path. compare_digest compares hashes safely.
        salt = bytes.fromhex(account["salt"]) if account else bytes(16)
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt, PASSWORD_ITERATIONS
        ).hex()
        expected = account["password_hash"] if account else "0" * 64
        if not hmac.compare_digest(digest, expected) or account is None:
            raise AccountError(invalid)
        return public_member(account)
