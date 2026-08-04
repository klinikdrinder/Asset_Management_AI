from __future__ import annotations

from types import SimpleNamespace
import os
import unittest
from unittest.mock import MagicMock, patch

from kdi_media.source_folders import (
    create_supabase_client_from_environment,
    extract_google_folder_id,
    normalize_google_folder_url,
    register_source_folder,
)


FOLDER_ID = "1AbC_def-234567890"
FOLDER_URL = f"https://drive.google.com/drive/folders/{FOLDER_ID}"


class GoogleDriveFolderUrlTests(unittest.TestCase):
    def test_valid_folder_url(self) -> None:
        self.assertEqual(normalize_google_folder_url(FOLDER_URL), FOLDER_URL)

    def test_url_with_drive_link_query_parameter(self) -> None:
        url = f"{FOLDER_URL}?usp=drive_link"
        self.assertEqual(normalize_google_folder_url(url), FOLDER_URL)

    def test_malformed_url(self) -> None:
        with self.assertRaisesRegex(ValueError, "HTTPS URL"):
            extract_google_folder_id("not-a-url")

    def test_non_folder_google_drive_url(self) -> None:
        with self.assertRaisesRegex(ValueError, "not a Google Drive folder"):
            extract_google_folder_id(
                f"https://drive.google.com/file/d/{FOLDER_ID}/view"
            )

    def test_folder_id_extraction(self) -> None:
        self.assertEqual(
            extract_google_folder_id(f"{FOLDER_URL}/?usp=sharing#details"),
            FOLDER_ID,
        )


class SourceFolderRegistrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.table = MagicMock()
        self.table.upsert.return_value.execute.return_value = SimpleNamespace(
            data=[{"id": "row-1", "google_folder_id": FOLDER_ID}]
        )
        self.client = MagicMock()
        self.client.table.return_value = self.table

    def test_duplicate_prevention_uses_google_folder_id_conflict_key(self) -> None:
        register_source_folder(
            self.client,
            source_name="Test Folder",
            account_name="example@gmail.com",
            folder_url=FOLDER_URL,
        )

        self.client.table.assert_called_once_with("source_folders")
        _, kwargs = self.table.upsert.call_args
        self.assertEqual(kwargs, {"on_conflict": "google_folder_id"})
        self.assertEqual(
            self.table.upsert.call_args.args[0]["google_folder_id"],
            FOLDER_ID,
        )

    def test_update_existing_folder_sends_explicit_editable_fields(self) -> None:
        register_source_folder(
            self.client,
            source_name="Renamed Folder",
            account_name="new@example.com",
            folder_url=f"{FOLDER_URL}?usp=drive_link",
            notes="Updated notes",
            active=False,
        )

        values = self.table.upsert.call_args.args[0]
        self.assertEqual(values["source_name"], "Renamed Folder")
        self.assertEqual(values["account_name"], "new@example.com")
        self.assertEqual(values["folder_url"], FOLDER_URL)
        self.assertEqual(values["notes"], "Updated notes")
        self.assertIs(values["active"], False)

    def test_preserves_operational_fields_when_not_supplied(self) -> None:
        register_source_folder(
            self.client,
            source_name="Test Folder",
            account_name="example@gmail.com",
            folder_url=FOLDER_URL,
        )

        values = self.table.upsert.call_args.args[0]
        operational_fields = {
            "access_status",
            "permission_role",
            "last_access_checked_at",
            "last_scan_at",
            "last_successful_scan_at",
            "notes",
            "active",
        }
        self.assertTrue(operational_fields.isdisjoint(values))


class EnvironmentTests(unittest.TestCase):
    @patch("kdi_media.source_folders.load_dotenv")
    @patch("kdi_media.source_folders.create_client")
    def test_missing_environment_variables(
        self,
        create_client: MagicMock,
        load_dotenv: MagicMock,
    ) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(
                ValueError,
                "Missing required environment variable: SUPABASE_URL",
            ):
                create_supabase_client_from_environment()
        create_client.assert_not_called()


if __name__ == "__main__":
    unittest.main()
