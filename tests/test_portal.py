"""Test the complete Login → Dashboard → Logout flow without a desktop window."""

import unittest
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import flet as ft

import main
from auth import AccountStore
from storage import load_habits, save_habits


class TestPage:
    def __init__(self):
        self.controls = []

    def add(self, *controls):
        self.controls.extend(controls)

    def clean(self):
        self.controls.clear()

    def update(self):
        pass


def walk(control):
    # Walk the content/controls tree to find controls by stable .data labels.
    yield control
    content = getattr(control, "content", None)
    if isinstance(content, ft.Control):
        yield from walk(content)
    for child in getattr(control, "controls", []):
        yield from walk(child)


class PortalTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        folder = Path(self.directory.name)
        self.store = AccountStore(folder / "members.json")
        self.habits_file = folder / "habits.json"
        patches = [
            patch("main.AccountStore", return_value=self.store),
            patch("dashboard.load_habits", side_effect=lambda: load_habits(self.habits_file)),
            patch("dashboard.save_habits", side_effect=lambda habits: save_habits(habits, self.habits_file)),
        ]
        self.account_factory, self.loader, self.saver = [p.start() for p in patches]
        for p in patches:
            self.addCleanup(p.stop)
        self.page = TestPage()
        main.main(self.page)

    def find(self, label):
        return next(
            c for root in self.page.controls for c in walk(root)
            if getattr(c, "data", None) == label
        )

    def login(self, email="alex@example.com", password="password123"):
        self.find("auth_email").value = email
        self.find("auth_password").value = password
        self.find("submit_auth").on_click(None)

    def save_activity(self, name="Steps", value="2000"):
        form = self.page.controls[-1].controls[0].content.controls
        activity_input = next(c for c in form if isinstance(c, ft.Column))
        activity_input.controls[1].value = name
        next(c for c in form if isinstance(c, ft.TextField)).value = value
        button = next(c for c in form if isinstance(c, ft.Button))
        button.on_click(None)
        return button

    def personal_entries(self):
        tabs = self.page.controls[-1].controls[1]
        return tabs.content.controls[1].controls[1].content.controls[-1].controls

    def test_starts_logged_out_and_failed_login_cannot_open_dashboard(self):
        self.assertTrue(self.find("auth_password").password)
        self.loader.assert_not_called()
        self.login(password="incorrect")
        self.assertIn("Incorrect email or password", self.find("auth_feedback").value)
        self.assertEqual(self.find("auth_password").value, "")
        self.assertFalse(self.find("submit_auth").disabled)
        self.assertFalse(self.find("auth_spinner").visible)
        self.loader.assert_not_called()

    def test_signup_requires_matching_passwords_then_allows_login_and_logout(self):
        self.find("switch_auth").on_click(None)
        self.find("auth_name").value = "Alex Morgan"
        self.find("auth_email").value = "Alex@Example.com"
        self.find("auth_password").value = "password123"
        self.find("auth_confirm").value = "different"
        self.find("submit_auth").on_click(None)
        self.assertIsNotNone(self.find("auth_confirm").error_text)
        self.assertEqual(self.store.members(), [])
        self.find("auth_confirm").value = "password123"
        old_password = self.find("auth_password")
        self.find("submit_auth").on_click(None)
        self.assertEqual(old_password.value, "")
        self.assertIn("Account created", self.find("auth_feedback").value)
        self.assertFalse(self.find("auth_name").visible)
        self.login()
        self.assertIsInstance(self.page.controls[-1], ft.Row)
        self.assertEqual(len(self.personal_entries()), 0)
        self.find("logout").on_click(None)
        self.assertIn("logged out", self.find("auth_feedback").value)
        self.assertEqual(self.find("auth_password").value, "")

    def test_two_accounts_have_separate_histories_and_legacy_demo_is_not_claimed(self):
        alex = self.store.register("Alex Morgan", "alex@example.com", "password123")
        jamie = self.store.register("Jamie Morgan", "jamie@example.com", "password123")
        legacy = {"name": "Steps", "value": 500, "unit": "steps",
                  "logged_at": datetime.now(), "member_id": "demo-alex"}
        save_habits([legacy], self.habits_file)
        self.login()
        self.assertEqual(len(self.personal_entries()), 0)
        self.save_activity()
        self.assertEqual(len(self.personal_entries()), 1)
        self.find("logout").on_click(None)
        self.login("jamie@example.com")
        self.assertEqual(len(self.personal_entries()), 0)
        self.save_activity("Water Intake", "3")
        self.assertEqual(len(self.personal_entries()), 1)
        records = load_habits(self.habits_file)
        self.assertEqual([h["member_id"] for h in records], ["demo-alex", alex["id"], jamie["id"]])

    def test_old_save_and_logout_handlers_stay_invalid_after_same_member_logs_in_again(self):
        self.store.register("Alex", "alex@example.com", "password123")
        self.login()
        old_save = self.save_activity()
        old_logout = self.find("logout")
        old_logout.on_click(None)
        original = self.habits_file.read_bytes()
        old_save.on_click(None)
        self.assertEqual(self.habits_file.read_bytes(), original)
        self.login()
        old_save.on_click(None)
        old_logout.on_click(None)
        self.assertEqual(self.habits_file.read_bytes(), original)
        self.assertIsInstance(self.page.controls[-1], ft.Row)

    def test_restarting_requires_login_even_when_accounts_exist(self):
        self.store.register("Alex", "alex@example.com", "password123")
        self.login()
        other_page = TestPage()
        main.main(other_page)
        self.assertEqual(len(other_page.controls), 1)
        self.assertIsInstance(other_page.controls[0], ft.Container)

    def test_corrupt_account_file_blocks_signup_without_overwriting_it(self):
        self.store.path.write_text("damaged accounts", encoding="utf-8")
        self.find("switch_auth").on_click(None)
        for field, value in [("auth_name", "Alex"), ("auth_email", "alex@example.com"),
                             ("auth_password", "password123"), ("auth_confirm", "password123")]:
            self.find(field).value = value
        self.find("submit_auth").on_click(None)
        self.assertIn("damaged", self.find("auth_feedback").value)
        self.assertEqual(self.store.path.read_text(encoding="utf-8"), "damaged accounts")
        self.loader.assert_not_called()
