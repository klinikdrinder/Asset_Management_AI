from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import sys
import unittest
from uuid import uuid4


SCRIPT = Path("scripts/run_step10_upload_worker.py")
ROOT = "1CdmowWV5TAk5R9D5yl2cOT8Plx3ihZgl"
PROFILES = [
    "--source-profile", "source_readonly",
    "--destination-profile", "destination_write",
]


class Step10CliTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("step10_cli", SCRIPT)
        cls.module = importlib.util.module_from_spec(spec)
        assert spec.loader
        spec.loader.exec_module(cls.module)

    def test_import_has_no_effects(self):
        self.assertTrue(callable(self.module.main))

    def test_dry_run_makes_no_production_calls(self):
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--limit", "8",
                "--destination-folder-id", ROOT,
                *PROFILES,
                "--dry-run",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn('"database_writes": 0', result.stdout)
        self.assertIn('"drive_requests": 0', result.stdout)

    def test_execute_requires_destination_confirmation(self):
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--limit", "1",
                "--destination-folder-id", ROOT,
                *PROFILES,
                "--execute",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("confirm-destination", result.stderr)

    def test_wrong_root_and_invalid_limit_refused(self):
        for arguments in (
            ["--limit", "0", "--destination-folder-id", ROOT, *PROFILES],
            ["--limit", "1", "--destination-folder-id", "wrong", *PROFILES],
        ):
            result = subprocess.run(
                [sys.executable, str(SCRIPT), *arguments],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(result.returncode, 0)

    def test_asset_id_validation(self):
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--limit", "1",
                "--asset-id", "not-a-uuid",
                "--destination-folder-id", ROOT,
                *PROFILES,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)

    def test_profiles_must_be_explicit(self):
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--limit", "1",
                "--destination-folder-id", ROOT,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("--source-profile", result.stderr)

    def test_exact_lifecycle_allowlist_is_validated(self):
        lifecycle_ids = [str(uuid4()) for _ in range(3)]
        arguments = [
            sys.executable,
            str(SCRIPT),
            "--limit", "3",
            "--destination-folder-id", ROOT,
            *PROFILES,
            "--dry-run",
        ]
        for lifecycle_id in lifecycle_ids:
            arguments.extend(["--asset-destination-id", lifecycle_id])
        result = subprocess.run(
            arguments,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn('"lifecycle_allowlist_count": 3', result.stdout)

    def test_invalid_lifecycle_allowlist_id_is_rejected(self):
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--limit", "1",
                "--destination-folder-id", ROOT,
                *PROFILES,
                "--asset-destination-id", "not-a-uuid",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)

    def test_explicit_empty_allowlist_is_distinct_from_null(self):
        base = [
            sys.executable,
            str(SCRIPT),
            "--limit", "1",
            "--destination-folder-id", ROOT,
            *PROFILES,
            "--dry-run",
        ]
        unscoped = subprocess.run(
            base,
            capture_output=True,
            text=True,
            check=False,
        )
        empty = subprocess.run(
            [*base, "--empty-asset-destination-allowlist"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(unscoped.returncode, 0)
        self.assertEqual(empty.returncode, 0)
        self.assertIn('"lifecycle_allowlist_count": null', unscoped.stdout)
        self.assertIn('"lifecycle_allowlist_count": 0', empty.stdout)


if __name__ == "__main__":
    unittest.main()
