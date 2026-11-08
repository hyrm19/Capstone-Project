"""Exercise online signup/login/logout using fake Airtable account records."""

import asyncio
import unittest
from unittest.mock import patch

import main
from auth import AccountStore
from airtable_api import AirtableError
from ui_helpers import TestPage, find


class PortalTests(unittest.TestCase):
    def setUp(self):
        self.remote_accounts = []
        def create(account):
            self.remote_accounts.append(dict(account))
            return account
        patches = [
            patch("auth.read_accounts", side_effect=lambda: [dict(a) for a in self.remote_accounts]),
            patch("auth.create_account", side_effect=create),
            patch("dashboard.get_destination", return_value={"base_id": "appTest", "table": "Habits"}),
            patch("dashboard.download_records", return_value=[]),
            patch("dashboard.upload_batch", side_effect=lambda batch, names, target: {batch[0]["log_id"]: "rec123"}),
        ]
        self.reader, self.writer, _, self.downloader, self.uploader = [p.start() for p in patches]
        for p in patches:
            self.addCleanup(p.stop)
        self.page = TestPage()
        main.main(self.page)

    def get(self, label):
        return find(self.page, label)

    def login(self, email="alex@example.com", password="password123"):
        self.get("auth_email").value = email
        self.get("auth_password").value = password
        asyncio.run(self.get("submit_auth").on_click(None))
        while self.page.tasks:
            asyncio.run(self.page.tasks.pop(0)())

    def test_starts_logged_out_and_masks_login_and_signup_passwords(self):
        self.assertTrue(self.get("auth_password").password)
        self.assertFalse(self.get("auth_password").can_reveal_password)  # Custom eye instead.
        self.reader.assert_not_called()
        self.get("switch_auth").on_click(None)
        self.assertTrue(self.get("auth_confirm").password)
        self.assertFalse(self.get("auth_confirm").can_reveal_password)

    def test_eye_icon_shows_current_password_visibility_in_both_forms(self):
        import flet as ft
        for signup in [False, True]:
            if signup:
                self.get("switch_auth").on_click(None)
            keys = ["auth_password", "auth_confirm"] if signup else ["auth_password"]
            for key in keys:
                field = self.get(key)
                eye = field.suffix
                field.value = "demo1234"
                self.assertTrue(field.password)
                self.assertEqual(eye.icon, ft.Icons.VISIBILITY_OFF)
                eye.on_click(None)
                self.assertFalse(field.password)
                self.assertEqual(eye.icon, ft.Icons.VISIBILITY)
                eye.on_click(None)
                self.assertTrue(field.password)
                self.assertEqual(eye.icon, ft.Icons.VISIBILITY_OFF)
                self.assertEqual(field.value, "demo1234")

    def test_signup_confirmation_then_login_and_logout(self):
        self.get("switch_auth").on_click(None)
        for key, value in [("auth_name", "Alex Morgan"), ("auth_email", "Alex@Example.com"),
                           ("auth_password", "password123"), ("auth_confirm", "different")]:
            self.get(key).value = value
        asyncio.run(self.get("submit_auth").on_click(None))
        self.assertIsNotNone(self.get("auth_confirm").error_text)
        self.writer.assert_not_called()
        self.get("auth_confirm").value = "password123"
        asyncio.run(self.get("submit_auth").on_click(None))
        self.assertIn("Account created", self.get("auth_feedback").value)
        self.assertEqual(self.remote_accounts[0]["password"], "password123")
        self.login()
        self.assertFalse(self.get("save_log").disabled)
        self.get("logout").on_click(None)
        self.assertIn("logged out", self.get("auth_feedback").value)
        self.assertEqual(self.get("auth_password").value, "")

    def test_failed_or_offline_login_cannot_open_dashboard(self):
        self.login(password="wrong")
        self.assertIn("Incorrect", self.get("auth_feedback").value)
        self.downloader.assert_not_called()
        self.reader.side_effect = AirtableError("Members unavailable")
        self.login()
        self.assertIn("Members unavailable", self.get("auth_feedback").value)
        self.assertFalse(self.get("submit_auth").disabled)
        self.downloader.assert_not_called()

    def test_same_online_account_can_login_in_a_new_app_session(self):
        member = AccountStore().register("Alex", "alex@example.com", "password123")
        self.login()
        other_page = TestPage()
        main.main(other_page)
        self.assertTrue(find(other_page, "auth_password").password)
        find(other_page, "auth_email").value = "alex@example.com"
        find(other_page, "auth_password").value = "password123"
        asyncio.run(find(other_page, "submit_auth").on_click(None))
        self.assertEqual(AccountStore().members()[0]["id"], member["id"])
        self.assertIn("alex@example.com", str(other_page.controls))

    def test_old_buttons_remain_invalid_after_logout_and_login_again(self):
        AccountStore().register("Alex", "alex@example.com", "password123")
        self.login()
        old_save, old_logout = self.get("save_log"), self.get("logout")
        old_logout.on_click(None)
        self.login()
        asyncio.run(old_save.on_click(None))
        old_logout.on_click(None)
        self.uploader.assert_not_called()
        self.assertFalse(self.get("save_log").disabled)
