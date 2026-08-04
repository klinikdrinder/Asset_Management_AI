from __future__ import annotations

from dataclasses import FrozenInstanceError
import unittest

from kdi_media.rules import (
    FORMAT_POLICY,
    RULE_VERSION,
    FileRuleInput,
    ReasonCode,
    RuleConfiguration,
    evaluate_file,
)


MIME = {
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
    "mp4": "video/mp4",
    "mov": "video/quicktime",
    "pdf": "application/pdf",
    "pptx": (
        "application/vnd.openxmlformats-officedocument."
        "presentationml.presentation"
    ),
}


def item(
    extension: object = "jpg",
    mime_type: object = "image/jpeg",
    **overrides: object,
) -> FileRuleInput:
    values: dict[str, object] = {
        "file_name": f"asset.{extension}" if extension else "asset",
        "mime_type": mime_type,
        "file_extension": extension,
        "size_bytes": 10,
        "relative_path": "Folder/Subfolder",
        "accessibility_status": "accessible",
        "trashed": False,
        "is_missing": False,
        "is_folder": False,
    }
    values.update(overrides)
    return FileRuleInput(**values)


class FormatPolicyTests(unittest.TestCase):
    def test_exact_eight_format_registry(self) -> None:
        self.assertEqual(set(FORMAT_POLICY), set(MIME))
        for extension, mime_type in MIME.items():
            policy = FORMAT_POLICY[extension]
            self.assertEqual(policy.required_mime_type, mime_type)
            self.assertTrue(policy.accepted_for_inventory)
            self.assertTrue(policy.accepted_for_migration)
            self.assertTrue(policy.accepted_for_duplicate_detection)

    def test_document_ai_analysis_is_disabled(self) -> None:
        self.assertFalse(FORMAT_POLICY["pdf"].accepted_for_ai_analysis)
        self.assertFalse(FORMAT_POLICY["pptx"].accepted_for_ai_analysis)

    def test_registry_and_results_are_immutable(self) -> None:
        with self.assertRaises(TypeError):
            FORMAT_POLICY["gif"] = FORMAT_POLICY["jpg"]  # type: ignore[index]
        result = evaluate_file(item())
        with self.assertRaises(FrozenInstanceError):
            result.automatic_decision = "SKIP"  # type: ignore[misc]


class DecisionRuleTests(unittest.TestCase):
    def assert_reason(
        self,
        value: FileRuleInput,
        reason: ReasonCode,
        decision: str = "SKIP",
        status: str = "SKIPPED",
        *,
        configuration: RuleConfiguration = RuleConfiguration(),
    ) -> None:
        result = evaluate_file(value, configuration=configuration)
        self.assertEqual(result.reason_code, reason)
        self.assertEqual(result.automatic_decision, decision)
        self.assertEqual(result.target_processing_status, status)
        self.assertEqual(result.rule_version, RULE_VERSION)

    def test_all_supported_pairs(self) -> None:
        for extension, mime_type in MIME.items():
            with self.subTest(extension=extension):
                result = evaluate_file(item(extension, mime_type))
                self.assertEqual(result.automatic_decision, "TAKE")
                self.assertEqual(result.reason_code, ReasonCode.SUPPORTED_FORMAT)

    def test_uppercase_and_leading_dot_extensions(self) -> None:
        for extension in ("PDF", ".PPTX"):
            normalized = extension.lower().lstrip(".")
            result = evaluate_file(item(extension, MIME[normalized]))
            self.assertEqual(result.automatic_decision, "TAKE")
            self.assertEqual(result.normalized_extension, normalized)

    def test_heic_is_unsupported(self) -> None:
        self.assert_reason(
            item("heic", "image/heif"),
            ReasonCode.UNSUPPORTED_EXTENSION,
        )

    def test_google_native_types_and_shortcut(self) -> None:
        types = {
            "application/vnd.google-apps.document":
                ReasonCode.GOOGLE_NATIVE_FILE,
            "application/vnd.google-apps.spreadsheet":
                ReasonCode.GOOGLE_NATIVE_FILE,
            "application/vnd.google-apps.presentation":
                ReasonCode.GOOGLE_NATIVE_FILE,
            "application/vnd.google-apps.shortcut":
                ReasonCode.GOOGLE_DRIVE_SHORTCUT,
        }
        for mime_type, reason in types.items():
            with self.subTest(mime_type=mime_type):
                self.assert_reason(item(None, mime_type), reason)

    def test_actual_pptx_is_distinct_from_google_slides(self) -> None:
        actual = evaluate_file(item("pptx", MIME["pptx"]))
        native = evaluate_file(
            item(None, "application/vnd.google-apps.presentation")
        )
        self.assertEqual(actual.automatic_decision, "TAKE")
        self.assertFalse(actual.accepted_for_ai_analysis)
        self.assertEqual(native.reason_code, ReasonCode.GOOGLE_NATIVE_FILE)

    def test_extension_and_mime_failures(self) -> None:
        cases = [
            (item(None, "image/jpeg"), ReasonCode.UNSUPPORTED_EXTENSION),
            (item("pdf", None), ReasonCode.INVALID_METADATA),
            (item("pptx", "application/pdf"),
             ReasonCode.UNSUPPORTED_MIME_TYPE),
            (item("pdf", "image/jpeg"),
             ReasonCode.UNSUPPORTED_MIME_TYPE),
            (item("bin", "image/jpeg"),
             ReasonCode.UNSUPPORTED_EXTENSION),
        ]
        for value, reason in cases:
            with self.subTest(reason=reason):
                self.assert_reason(value, reason)

    def test_size_failures(self) -> None:
        cases = [
            (0, ReasonCode.ZERO_BYTE_FILE),
            (-1, ReasonCode.INVALID_SIZE),
            ("10", ReasonCode.INVALID_SIZE),
            (None, ReasonCode.INVALID_SIZE),
        ]
        for size, reason in cases:
            with self.subTest(size=size):
                self.assert_reason(
                    item(size_bytes=size),
                    reason,
                )

    def test_temporary_filename_patterns(self) -> None:
        names = [
            "~$draft.pdf",
            ".~lock.notes.pdf#",
            "asset.tmp",
            "asset.temp",
            "asset.part",
            "asset.crdownload",
        ]
        for name in names:
            with self.subTest(name=name):
                self.assert_reason(
                    item(file_name=name),
                    ReasonCode.TEMPORARY_FILE,
                )

    def test_system_filenames_and_dotfile_configuration(self) -> None:
        for name in (
            ".DS_Store",
            "Thumbs.db",
            "desktop.ini",
            "Icon\r",
            "._asset.jpg",
        ):
            with self.subTest(name=name):
                self.assert_reason(
                    item(file_name=name),
                    ReasonCode.SYSTEM_FILE,
                )
        allowed = evaluate_file(item(file_name=".portrait.jpg"))
        self.assertEqual(allowed.automatic_decision, "TAKE")
        self.assert_reason(
            item(file_name=".portrait.jpg"),
            ReasonCode.SYSTEM_FILE,
            configuration=RuleConfiguration(reject_all_dotfiles=True),
        )

    def test_configured_exclusions_are_case_insensitive(self) -> None:
        filename_config = RuleConfiguration(
            excluded_filename_patterns=("PRIVATE-*",)
        )
        self.assert_reason(
            item(file_name="Private-Asset.JPG"),
            ReasonCode.EXCLUDED_FILENAME,
            configuration=filename_config,
        )
        path_config = RuleConfiguration(
            excluded_path_patterns=("ARCHIVE/*",)
        )
        self.assert_reason(
            item(relative_path=r"Archive\Old"),
            ReasonCode.EXCLUDED_PATH,
            configuration=path_config,
        )

    def test_source_state_and_access_outcomes(self) -> None:
        self.assert_reason(
            item(trashed=True), ReasonCode.TRASHED_FILE
        )
        self.assert_reason(
            item(is_missing=True), ReasonCode.MISSING_FILE
        )
        self.assert_reason(
            item(accessibility_status="inaccessible"),
            ReasonCode.INACCESSIBLE,
            "PENDING",
            "INACCESSIBLE",
        )
        self.assert_reason(
            item(
                mime_type="application/vnd.google-apps.folder",
                is_folder=True,
            ),
            ReasonCode.FOLDER_ITEM,
            "PENDING",
            "DISCOVERED",
        )

    def test_invalid_core_metadata(self) -> None:
        self.assert_reason(
            item(file_name=""), ReasonCode.INVALID_METADATA
        )
        self.assert_reason(
            item(trashed="false"), ReasonCode.INVALID_METADATA
        )

    def test_repeated_evaluation_is_identical(self) -> None:
        value = item("pdf", " application/PDF ", relative_path=r"A\B")
        self.assertEqual(evaluate_file(value), evaluate_file(value))


if __name__ == "__main__":
    unittest.main()
