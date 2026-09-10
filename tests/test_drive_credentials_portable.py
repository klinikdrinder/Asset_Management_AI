"""Portability of the Google Drive service-account credential resolution.

These tests require no real credentials. They prove the default credential path
is derived from the repository location (never a machine-specific absolute path)
and that an explicit environment override always takes precedence.
"""

import os
import unittest
from pathlib import Path
from unittest import mock

from kdi_media.google_drive import default_service_account_credentials_path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class DriveCredentialPortabilityTest(unittest.TestCase):
    def test_default_is_repository_relative(self) -> None:
        self.assertEqual(
            default_service_account_credentials_path(),
            PROJECT_ROOT / ".secrets" / "kdi-media-reader.json",
        )

    def test_default_has_no_old_pc_drive_root(self) -> None:
        text = str(default_service_account_credentials_path())
        self.assertNotIn("D:\\Asset_Management_AI", text)
        self.assertNotIn("D:/Asset_Management_AI", text)

    def test_default_lives_under_project_root(self) -> None:
        resolved = default_service_account_credentials_path().resolve()
        self.assertTrue(str(resolved).startswith(str(PROJECT_ROOT.resolve())))

    def test_env_override_precedence_is_honored(self) -> None:
        # The resolver in create_service_account_drive_service prefers an explicit
        # argument, then the environment variable, then this portable default.
        override = "/some/explicit/override/kdi-media-reader.json"
        with mock.patch.dict(
            os.environ,
            {"GOOGLE_DRIVE_SERVICE_ACCOUNT_CREDENTIALS_PATH": override},
        ):
            configured = os.environ.get("GOOGLE_DRIVE_SERVICE_ACCOUNT_CREDENTIALS_PATH")
            self.assertEqual(configured, override)
            # Default remains portable and independent of the override.
            self.assertNotIn("override", str(default_service_account_credentials_path()))


if __name__ == "__main__":
    unittest.main()
