"""Connection, upload, and download tests using only mocked HTTP responses."""

import os
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

import requests

from airtable_api import AirtableError, check_connection, get_destination, upload_batch, download_records, read_accounts, create_account


class AirtableTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / ".env"
        # Never load the real project's .env or call Airtable in automated tests.
        self.path.write_text(
            "AIRTABLE_TOKEN=fake-test-token\n"
            "AIRTABLE_BASE_ID=appExample123\n"
            "AIRTABLE_TABLE_NAME=Habits\n",
            encoding="utf-8",
        )
        environment = patch.dict(os.environ, {}, clear=True)
        environment.start()
        self.addCleanup(environment.stop)
        getter = patch("airtable_api.requests.get")
        self.get = getter.start()
        self.addCleanup(getter.stop)
        self.response = Mock(status_code=200)
        self.response.json.return_value = {"records": []}
        self.get.return_value = self.response
        writer = patch("airtable_api.requests.patch")
        self.writer = writer.start()
        self.addCleanup(writer.stop)

        def fake_write(url, **kwargs):
            response = Mock(status_code=200)
            response.json.return_value = {"records": [
                {"id": f"rec{index}", "fields": record["fields"]}
                for index, record in enumerate(kwargs["json"]["records"])
            ]}
            return response

        self.writer.side_effect = fake_write
        self.habit = {
            "log_id": "log123", "name": "Running", "value": 2.5, "unit": "km",
            "member_id": "member-alex", "logged_at": datetime(2026, 11, 1, 12, tzinfo=timezone.utc),
            "password": "never-send-this",  # Even extra input keys must not leak.
        }
        self.target = {"base_id": "appExample123", "table": "Habits"}
        poster = patch("airtable_api.requests.post")
        self.poster = poster.start()
        self.addCleanup(poster.stop)
        def fake_create(url, **kwargs):
            response = Mock(status_code=200)
            response.json.return_value = {"records": [{"id": "recMember", "fields": kwargs["json"]["records"][0]["fields"]}]}
            return response
        self.poster.side_effect = fake_create
        self.account = {"id": "member-alex", "name": "Alex Morgan", "email": "alex@example.com",
                        "password": "demo1234", "color": "#2563EB"}

    def test_accounts_are_read_from_members_not_habits_and_blank_rows_are_ignored(self):
        self.response.json.return_value = {"records": [
            {"id": "recBlank", "fields": {}}, {"id": "recMember", "fields": self.account},
        ]}
        self.assertEqual(read_accounts(self.path), [self.account])
        self.assertTrue(self.get.call_args.args[0].endswith("/Members"))
        self.assertEqual(self.get.call_args.kwargs["params"]["fields[]"], ["id", "name", "email", "password", "color"])
        self.poster.assert_not_called()

    def test_members_403_identifies_account_table_without_claiming_password_is_wrong(self):
        self.response.status_code = 403
        self.response.json.return_value = {
            "error": {"type": "INVALID_PERMISSIONS_OR_MODEL_NOT_FOUND", "message": "private server details"}
        }
        with self.assertRaises(AirtableError) as caught:
            read_accounts(self.path)
        message = str(caught.exception)
        self.assertIn("AIRTABLE_MEMBERS_TABLE", message)
        self.assertIn("table not found", message)
        self.assertIn("HTTP 403", message)
        self.assertNotIn("Incorrect email or password", message)
        self.assertNotIn("private server details", message)

    def test_signup_creates_only_five_members_fields_without_upserting_existing_email(self):
        self.assertEqual(create_account(self.account, self.path), self.account)
        self.assertTrue(self.poster.call_args.args[0].endswith("/Members"))
        self.assertEqual(self.poster.call_args.kwargs["json"], {"records": [{"fields": self.account}]})
        self.writer.assert_not_called()  # No activity upsert for account creation.

    def test_members_table_name_is_configurable_and_cannot_equal_habits(self):
        os.environ["AIRTABLE_MEMBERS_TABLE"] = "Family Members"
        create_account(self.account, self.path)
        self.assertTrue(self.poster.call_args.args[0].endswith("/Family%20Members"))
        os.environ["AIRTABLE_MEMBERS_TABLE"] = "Habits"
        with self.assertRaisesRegex(AirtableError, "separate Members"):
            read_accounts(self.path)

    def test_signup_timeout_does_not_expose_password_or_claim_success(self):
        self.poster.side_effect = requests.Timeout("fake-test-token demo1234")
        with self.assertRaises(AirtableError) as caught:
            create_account(self.account, self.path)
        self.assertNotIn("fake-test-token", str(caught.exception))
        self.assertNotIn("demo1234", str(caught.exception))
        self.assertIn("Try logging in", str(caught.exception))

    def test_signup_requires_matching_confirmation_fields(self):
        self.poster.side_effect = None
        self.poster.return_value = Mock(status_code=200)
        self.poster.return_value.json.return_value = {"records": [{"id": "recMember", "fields": {"id": "wrong"}}]}
        with self.assertRaises(AirtableError):
            create_account(self.account, self.path)

    def upload(self, habits=None):
        return upload_batch(
            habits if habits is not None else [self.habit],
            {"member-alex": "Alex Morgan"}, self.target, self.path,
        )

    def test_download_reads_every_page_and_requests_only_activity_fields(self):
        first = Mock(status_code=200)
        first.json.return_value = {"records": [{"id": "rec1", "fields": {}}], "offset": "nextPage"}
        second = Mock(status_code=200)
        second.json.return_value = {"records": [{"id": "rec2", "fields": {}}]}
        self.get.side_effect = [first, second]
        with patch("airtable_api.time.sleep") as pause:
            records = download_records(self.target, self.path)
        self.assertEqual([r["id"] for r in records], ["rec1", "rec2"])
        self.assertEqual(self.get.call_count, 2)
        first_params = self.get.call_args_list[0].kwargs["params"]
        second_params = self.get.call_args_list[1].kwargs["params"]
        self.assertEqual(first_params["pageSize"], 100)
        self.assertNotIn("offset", first_params)
        self.assertEqual(second_params["offset"], "nextPage")
        self.assertNotIn("password", first_params["fields[]"])
        self.assertEqual(len(first_params["fields[]"]), 7)
        pause.assert_called_once_with(0.25)
        self.writer.assert_not_called()

    def test_download_empty_table_is_valid(self):
        self.assertEqual(download_records(self.target, self.path), [])
        self.writer.assert_not_called()

    def test_failed_later_page_does_not_return_partial_history_or_secrets(self):
        first = Mock(status_code=200)
        first.json.return_value = {"records": [{"id": "rec1"}], "offset": "next"}
        self.get.side_effect = [first, requests.Timeout("fake-test-token")]
        with patch("airtable_api.time.sleep"):
            with self.assertRaises(AirtableError) as caught:
                download_records(self.target, self.path)
        self.assertNotIn("fake-test-token", str(caught.exception))
        self.assertIn("not changed", str(caught.exception))

    def test_invalid_or_repeated_page_offset_stops_download(self):
        for offset in ["", 5, "repeat"]:
            with self.subTest(offset=offset):
                response = Mock(status_code=200)
                response.json.return_value = {"records": [], "offset": offset}
                self.get.return_value = response
                with patch("airtable_api.time.sleep"):
                    with self.assertRaises(AirtableError):
                        download_records(self.target, self.path)

    def test_download_rejects_changed_destination_before_request(self):
        os.environ["AIRTABLE_TABLE_NAME"] = "Other table"
        with self.assertRaisesRegex(AirtableError, "destination changed"):
            download_records(self.target, self.path)
        self.get.assert_not_called()

    def test_upload_sends_only_seven_activity_fields_and_uses_upsert(self):
        self.assertEqual(self.upload(), {"log123": "rec0"})
        payload = self.writer.call_args.kwargs["json"]
        self.assertEqual(payload["performUpsert"], {"fieldsToMergeOn": ["LogID"]})
        self.assertEqual(payload["records"][0]["fields"], {
            "LogID": "log123", "MemberID": "member-alex", "MemberName": "Alex Morgan",
            "Activity": "Running", "Value": 2.5, "Unit": "km", "LoggedAt": "2026-11-01T12:00:00Z",
        })
        self.assertNotIn("never-send-this", str(payload))
        self.get.assert_not_called()

    def test_unknown_unit_and_owner_are_not_guessed(self):
        legacy = {"log_id": "old123", "name": "Running", "value": 5, "logged_at": self.habit["logged_at"]}
        self.upload([legacy])
        fields = self.writer.call_args.kwargs["json"]["records"][0]["fields"]
        self.assertEqual(fields["MemberID"], "")
        self.assertEqual(fields["MemberName"], "Unassigned")
        self.assertEqual(fields["Unit"], "unspecified")

    def test_destination_change_is_rejected_before_write(self):
        self.assertEqual(get_destination(self.path), self.target)
        os.environ["AIRTABLE_BASE_ID"] = "appChanged"
        with self.assertRaisesRegex(AirtableError, "destination changed"):
            self.upload()
        self.writer.assert_not_called()

    def test_missing_duplicate_log_ids_and_large_batches_are_rejected(self):
        for batch in [[], [dict(self.habit, log_id="")], [self.habit, self.habit], [self.habit] * 11]:
            with self.subTest(size=len(batch)):
                with self.assertRaises(AirtableError):
                    self.upload(batch)
        self.writer.assert_not_called()

    def test_upload_failure_does_not_expose_secrets(self):
        self.writer.side_effect = requests.Timeout("fake-test-token")
        with self.assertRaises(AirtableError) as caught:
            self.upload()
        self.assertIn("same LogIDs", str(caught.exception))
        self.assertNotIn("fake-test-token", str(caught.exception))

    def test_timeout_after_server_saved_record_is_safe_to_retry(self):
        # This fake server implements the same merge-by-LogID contract that
        # Airtable's performUpsert option requests. Lose its FIRST response.
        server = {}

        def fake_write(url, **kwargs):
            for record in kwargs["json"]["records"]:
                server[record["fields"]["LogID"]] = record["fields"]
            if self.writer.call_count == 1:
                raise requests.Timeout("response lost")
            response = Mock(status_code=200)
            response.json.return_value = {"records": [{"id": "rec123", "fields": server["log123"]}]}
            return response

        self.writer.side_effect = fake_write
        with self.assertRaises(AirtableError):
            self.upload()
        self.assertEqual(self.upload(), {"log123": "rec123"})
        self.assertEqual(len(server), 1)

    def test_upload_requires_confirmation_for_every_log_id(self):
        self.writer.side_effect = None
        for records in [[], [{"id": "rec123", "fields": {"LogID": "different"}}],
                        [{"id": "rec123", "fields": {"LogID": "log123"}}] * 2,
                        [{"fields": {"LogID": "log123"}}]]:
            self.writer.return_value = Mock(status_code=200)
            self.writer.return_value.json.return_value = {"records": records}
            with self.assertRaises(AirtableError):
                self.upload()

    def test_write_permission_or_schema_error_is_actionable(self):
        self.writer.side_effect = None
        for code in [403, 422, 429, 500]:
            with self.subTest(code=code):
                self.writer.return_value = Mock(status_code=code)
                with self.assertRaises(AirtableError) as caught:
                    self.upload()
                self.assertIn(str(code), str(caught.exception))

    def test_empty_table_proves_read_access(self):
        self.assertIn("connected", check_connection(self.path))
        self.get.assert_called_once_with(
            "https://api.airtable.com/v0/appExample123/Habits",
            headers={"Authorization": "Bearer fake-test-token"},
            params={"maxRecords": 1}, timeout=15, allow_redirects=False,
        )

    def test_existing_records_are_not_returned_or_displayed(self):
        self.response.json.return_value = {"records": [{"fields": {"Activity": "private activity"}}]}
        self.assertNotIn("private activity", check_connection(self.path))

    def test_missing_settings_fail_before_network_request(self):
        self.path.write_text("AIRTABLE_TABLE_NAME=Habits\n", encoding="utf-8")
        with self.assertRaisesRegex(AirtableError, "AIRTABLE_TOKEN"):
            check_connection(self.path)
        self.get.assert_not_called()

    def test_base_url_instead_of_id_is_rejected(self):
        os.environ["AIRTABLE_BASE_ID"] = "https://airtable.com/appExample123"
        with self.assertRaisesRegex(AirtableError, "not a URL"):
            check_connection(self.path)
        self.get.assert_not_called()

    def test_table_names_are_url_encoded(self):
        os.environ["AIRTABLE_TABLE_NAME"] = "Family Habits"
        check_connection(self.path)
        self.assertEqual(self.get.call_args.args[0], "https://api.airtable.com/v0/appExample123/Family%20Habits")

    def test_settings_are_reread_for_each_check(self):
        check_connection(self.path)
        self.path.write_text(
            "AIRTABLE_TOKEN=another-fake-token\nAIRTABLE_BASE_ID=appOther123\n",
            encoding="utf-8",
        )
        check_connection(self.path)
        self.assertIn("appOther123/Habits", self.get.call_args.args[0])
        self.assertEqual(self.get.call_args.kwargs["headers"]["Authorization"], "Bearer another-fake-token")

    def test_http_errors_have_helpful_messages_without_response_secrets(self):
        for code in [301, 401, 403, 404, 429, 500]:
            with self.subTest(code=code):
                self.response.status_code = code
                self.response.text = "fake-test-token and private data"
                with self.assertRaises(AirtableError) as caught:
                    check_connection(self.path)
                self.assertIn(str(code), str(caught.exception))
                self.assertNotIn("fake-test-token", str(caught.exception))

    def test_network_and_timeout_errors_do_not_expose_request_details(self):
        for error in [requests.Timeout("fake-test-token"), requests.ConnectionError("fake-test-token")]:
            with self.subTest(error=type(error).__name__):
                self.get.side_effect = error
                with self.assertRaises(AirtableError) as caught:
                    check_connection(self.path)
                self.assertNotIn("fake-test-token", str(caught.exception))

    def test_invalid_success_response_is_reported(self):
        for data in [None, [], {}, {"records": "not a list"}]:
            self.response.json.return_value = data
            with self.assertRaises(AirtableError):
                check_connection(self.path)
        self.response.json.side_effect = ValueError("invalid json")
        with self.assertRaises(AirtableError):
            check_connection(self.path)

    def test_unreadable_env_file_is_reported_without_details(self):
        with patch("airtable_api.dotenv_values", side_effect=OSError("private details")):
            with self.assertRaises(AirtableError) as caught:
                check_connection(self.path)
        self.assertNotIn("private details", str(caught.exception))
        self.get.assert_not_called()
