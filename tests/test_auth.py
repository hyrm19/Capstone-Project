"""Cloud account tests. Remote records are simulated, never real passwords."""

import unittest
from unittest.mock import patch

from auth import AccountError, AccountStore
from airtable_api import AirtableError


class AccountTests(unittest.TestCase):
    def setUp(self):
        self.remote = []
        reader = patch("auth.read_accounts", side_effect=lambda: [dict(a) for a in self.remote])
        writer = patch("auth.create_account", side_effect=self.create)
        self.reader, self.writer = reader.start(), writer.start()
        self.addCleanup(reader.stop)
        self.addCleanup(writer.stop)
        self.store = AccountStore()

    def create(self, account):
        self.remote.append(dict(account))
        return account

    def register(self, email="alex@example.com", password="password123"):
        return self.store.register("Alex Morgan", email, password)

    def test_signup_stores_plain_password_online_but_returns_public_profile(self):
        with patch("pathlib.Path.write_text", side_effect=AssertionError("No file writes")):
            member = self.register(" Alex@Example.COM ")
        self.assertEqual(member["email"], "alex@example.com")
        self.assertEqual(self.remote[0]["password"], "password123")
        self.assertNotIn("password", member)
        self.assertTrue(member["id"].startswith("member-"))
        self.assertFalse(hasattr(self.store, "path"))

    def test_login_compares_strings_without_writing_any_data(self):
        member = self.register()
        self.writer.reset_mock()
        self.assertEqual(self.store.authenticate("ALEX@example.com", "password123"), member)
        self.writer.assert_not_called()
        self.assertEqual(AccountStore().authenticate("alex@example.com", "password123"), member)

    def test_wrong_email_password_case_and_spaces_do_not_match(self):
        self.register()
        for email, password in [("missing@example.com", "password123"),
                                ("alex@example.com", "Password123"),
                                ("alex@example.com", " password123"),
                                ("not-email", "password123"), ("alex@example.com", "")]:
            with self.subTest(email=email):
                with self.assertRaisesRegex(AccountError, "Incorrect email or password"):
                    self.store.authenticate(email, password)

    def test_password_spaces_are_preserved(self):
        self.register(password=" password123 ")
        self.store.authenticate("alex@example.com", " password123 ")
        with self.assertRaises(AccountError):
            self.store.authenticate("alex@example.com", "password123")

    def test_duplicate_email_is_rejected_without_overwriting_account(self):
        self.register()
        with self.assertRaisesRegex(AccountError, "already exists"):
            self.register(" ALEX@example.com ")
        self.assertEqual(len(self.remote), 1)

    def test_invalid_signup_is_rejected_before_network(self):
        for name, email, password in [(" ", "a@example.com", "password123"),
                                      ("A" * 61, "a@example.com", "password123"),
                                      ("Alex", "not-email", "password123"),
                                      ("Alex", "a@example.com", "short"),
                                      ("Alex", "a@example.com", " " * 8)]:
            with self.assertRaises(AccountError):
                self.store.register(name, email, password)
        self.reader.assert_not_called()
        self.writer.assert_not_called()

    def test_network_failure_cannot_become_successful_login_or_signup(self):
        self.reader.side_effect = AirtableError("Members unavailable")
        with self.assertRaisesRegex(AccountError, "Members unavailable"):
            self.register()
        with self.assertRaises(AccountError):
            self.store.authenticate("alex@example.com", "password123")
        self.writer.assert_not_called()

    def test_signup_failure_does_not_return_a_profile(self):
        self.writer.side_effect = AirtableError("Signup not confirmed")
        with self.assertRaisesRegex(AccountError, "not confirmed"):
            self.register()
        self.assertEqual(self.remote, [])

    def test_incomplete_duplicate_or_bad_color_cloud_accounts_are_rejected(self):
        self.register()
        good = dict(self.remote[0])
        for records in [[{**good, "password": None}], [good, good], [{**good, "color": "not-a-color"}]]:
            self.remote[:] = records
            with self.assertRaises(AccountError):
                self.store.members()

    def test_public_members_never_contain_passwords(self):
        self.register()
        profiles = self.store.members()
        self.assertEqual(len(profiles), 1)
        self.assertNotIn("password", profiles[0])
