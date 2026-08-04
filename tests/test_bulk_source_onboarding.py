from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from scripts.onboard_source_folders import (
    SourceManifestRow,
    execute_plan,
    parse_manifest,
    plan_onboarding,
)


HEADER = (
    "source_name,account_name,folder_url,notes,active,"
    "expected_folder_id,clinical_content,processing_enabled\n"
)


class FakeRepository:
    def __init__(self) -> None:
        self.registered: list[str] = []

    def register(self, row: SourceManifestRow):
        self.registered.append(row.google_folder_id)
        return {"google_folder_id": row.google_folder_id}


class BulkSourceOnboardingTests(unittest.TestCase):
    def _parse(self, body: str):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sources.csv"
            path.write_text(HEADER + body, encoding="utf-8")
            return parse_manifest(path)

    def test_valid_csv_is_normalized(self) -> None:
        rows, rejected = self._parse(
            " Example , account ,"
            "https://drive.google.com/drive/folders/FOLDER_A?usp=sharing,"
            " Notes ,true,FOLDER_A,false,true\n"
        )
        self.assertFalse(rejected)
        self.assertEqual(rows[0].source_name, "Example")
        self.assertEqual(rows[0].google_folder_id, "FOLDER_A")
        self.assertEqual(
            rows[0].folder_url,
            "https://drive.google.com/drive/folders/FOLDER_A",
        )

    def test_invalid_folder_url_rejects_only_row(self) -> None:
        rows, rejected = self._parse(
            "Bad,account,https://example.com/folder/x,,true,,, \n"
            "Good,account,https://drive.google.com/drive/folders/GOOD,,"
            "true,GOOD,,\n"
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(len(rejected), 1)
        self.assertEqual(rejected[0].row_number, 2)

    def test_missing_source_name_is_rejected(self) -> None:
        rows, rejected = self._parse(
            ",account,https://drive.google.com/drive/folders/GOOD,,"
            "true,GOOD,,\n"
        )
        self.assertFalse(rows)
        self.assertIn("source name", rejected[0].reason.lower())

    def test_duplicate_folder_id_in_csv_is_rejected(self) -> None:
        rows, rejected = self._parse(
            "One,a,https://drive.google.com/drive/folders/SAME,,true,SAME,,\n"
            "Two,b,https://drive.google.com/drive/folders/SAME,,true,SAME,,\n"
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(len(rejected), 1)
        self.assertIn("Duplicate", rejected[0].reason)

    def test_existing_source_unchanged_and_new_source_insert(self) -> None:
        rows, rejected = self._parse(
            "One,a,https://drive.google.com/drive/folders/ONE,Note,true,ONE,,\n"
            "Two,b,https://drive.google.com/drive/folders/TWO,,true,TWO,,\n"
        )
        self.assertFalse(rejected)
        existing = [
            {
                "google_folder_id": "ONE",
                "source_name": "One",
                "account_name": "a",
                "folder_url": (
                    "https://drive.google.com/drive/folders/ONE"
                ),
                "notes": "Note",
                "active": True,
            }
        ]
        plan = plan_onboarding(rows, existing)
        self.assertEqual(
            [item.action for item in plan], ["UNCHANGED", "INSERT"]
        )

    def test_changed_existing_source_proposes_update(self) -> None:
        rows, _ = self._parse(
            "One,a,https://drive.google.com/drive/folders/ONE,New,true,ONE,,\n"
        )
        plan = plan_onboarding(
            rows,
            [
                {
                    "google_folder_id": "ONE",
                    "source_name": "One",
                    "account_name": "a",
                    "folder_url": (
                        "https://drive.google.com/drive/folders/ONE"
                    ),
                    "notes": "Old",
                    "active": True,
                }
            ],
        )
        self.assertEqual(plan[0].action, "UPDATE")

    def test_repeated_onboarding_becomes_unchanged(self) -> None:
        rows, _ = self._parse(
            "One,a,https://drive.google.com/drive/folders/ONE,,true,ONE,,\n"
        )
        first = plan_onboarding(rows, [])
        repository = FakeRepository()
        changed, failed = execute_plan(
            first, repository, continue_on_error=False
        )
        self.assertEqual((changed, failed), (1, 0))
        current = {
            **rows[0].registration_values(),
            "google_folder_id": "ONE",
        }
        second = plan_onboarding(rows, [current])
        self.assertEqual(second[0].action, "UNCHANGED")
        changed, failed = execute_plan(
            second, repository, continue_on_error=False
        )
        self.assertEqual((changed, failed), (0, 0))
        self.assertEqual(repository.registered, ["ONE"])


if __name__ == "__main__":
    unittest.main()
