from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from googleapiclient.errors import HttpError

from kdi_media.google_drive import (
    ACCESSIBLE_STATUS,
    DRIVE_DESTINATION_WRITE_SCOPE,
    DRIVE_DESTINATION_WRITE_SCOPES,
    DRIVE_READONLY_SCOPE,
    DRIVE_READONLY_SCOPES,
    DriveCredentialProfile,
    FOLDER_MIME_TYPE,
    INACCESSIBLE_ITEM_CLASSIFICATION,
    SUPPORTED_FILE_CLASSIFICATION,
    UNSUPPORTED_FILE_CLASSIFICATION,
    GoogleDriveAccessError,
    GoogleDriveAuthenticationError,
    GoogleDriveConfigurationError,
    GoogleDriveNotFolderError,
    GoogleDriveOAuthConfig,
    create_destination_write_drive_service,
    create_readonly_drive_service,
    get_item_metadata,
    list_immediate_children,
    load_destination_oauth_config,
    load_destination_write_credentials,
    load_oauth_config,
    load_readonly_credentials,
    require_expected_account,
    require_write_profile,
    scan_folder_recursive,
    verify_folder_access,
)


FOLDER_ID = "folder-123"


def api_item(
    item_id: str = FOLDER_ID,
    *,
    name: str = "Test Folder",
    mime_type: str = FOLDER_MIME_TYPE,
    extension: str | None = None,
    parent: str = "parent-1",
) -> dict[str, object]:
    result: dict[str, object] = {
        "id": item_id,
        "name": name,
        "mimeType": mime_type,
        "createdTime": "2026-07-28T00:00:00Z",
        "modifiedTime": "2026-07-29T00:00:00Z",
        "parents": [parent],
        "driveId": "shared-drive-1",
        "webViewLink": "https://drive.google.com/example",
    }
    if extension is not None:
        result["fileExtension"] = extension
    if (
        mime_type != FOLDER_MIME_TYPE
        and not mime_type.startswith("application/vnd.google-apps.")
    ):
        result["size"] = "1"
    return result


def valid_credentials(
    *,
    expired: bool = False,
    scopes: tuple[str, ...] = DRIVE_READONLY_SCOPES,
) -> MagicMock:
    credentials = MagicMock()
    credentials.valid = not expired
    credentials.expired = expired
    credentials.refresh_token = "present" if expired else None
    credentials.granted_scopes = list(scopes)
    credentials.scopes = list(scopes)
    credentials.has_scopes.return_value = True
    credentials.to_json.return_value = '{"redacted":"test-token"}'
    return credentials


class ConfigurationTests(unittest.TestCase):
    def test_missing_credentials_file_configuration(self) -> None:
        with self.assertRaisesRegex(
            GoogleDriveConfigurationError,
            "GOOGLE_DRIVE_CREDENTIALS_FILE",
        ):
            load_oauth_config(
                {"GOOGLE_DRIVE_TOKEN_FILE": "token.json"}
            )

    def test_missing_token_file_configuration(self) -> None:
        with self.assertRaisesRegex(
            GoogleDriveConfigurationError,
            "GOOGLE_DRIVE_TOKEN_FILE",
        ):
            load_oauth_config(
                {"GOOGLE_DRIVE_CREDENTIALS_FILE": "credentials.json"}
            )

    def test_missing_credentials_file(self) -> None:
        config = GoogleDriveOAuthConfig(
            Path("does-not-exist-credentials.json"),
            Path("does-not-exist-token.json"),
        )
        with self.assertRaisesRegex(
            GoogleDriveConfigurationError,
            "credentials file is missing",
        ):
            load_readonly_credentials(config)


class AuthenticationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_directory = tempfile.TemporaryDirectory()
        root = Path(self.temp_directory.name)
        self.credentials_file = root / "credentials.json"
        self.token_file = root / "token.json"
        self.credentials_file.write_text("{}", encoding="utf-8")
        self.config = GoogleDriveOAuthConfig(
            self.credentials_file,
            self.token_file,
        )

    def tearDown(self) -> None:
        self.temp_directory.cleanup()

    @patch("kdi_media.google_drive.Credentials.from_authorized_user_file")
    def test_valid_token_reuse(self, from_file: MagicMock) -> None:
        self.token_file.write_text("{}", encoding="utf-8")
        credentials = valid_credentials()
        from_file.return_value = credentials

        result = load_readonly_credentials(self.config)

        self.assertIs(result, credentials)
        credentials.refresh.assert_not_called()
        from_file.assert_called_once_with(
            str(self.token_file),
            scopes=list(DRIVE_READONLY_SCOPES),
        )

    @patch("kdi_media.google_drive.Request")
    @patch("kdi_media.google_drive.Credentials.from_authorized_user_file")
    def test_expired_token_refresh(
        self,
        from_file: MagicMock,
        request_type: MagicMock,
    ) -> None:
        self.token_file.write_text("{}", encoding="utf-8")
        credentials = valid_credentials(expired=True)
        from_file.return_value = credentials

        result = load_readonly_credentials(self.config)

        self.assertIs(result, credentials)
        credentials.refresh.assert_called_once_with(
            request_type.return_value
        )
        self.assertTrue(self.token_file.is_file())

    @patch("kdi_media.google_drive.InstalledAppFlow")
    def test_oauth_flow_when_no_token_exists(
        self,
        flow_type: MagicMock,
    ) -> None:
        credentials = valid_credentials()
        flow_type.from_client_secrets_file.return_value.run_local_server.return_value = (
            credentials
        )

        result = load_readonly_credentials(self.config)

        self.assertIs(result, credentials)
        flow_type.from_client_secrets_file.assert_called_once_with(
            str(self.credentials_file),
            scopes=[DRIVE_READONLY_SCOPE],
        )
        flow_type.from_client_secrets_file.return_value.run_local_server.assert_called_once_with(
            port=0,
            authorization_prompt_message="",
        )
        self.assertTrue(self.token_file.is_file())

    @patch("kdi_media.google_drive.build")
    @patch("kdi_media.google_drive.load_readonly_credentials")
    def test_service_uses_authenticated_credentials(
        self,
        load_credentials: MagicMock,
        build: MagicMock,
    ) -> None:
        credentials = valid_credentials()
        load_credentials.return_value = credentials

        service = create_readonly_drive_service(self.config)

        self.assertIs(service, build.return_value)
        build.assert_called_once_with(
            "drive",
            "v3",
            credentials=credentials,
            cache_discovery=False,
        )

    def test_only_drive_readonly_scope_is_configured(self) -> None:
        self.assertEqual(
            DRIVE_READONLY_SCOPES,
            ("https://www.googleapis.com/auth/drive.readonly",),
        )


class CredentialProfileIsolationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_directory = tempfile.TemporaryDirectory()
        root = Path(self.temp_directory.name)
        self.credentials_file = root / "credentials.json"
        self.source_token = root / "source-token.json"
        self.destination_token = root / "destination-token.json"
        self.credentials_file.write_text("{}", encoding="utf-8")
        self.environment = {
            "GOOGLE_DRIVE_CREDENTIALS_FILE": str(self.credentials_file),
            "GOOGLE_DRIVE_TOKEN_FILE": str(self.source_token),
            "GOOGLE_DRIVE_DESTINATION_TOKEN_FILE": str(
                self.destination_token
            ),
        }

    def tearDown(self) -> None:
        self.temp_directory.cleanup()

    def test_profile_token_paths_are_explicit_and_distinct(self) -> None:
        source = load_oauth_config(self.environment)
        destination = load_destination_oauth_config(self.environment)
        self.assertEqual(source.token_file, self.source_token)
        self.assertEqual(destination.token_file, self.destination_token)
        self.assertNotEqual(source.token_file, destination.token_file)

    def test_destination_profile_rejects_source_token_path(self) -> None:
        environment = dict(self.environment)
        environment["GOOGLE_DRIVE_DESTINATION_TOKEN_FILE"] = str(
            self.source_token
        )
        with self.assertRaisesRegex(
            GoogleDriveConfigurationError,
            "must differ",
        ):
            load_destination_oauth_config(environment)

    def test_missing_destination_token_configuration_is_safe(self) -> None:
        environment = dict(self.environment)
        del environment["GOOGLE_DRIVE_DESTINATION_TOKEN_FILE"]
        with self.assertRaisesRegex(
            GoogleDriveConfigurationError,
            "GOOGLE_DRIVE_DESTINATION_TOKEN_FILE",
        ):
            load_destination_oauth_config(environment)

    def test_source_profile_rejected_for_write_required_work(self) -> None:
        with self.assertRaisesRegex(
            GoogleDriveConfigurationError,
            "requires destination_write",
        ):
            require_write_profile(DriveCredentialProfile.SOURCE_READONLY)

    def test_destination_profile_is_explicitly_accepted(self) -> None:
        require_write_profile(DriveCredentialProfile.DESTINATION_WRITE)

    @patch("kdi_media.google_drive.Credentials.from_authorized_user_file")
    def test_destination_token_scope_validation_passes(
        self,
        from_file: MagicMock,
    ) -> None:
        self.destination_token.write_text("{}", encoding="utf-8")
        credentials = valid_credentials(
            scopes=DRIVE_DESTINATION_WRITE_SCOPES
        )
        from_file.return_value = credentials
        config = load_destination_oauth_config(self.environment)

        result = load_destination_write_credentials(config)

        self.assertIs(result, credentials)
        from_file.assert_called_once_with(
            str(self.destination_token),
            scopes=[DRIVE_DESTINATION_WRITE_SCOPE],
        )

    @patch("kdi_media.google_drive.Credentials.from_authorized_user_file")
    def test_destination_scope_mismatch_is_rejected(
        self,
        from_file: MagicMock,
    ) -> None:
        self.destination_token.write_text("{}", encoding="utf-8")
        credentials = valid_credentials(scopes=DRIVE_READONLY_SCOPES)
        from_file.return_value = credentials
        config = load_destination_oauth_config(self.environment)

        with self.assertRaisesRegex(
            GoogleDriveAuthenticationError,
            "scope does not match",
        ):
            load_destination_write_credentials(config)

    @patch("kdi_media.google_drive.build")
    @patch("kdi_media.google_drive.load_destination_write_credentials")
    def test_destination_service_uses_only_destination_credentials(
        self,
        load_credentials: MagicMock,
        build: MagicMock,
    ) -> None:
        credentials = valid_credentials(
            scopes=DRIVE_DESTINATION_WRITE_SCOPES
        )
        load_credentials.return_value = credentials
        config = GoogleDriveOAuthConfig(
            self.credentials_file,
            self.destination_token,
        )

        service = create_destination_write_drive_service(config)

        self.assertIs(service, build.return_value)
        build.assert_called_once_with(
            "drive",
            "v3",
            credentials=credentials,
            cache_discovery=False,
        )

    def test_wrong_account_detection(self) -> None:
        service = MagicMock()
        service.about.return_value.get.return_value.execute.return_value = {
            "user": {"emailAddress": "wrong@example.com"}
        }
        with self.assertRaisesRegex(
            GoogleDriveAuthenticationError,
            "does not match",
        ):
            require_expected_account(service)

    def test_profile_code_does_not_log_token_contents(self) -> None:
        import inspect
        import kdi_media.google_drive as module

        source = inspect.getsource(module)
        self.assertNotIn("print(credentials", source)
        self.assertNotIn("print(token", source)


class MetadataTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = MagicMock()
        self.files = self.service.files.return_value

    def test_folder_metadata_retrieval(self) -> None:
        self.files.get.return_value.execute.return_value = api_item()

        folder = get_item_metadata(self.service, FOLDER_ID)

        self.assertEqual(folder.id, FOLDER_ID)
        self.assertEqual(folder.name, "Test Folder")
        self.files.get.assert_called_once()
        request = self.files.get.call_args.kwargs
        self.assertEqual(request["fileId"], FOLDER_ID)
        self.assertTrue(request["supportsAllDrives"])
        self.assertNotIn("alt", request)

    def test_rejects_non_folder_item(self) -> None:
        self.files.get.return_value.execute.return_value = api_item(
            mime_type="video/mp4"
        )

        with self.assertRaises(GoogleDriveNotFolderError):
            verify_folder_access(self.service, FOLDER_ID)

    def test_access_denied_handling(self) -> None:
        response = SimpleNamespace(status=403, reason="Forbidden")
        self.files.get.return_value.execute.side_effect = HttpError(
            response,
            b'{"error":{"message":"forbidden"}}',
        )

        with self.assertRaisesRegex(
            GoogleDriveAccessError,
            "is not accessible",
        ):
            get_item_metadata(self.service, FOLDER_ID)

    def test_immediate_child_pagination(self) -> None:
        first_request = MagicMock()
        first_request.execute.return_value = {
            "files": [api_item("child-1", name="One")],
            "nextPageToken": "page-2",
        }
        second_request = MagicMock()
        second_request.execute.return_value = {
            "files": [api_item("child-2", name="Two")],
        }
        self.files.list.side_effect = [first_request, second_request]

        listing = list_immediate_children(self.service, FOLDER_ID)

        self.assertEqual(
            [item.id for item in listing.children],
            ["child-1", "child-2"],
        )
        self.assertEqual(listing.page_count, 2)
        self.assertTrue(listing.pagination_used)
        self.assertEqual(self.files.list.call_count, 2)
        self.assertIsNone(
            self.files.list.call_args_list[0].kwargs["pageToken"]
        )
        self.assertEqual(
            self.files.list.call_args_list[1].kwargs["pageToken"],
            "page-2",
        )

    def test_listing_uses_shared_drive_flags(self) -> None:
        self.files.list.return_value.execute.return_value = {"files": []}

        listing = list_immediate_children(self.service, FOLDER_ID)

        self.assertEqual(listing.children, ())
        request = self.files.list.call_args.kwargs
        self.assertTrue(request["includeItemsFromAllDrives"])
        self.assertTrue(request["supportsAllDrives"])
        self.assertEqual(request["spaces"], "drive")
        self.assertEqual(
            request["q"],
            f"'{FOLDER_ID}' in parents and trashed = false",
        )


class RecursiveScanTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = MagicMock()
        self.files = self.service.files.return_value
        self.files.get.return_value.execute.return_value = api_item()

    @staticmethod
    def page(
        items: list[dict[str, object]],
        *,
        next_token: str | None = None,
    ) -> MagicMock:
        request = MagicMock()
        response: dict[str, object] = {"files": items}
        if next_token is not None:
            response["nextPageToken"] = next_token
        request.execute.return_value = response
        return request

    def test_multiple_levels_empty_folder_and_paths(self) -> None:
        self.files.list.side_effect = [
            self.page(
                [
                    api_item(
                        "folder-a",
                        name="Level A",
                        parent=FOLDER_ID,
                    ),
                    api_item(
                        "root-image",
                        name="root.jpg",
                        mime_type="image/jpeg",
                        extension="jpg",
                        parent=FOLDER_ID,
                    ),
                ]
            ),
            self.page(
                [
                    api_item(
                        "folder-b",
                        name="Level B",
                        parent="folder-a",
                    )
                ]
            ),
            self.page([]),
        ]

        report = scan_folder_recursive(self.service, FOLDER_ID)
        by_id = {item.file_id: item for item in report.items}

        self.assertEqual(report.summary.folders_scanned, 3)
        self.assertEqual(by_id["folder-a"].relative_folder_path, "Level A")
        self.assertEqual(
            by_id["folder-b"].relative_folder_path,
            "Level A/Level B",
        )
        self.assertEqual(
            by_id["root-image"].relative_folder_path,
            "",
        )
        self.assertEqual(
            by_id["root-image"].accessibility_status,
            ACCESSIBLE_STATUS,
        )

    def test_recursive_pagination_is_independent_per_folder(self) -> None:
        self.files.list.side_effect = [
            self.page(
                [api_item("folder-a", name="A", parent=FOLDER_ID)],
                next_token="root-page-2",
            ),
            self.page(
                [
                    api_item(
                        "root-file",
                        name="root.png",
                        mime_type="image/png",
                        extension="png",
                        parent=FOLDER_ID,
                    )
                ]
            ),
            self.page(
                [
                    api_item(
                        "nested-1",
                        name="one.mp4",
                        mime_type="video/mp4",
                        extension="mp4",
                        parent="folder-a",
                    )
                ],
                next_token="nested-page-2",
            ),
            self.page(
                [
                    api_item(
                        "nested-2",
                        name="two.mov",
                        mime_type="video/quicktime",
                        extension="mov",
                        parent="folder-a",
                    )
                ]
            ),
        ]

        report = scan_folder_recursive(self.service, FOLDER_ID)

        self.assertEqual(report.summary.api_pages_requested, 4)
        tokens = [
            call.kwargs["pageToken"]
            for call in self.files.list.call_args_list
        ]
        self.assertEqual(
            tokens,
            [None, "root-page-2", None, "nested-page-2"],
        )

    def test_supported_unsupported_and_google_native_classification(
        self,
    ) -> None:
        supported = [
            ("jpg", "image/jpeg"),
            ("jpeg", "image/jpeg"),
            ("png", "image/png"),
            ("webp", "image/webp"),
            ("mp4", "video/mp4"),
            ("mov", "video/quicktime"),
            ("pdf", "application/pdf"),
            (
                "pptx",
                "application/vnd.openxmlformats-officedocument."
                "presentationml.presentation",
            ),
        ]
        items = [
            api_item(
                f"supported-{extension}",
                name=f"asset.{extension}",
                mime_type=mime_type,
                extension=extension.upper(),
                parent=FOLDER_ID,
            )
            for extension, mime_type in supported
        ]
        items.extend(
            [
                api_item(
                    "sheet",
                    name="Native Sheet",
                    mime_type="application/vnd.google-apps.spreadsheet",
                    parent=FOLDER_ID,
                ),
            ]
        )
        self.files.list.return_value = self.page(items)

        report = scan_folder_recursive(self.service, FOLDER_ID)
        by_id = {item.file_id: item for item in report.items}

        self.assertEqual(report.summary.supported_files, 8)
        self.assertEqual(report.summary.unsupported_files, 1)
        self.assertEqual(
            by_id["supported-jpg"].classification,
            SUPPORTED_FILE_CLASSIFICATION,
        )
        self.assertEqual(
            by_id["supported-pdf"].classification,
            SUPPORTED_FILE_CLASSIFICATION,
        )
        self.assertEqual(
            by_id["supported-pptx"].classification,
            SUPPORTED_FILE_CLASSIFICATION,
        )
        self.assertEqual(
            by_id["sheet"].classification,
            UNSUPPORTED_FILE_CLASSIFICATION,
        )

    def test_repeated_folder_id_is_traversed_once(self) -> None:
        repeated = api_item(
            "same-folder",
            name="Repeated",
            parent=FOLDER_ID,
        )
        self.files.list.side_effect = [
            self.page([repeated, repeated]),
            self.page([]),
        ]

        report = scan_folder_recursive(self.service, FOLDER_ID)

        self.assertEqual(self.files.list.call_count, 2)
        self.assertEqual(report.summary.folders_scanned, 2)

    def test_invalid_item_metadata_records_error_and_continues(self) -> None:
        self.files.list.return_value = self.page(
            [
                {
                    "id": "bad-size",
                    "name": "bad.jpg",
                    "mimeType": "image/jpeg",
                    "fileExtension": "jpg",
                    "size": "not-a-number",
                },
                api_item(
                    "good-file",
                    name="good.png",
                    mime_type="image/png",
                    extension="png",
                    parent=FOLDER_ID,
                ),
            ]
        )

        report = scan_folder_recursive(self.service, FOLDER_ID)
        by_id = {item.file_id: item for item in report.items}

        self.assertEqual(
            by_id["bad-size"].classification,
            INACCESSIBLE_ITEM_CLASSIFICATION,
        )
        self.assertEqual(
            by_id["good-file"].classification,
            SUPPORTED_FILE_CLASSIFICATION,
        )
        self.assertEqual(report.summary.errors, 1)
        self.assertEqual(
            report.errors[0].failure_category,
            "item_metadata_invalid",
        )

    def test_inaccessible_nested_folder_is_sanitized_and_scan_continues(
        self,
    ) -> None:
        first = self.page(
            [
                api_item(
                    "blocked-folder",
                    name="Blocked",
                    parent=FOLDER_ID,
                ),
                api_item(
                    "open-folder",
                    name="Open",
                    parent=FOLDER_ID,
                ),
            ]
        )
        denied = MagicMock()
        denied.execute.side_effect = HttpError(
            SimpleNamespace(status=403, reason="Forbidden"),
            b'{"error":{"message":"sensitive raw response"}}',
        )
        open_page = self.page(
            [
                api_item(
                    "open-file",
                    name="open.webp",
                    mime_type="image/webp",
                    extension="webp",
                    parent="open-folder",
                )
            ]
        )
        self.files.list.side_effect = [first, denied, open_page]

        report = scan_folder_recursive(self.service, FOLDER_ID)
        by_id = {item.file_id: item for item in report.items}

        self.assertEqual(
            by_id["blocked-folder"].classification,
            INACCESSIBLE_ITEM_CLASSIFICATION,
        )
        self.assertEqual(
            by_id["open-file"].classification,
            SUPPORTED_FILE_CLASSIFICATION,
        )
        self.assertEqual(report.errors[0].http_status, 403)
        self.assertEqual(
            report.errors[0].message,
            "Nested folder metadata could not be listed",
        )
        self.assertNotIn("sensitive", report.errors[0].message)

    def test_recursive_requests_use_shared_drive_metadata_only_fields(
        self,
    ) -> None:
        self.files.list.return_value = self.page([])

        scan_folder_recursive(self.service, FOLDER_ID)

        get_request = self.files.get.call_args.kwargs
        list_request = self.files.list.call_args.kwargs
        self.assertTrue(get_request["supportsAllDrives"])
        self.assertTrue(list_request["includeItemsFromAllDrives"])
        self.assertTrue(list_request["supportsAllDrives"])
        self.assertEqual(list_request["spaces"], "drive")
        self.assertIn("fileExtension", list_request["fields"])
        self.assertIn("createdTime", list_request["fields"])
        self.assertNotIn("permissions", list_request["fields"])
        self.assertNotIn("content", list_request["fields"])
        self.files.get.assert_called_once()
        self.files.list.assert_called_once()


if __name__ == "__main__":
    unittest.main()
    load_destination_oauth_config,
    load_destination_write_credentials,
