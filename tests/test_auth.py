"""Test plain-text password comparisons and local account file handling."""

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from auth import AccountError, AccountStore


class AccountTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "data" / "members.json"
        self.store = AccountStore(self.path)

    def register(self, email="alex@example.com"):
        return self.store.register("Alex Morgan", email, "Example-password-123")

    def test_registration_normalizes_email_and_stores_plain_password(self):
        member = self.register(" Alex@Example.COM ")
        self.assertEqual(member["email"], "alex@example.com")
        self.assertTrue(member["id"].startswith("member-"))
        self.assertEqual(set(member), {"id", "name", "email", "color"})
        text = self.path.read_text(encoding="utf-8")
        self.assertIn("Example-password-123", text)
        record = json.loads(text)[0]
        self.assertEqual(record["password"], "Example-password-123")
        for key in ("salt", "password_hash", "algorithm", "iterations"):
            self.assertNotIn(key, record)
        # A new store instance logs in by comparing the saved password string.
        self.assertEqual(
            AccountStore(self.path).authenticate("ALEX@example.com", "Example-password-123"),
            member,
        )
        self.assertEqual(self.store.members(), [member])

    def test_same_password_accounts_still_have_separate_member_ids(self):
        first = self.register()
        second = self.register("another@example.com")
        records = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertNotEqual(first["id"], second["id"])
        self.assertEqual(records[0]["password"], records[1]["password"])
        self.assertNotIn("password", first)  # The UI still gets display details only.

    def test_duplicate_email_does_not_replace_accounts(self):
        self.register()
        original = self.path.read_bytes()
        with self.assertRaisesRegex(AccountError, "already exists"):
            self.register(" ALEX@example.com ")
        self.assertEqual(self.path.read_bytes(), original)

    def test_invalid_signup_fields_do_not_create_file(self):
        for name, email, password in [
            (" ", "alex@example.com", "password123"),
            ("A" * 61, "alex@example.com", "password123"),
            ("Alex", "invalid-email", "password123"),
            ("Alex", "a@@example.com", "password123"),
            ("Alex", "alex@example.com", "short"),
            ("Alex", "alex@example.com", " " * 8),
            ("Alex", "alex@example.com", "a" * 129),
        ]:
            with self.subTest(name=name, email=email):
                with self.assertRaises(AccountError):
                    self.store.register(name, email, password)
        self.assertFalse(self.path.exists())

    def test_wrong_password_and_unknown_email_have_same_error(self):
        self.register()
        for email, password in [
            ("alex@example.com", "wrong-password"),
            ("missing@example.com", "Example-password-123"),
            ("not an email", "Example-password-123"),
            ("alex@example.com", ""),
        ]:
            with self.subTest(email=email):
                with self.assertRaisesRegex(AccountError, "^Incorrect email or password.$"):
                    self.store.authenticate(email, password)

    def test_password_spaces_are_not_silently_removed(self):
        member = self.store.register("Alex", "alex@example.com", " password123 ")
        self.assertEqual(self.store.authenticate("alex@example.com", " password123 "), member)
        with self.assertRaises(AccountError):
            self.store.authenticate("alex@example.com", "password123")

    def test_corrupt_accounts_are_not_overwritten(self):
        self.path.parent.mkdir()
        for text in ("", "broken", "{}", "[{}]", "[null]"):
            with self.subTest(text=text):
                self.path.write_text(text, encoding="utf-8")
                with self.assertRaises(AccountError):
                    self.register()
                with self.assertRaises(AccountError):
                    self.store.authenticate("alex@example.com", "password123")
                self.assertEqual(self.path.read_text(encoding="utf-8"), text)

    def test_invalid_password_formats_and_duplicate_records_are_rejected(self):
        self.register()
        good = json.loads(self.path.read_text(encoding="utf-8"))[0]
        for records in [
            [good, good],
            [{**good, "password": None}],
            [{**good, "password": ""}],
            [{**good, "password": 12345678}],
            [{key: value for key, value in good.items() if key != "password"}],
            [{**good, "id": "demo-alex"}],
        ]:
            with self.subTest(records=records):
                self.path.write_text(json.dumps(records), encoding="utf-8")
                with self.assertRaises(AccountError):
                    self.store.members()

    def test_password_comparison_is_case_sensitive(self):
        self.register()
        with self.assertRaises(AccountError):
            self.store.authenticate("alex@example.com", "example-password-123")

    def test_login_only_reads_accounts_and_does_not_change_the_file(self):
        member = self.register()
        original = self.path.read_bytes()
        with patch.object(self.store.file, "save", side_effect=AssertionError("Login must not save")):
            self.assertEqual(self.store.authenticate("alex@example.com", "Example-password-123"), member)
            with self.assertRaises(AccountError):
                self.store.authenticate("alex@example.com", "wrong-password")
        self.assertEqual(self.path.read_bytes(), original)

    def test_failed_write_preserves_existing_accounts_and_removes_temp_file(self):
        self.register()
        original = self.path.read_bytes()
        with patch("account_helpers.os.replace", side_effect=PermissionError("Access denied")):
            with self.assertRaises(AccountError):
                self.register("second@example.com")
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])

    def test_unreadable_accounts_are_not_treated_as_empty(self):
        with patch.object(Path, "read_text", side_effect=PermissionError("Access denied")):
            with self.assertRaises(AccountError):
                self.register()
