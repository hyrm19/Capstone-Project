"""Simple demo authentication: accounts are in Airtable, passwords are strings."""

import re
import threading
from uuid import uuid4

from airtable_api import AirtableError, read_accounts, create_account


BADGE_COLORS = ("#2563EB", "#7C3AED", "#047857", "#BE123C", "#B45309")
SIGNUP_LOCK = threading.Lock()


class AccountError(Exception):
    """main.py displays this message when validation or a cloud request fails."""


def normalize_email(email):
    email = email.strip().casefold()
    if len(email) > 254 or re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email) is None:
        raise AccountError("Enter a valid email address.")
    return email


def public_member(account):
    # The dashboard needs identity and color, never the stored password.
    return {"id": account["id"], "name": account["name"], "email": account["email"], "color": account["color"]}


class AccountStore:
    """Use Airtable as the account database. No account files are read or saved."""

    def _accounts(self):
        try:
            accounts = read_accounts()
        except AirtableError as error:
            raise AccountError(str(error)) from None
        # Detect incomplete or duplicate account rows instead of picking the
        # first matching password. Airtable does not enforce unique emails.
        ids, emails = set(), set()
        for account in accounts:
            for key in ("id", "name", "email", "password", "color"):
                if not isinstance(account.get(key), str) or not account[key].strip():
                    raise AccountError("A Members row is incomplete. Check id, name, email, password, and color.")
            email = normalize_email(account["email"])
            if re.fullmatch(r"#[0-9a-fA-F]{6}", account["color"]) is None:
                raise AccountError("Use a hex color such as #2563EB in the Members color column.")
            if account["id"] in ids or email in emails:
                raise AccountError("Duplicate member IDs or emails in Members. Fix the rows before logging in.")
            ids.add(account["id"])
            emails.add(email)
        return accounts

    def members(self):
        """Read display-safe family profiles, without downloading passwords to disk."""
        members = []
        for account in self._accounts():
            members.append(public_member(account))
        return members

    def register(self, name, email, password):
        # 1. Check the user's input before making a request.
        name = name.strip()
        if len(name) < 1 or len(name) > 60:
            raise AccountError("Enter a display name between 1 and 60 characters.")
        email = normalize_email(email)
        if len(password) < 8 or len(password) > 128 or not password.strip():
            raise AccountError("Use a password of 8–128 characters, not just spaces.")

        # This lock makes signups in this app take turns. It cannot guarantee
        # email uniqueness across multiple computers; this is a learning demo.
        with SIGNUP_LOCK:
            # 2. Look through the ONLINE accounts for an existing email.
            accounts = self._accounts()
            for account in accounts:
                if normalize_email(account["email"]) == email:
                    raise AccountError("An account with this email already exists.")
            # 3. Create an ID that stays the same across all computers, then
            # send the five account columns to Members, NOT the Habits table.
            account = {
                "id": "member-" + uuid4().hex, "name": name, "email": email,
                "password": password,  # Demo only: never use a real password.
                "color": BADGE_COLORS[len(accounts) % len(BADGE_COLORS)],
            }
            try:
                create_account(account)
            except AirtableError as error:
                raise AccountError(str(error)) from None
            return public_member(account)

    def authenticate(self, email, password):
        # 1. Clean up the email, but do NOT strip or lowercase the password.
        error_message = "Incorrect email or password."
        try:
            email = normalize_email(email)
        except AccountError:
            raise AccountError(error_message) from None
        if not 1 <= len(password) <= 128:
            raise AccountError(error_message)
        # 2. Compare ordinary strings against the ONLINE account records.
        # Nothing is written to disk or changed in Airtable when logging in.
        for account in self._accounts():
            if normalize_email(account["email"]) == email:
                if account["password"] == password:
                    return public_member(account)
        raise AccountError(error_message)
