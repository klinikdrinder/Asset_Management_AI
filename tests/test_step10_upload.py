from __future__ import annotations

import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock
from uuid import uuid4

from kdi_media.google_drive import DriveCredentialProfile
from kdi_media.step10_upload import (
    APP_PROPERTY_ASSET_ID,
    APP_PROPERTY_DESTINATION_ID,
    APP_PROPERTY_VERSION,
    AUDIT_EVENT_TYPES,
    DestinationAccessDenied,
    DestinationAction,
    DestinationConflict,
    DestinationRootGuard,
    DriveResumableTransfer,
    InvalidCanonicalState,
    MIGRATION_VERSION,
    PermanentTransferError,
    RetryableTransferError,
    SelectedSource,
    SourceAccessDenied,
    SourceChanged,
    SourceNotFound,
    VerificationLevel,
    build_destination_plan,
    decide_destination_action,
    destination_app_properties,
    destination_filename,
    deterministic_idempotency_key,
    lifecycle_values,
    preflight_source,
    prepare_lifecycle_initialization,
    retry_delay,
    route_category,
    run_with_retry,
    sanitize_event_details,
    select_canonical_source,
    verify_destination_metadata,
    verify_destination_sha256,
)


HASH = "a" * 64
ROOT = "1CdmowWV5TAk5R9D5yl2cOT8Plx3ihZgl"


def asset(asset_id=None, preferred=None):
    return {
        "id": asset_id or str(uuid4()),
        "content_hash": HASH,
        "metadata": {"canonical_source_file_id": preferred} if preferred else {},
    }


def source(source_id=None, **changes):
    value = {
        "id": source_id or str(uuid4()),
        "source_folder_id": "folder-a",
        "google_file_id": "google-a",
        "file_name": "Patient 12345678.jpg",
        "mime_type": "image/jpeg",
        "file_extension": "jpg",
        "size_bytes": 6,
        "decision": "TAKE",
        "processing_status": "READY",
        "hash_status": "HASHED",
        "hash_algorithm": "SHA-256",
        "content_sha256": HASH,
        "trashed": False,
        "is_missing": False,
        "access_status": "ACCESSIBLE",
        "hash_drive_modified_at": "2026-07-30T00:00:00Z",
        "hash_drive_version": "1",
        "hash_expected_bytes": 6,
        "hash_drive_mime_type": "image/jpeg",
    }
    value.update(changes)
    return value


def relation(asset_id, source_id):
    return {"asset_id": asset_id, "source_file_id": source_id}


def selected(**changes):
    value = SelectedSource(
        id=str(uuid4()),
        source_folder_id="folder-a",
        google_file_id="google-a",
        file_name="private patient name.jpg",
        mime_type="image/jpeg",
        file_extension="jpg",
        size_bytes=6,
        content_sha256=HASH,
        drive_modified_at="2026-07-30T00:00:00Z",
        drive_version="1",
    )
    return SelectedSource(**{**value.__dict__, **changes})


class SourceSelectionTests(unittest.TestCase):
    def test_one_source(self):
        row = source()
        item = asset(preferred=row["id"])
        self.assertEqual(
            select_canonical_source(item, [relation(item["id"], row["id"])], [row]).id,
            row["id"],
        )

    def test_multiple_prefers_step9_representative(self):
        first, second = source(), source(google_file_id="google-b")
        item = asset(preferred=second["id"])
        found = select_canonical_source(
            item,
            [relation(item["id"], first["id"]), relation(item["id"], second["id"])],
            [first, second],
        )
        self.assertEqual(found.id, second["id"])

    def test_invalid_preferred_uses_deterministic_fallback(self):
        first = source(source_folder_id="z", google_file_id="b")
        second = source(source_folder_id="a", google_file_id="z")
        item = asset(preferred=str(uuid4()))
        rows = [first, second]
        links = [relation(item["id"], row["id"]) for row in rows]
        self.assertEqual(select_canonical_source(item, links, rows).id, second["id"])
        self.assertEqual(select_canonical_source(item, links, reversed(rows)).id, second["id"])

    def test_excluded_and_unhashed_sources_ignored(self):
        bad = source(decision="SKIP", processing_status="SKIPPED")
        unhashed = source(hash_status="NOT_STARTED", content_sha256=None)
        good = source(source_folder_id="b")
        item = asset()
        rows = [bad, unhashed, good]
        links = [relation(item["id"], row["id"]) for row in rows]
        self.assertEqual(select_canonical_source(item, links, rows).id, good["id"])

    def test_missing_relationship_rejected(self):
        with self.assertRaises(InvalidCanonicalState):
            select_canonical_source(asset(), [], [source()])


class RoutingAndNamingTests(unittest.TestCase):
    def test_every_approved_route(self):
        pairs = {
            ("jpg", "image/jpeg"): "Images",
            ("jpeg", "image/jpeg"): "Images",
            ("png", "image/png"): "Images",
            ("webp", "image/webp"): "Images",
            ("mp4", "video/mp4"): "Videos",
            ("mov", "video/quicktime"): "Videos",
            ("pdf", "application/pdf"): "Documents",
            (
                "pptx",
                "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            ): "Documents",
        }
        for pair, expected in pairs.items():
            with self.subTest(pair=pair):
                self.assertEqual(route_category(*pair), expected)

    def test_unsupported_route_rejected(self):
        with self.assertRaises(InvalidCanonicalState):
            route_category("heic", "image/heic")

    def test_fallback_is_default_and_stable(self):
        item_id = str(uuid4())
        one = destination_filename(item_id, "JPG", original_name="Patient Name.JPG")
        two = destination_filename(item_id, ".jpg", original_name="different.jpg")
        self.assertEqual(one, two)
        self.assertRegex(one, r"^asset__[0-9a-f]{8}\.jpg$")

    def test_sensitive_stem_falls_back_even_when_enabled(self):
        name = destination_filename(
            str(uuid4()), "jpg", original_name="patient-12345678.jpg",
            allow_safe_stem=True,
        )
        self.assertTrue(name.startswith("asset__"))

    def test_unicode_invalid_duplicate_extension_and_trailing_dot(self):
        item_id = str(uuid4())
        name = destination_filename(
            item_id,
            "jpg",
            original_name="Café / promo.jpg.jpg.",
            allow_safe_stem=True,
        )
        self.assertNotIn("/", name)
        self.assertTrue(name.endswith(".jpg"))
        self.assertLessEqual(len(name), 120)

    def test_empty_and_reserved_names_fall_back(self):
        for original in ("...", "CON.jpg", "   "):
            self.assertTrue(
                destination_filename(
                    str(uuid4()), "jpg", original_name=original,
                    allow_safe_stem=True,
                ).startswith("asset__")
            )

    def test_long_filename_is_deterministically_truncated(self):
        item_id = str(uuid4())
        result = destination_filename(
            item_id, "jpg", original_name=("x" * 300) + ".jpg",
            allow_safe_stem=True,
        )
        self.assertLessEqual(len(result), 120)
        self.assertEqual(
            result,
            destination_filename(
                item_id, "jpg", original_name=("x" * 300) + ".jpg",
                allow_safe_stem=True,
            ),
        )

    def test_plan_routes_documents_and_uses_no_hash_in_name(self):
        item = asset()
        src = selected(
            mime_type="application/pdf",
            file_extension="pdf",
            file_name="report.pdf",
        )
        plan = build_destination_plan(
            item, src, ROOT, destination_record_id=str(uuid4())
        )
        self.assertTrue(plan.relative_path.startswith("Documents/asset__"))
        self.assertNotIn(HASH, plan.filename)


class IdentityTests(unittest.TestCase):
    def test_initialization_excludes_invalid_and_is_stable(self):
        good_source = source()
        good_asset = asset()
        invalid_asset = asset()
        relationships = [
            relation(good_asset["id"], good_source["id"]),
        ]
        first = prepare_lifecycle_initialization(
            [invalid_asset, good_asset],
            relationships,
            [good_source],
            ROOT,
        )
        second = prepare_lifecycle_initialization(
            [good_asset, invalid_asset],
            relationships,
            [good_source],
            ROOT,
        )
        self.assertEqual(first, second)
        self.assertEqual(len(first), 1)
        self.assertEqual(first[0]["asset_id"], good_asset["id"])
        self.assertEqual(first[0]["source_sha256"], HASH)

    def test_lifecycle_initialization_values_are_idempotent_inputs(self):
        item = asset()
        record_id = str(uuid4())
        plan = build_destination_plan(
            item, selected(), ROOT, destination_record_id=record_id
        )
        values = lifecycle_values(plan, destination_record_id=record_id)
        self.assertEqual(values["asset_id"], item["id"])
        self.assertEqual(values["upload_status"], "NOT_STARTED")
        self.assertEqual(
            values["verification_level"],
            "SOURCE_HASH_VERIFIED",
        )
        self.assertEqual(values["transferred_bytes"], 0)
        self.assertEqual(
            values["source_metadata_snapshot"]["hash_algorithm"],
            "SHA-256",
        )

    def test_idempotency_key_is_stable_and_destination_specific(self):
        item_id = str(uuid4())
        one = deterministic_idempotency_key(item_id, ROOT, MIGRATION_VERSION)
        self.assertEqual(one, deterministic_idempotency_key(item_id, ROOT, MIGRATION_VERSION))
        self.assertNotEqual(one, deterministic_idempotency_key(item_id, "other-root", MIGRATION_VERSION))

    def test_app_properties_are_compact_and_non_sensitive(self):
        values = destination_app_properties(str(uuid4()), str(uuid4()), MIGRATION_VERSION)
        self.assertEqual(
            set(values),
            {APP_PROPERTY_ASSET_ID, APP_PROPERTY_DESTINATION_ID, APP_PROPERTY_VERSION},
        )
        self.assertNotIn(HASH, "".join(values.values()))

    def test_verified_match_skips(self):
        self.assertEqual(
            decide_destination_action(
                {"upload_status": "VERIFIED", "destination_google_file_id": "d1"},
                [{"id": "d1"}],
            ),
            DestinationAction.SKIP,
        )

    def test_response_lost_is_recovered(self):
        self.assertEqual(
            decide_destination_action({"upload_status": "UPLOADING"}, [{"id": "d1"}]),
            DestinationAction.RECOVER,
        )

    def test_missing_verified_file_and_duplicate_matches_need_review(self):
        self.assertEqual(
            decide_destination_action({"upload_status": "VERIFIED"}, []),
            DestinationAction.MANUAL_REVIEW,
        )
        self.assertEqual(
            decide_destination_action({}, [{"id": "1"}, {"id": "2"}]),
            DestinationAction.MANUAL_REVIEW,
        )

    def test_retryable_without_file_retries_and_new_creates(self):
        self.assertEqual(
            decide_destination_action({"upload_status": "FAILED_RETRYABLE"}, []),
            DestinationAction.RETRY,
        )
        self.assertEqual(decide_destination_action({}, []), DestinationAction.CREATE)


class PreflightTests(unittest.TestCase):
    def current(self, **changes):
        value = {
            "id": "google-a",
            "size": "6",
            "mimeType": "image/jpeg",
            "modifiedTime": "2026-07-30T00:00:00Z",
            "version": "1",
            "trashed": False,
        }
        value.update(changes)
        return value

    def test_unchanged(self):
        self.assertEqual(preflight_source(source(), self.current())["size_bytes"], 6)

    def test_size_modified_mime_version_and_trashed_changes(self):
        cases = [
            {"size": "7"},
            {"modifiedTime": "2026-07-31T00:00:00Z"},
            {"mimeType": "video/mp4"},
            {"version": "2"},
            {"trashed": True},
        ]
        for changes in cases:
            with self.subTest(changes=changes), self.assertRaises(SourceChanged):
                preflight_source(source(), self.current(**changes))

    def test_missing_and_access_denied(self):
        with self.assertRaises(SourceNotFound):
            preflight_source(source(), {})
        with self.assertRaises(SourceAccessDenied):
            preflight_source(source(), {"access_denied": True})

    def test_missing_hash_expected_size_and_unsupported(self):
        with self.assertRaises(InvalidCanonicalState):
            preflight_source(source(content_sha256=None), self.current())
        with self.assertRaises(InvalidCanonicalState):
            preflight_source(source(hash_expected_bytes=None, size_bytes=None), self.current())
        with self.assertRaises(InvalidCanonicalState):
            preflight_source(
                source(file_extension="heic", mime_type="image/heic", hash_drive_mime_type="image/heic"),
                self.current(mimeType="image/heic"),
            )


class RootAndVerificationTests(unittest.TestCase):
    def setUp(self):
        self.asset = asset()
        self.source = selected()
        self.record_id = str(uuid4())
        self.plan = build_destination_plan(
            self.asset, self.source, ROOT, destination_record_id=self.record_id
        )
        self.parent = "images-folder"
        self.guard = DestinationRootGuard(ROOT, {"Images": self.parent})

    def metadata(self, **changes):
        value = {
            "id": "destination-1",
            "name": self.plan.filename,
            "mimeType": self.plan.mime_type,
            "size": str(self.plan.expected_bytes),
            "parents": [self.parent],
            "trashed": False,
            "appProperties": dict(self.plan.app_properties),
        }
        value.update(changes)
        return value

    def test_root_guard(self):
        self.guard.require_root(ROOT)
        self.guard.require_category_parent("Images", self.parent)
        with self.assertRaises(DestinationAccessDenied):
            self.guard.require_root("other")
        with self.assertRaises(DestinationAccessDenied):
            self.guard.require_category_parent("Images", "other")

    def test_metadata_pass(self):
        self.assertEqual(
            verify_destination_metadata(
                self.metadata(), plan=self.plan, expected_parent_id=self.parent
            ),
            VerificationLevel.DESTINATION_METADATA_VERIFIED,
        )

    def test_metadata_failures(self):
        cases = [
            {"size": "7"},
            {"mimeType": "video/mp4"},
            {"parents": ["wrong"]},
            {"trashed": True},
            {"appProperties": {}},
            {"name": "wrong.jpg"},
        ]
        for changes in cases:
            with self.subTest(changes=changes), self.assertRaises(DestinationConflict):
                verify_destination_metadata(
                    self.metadata(**changes),
                    plan=self.plan,
                    expected_parent_id=self.parent,
                )
        with self.assertRaises(DestinationConflict):
            verify_destination_metadata({}, plan=self.plan, expected_parent_id=self.parent)

    def test_optional_sha_pass_fail_and_disabled(self):
        data = [b"abc", b"def"]
        digest = hashlib.sha256(b"abcdef").hexdigest()
        reader = lambda *_a, **_k: iter(data)
        self.assertEqual(
            verify_destination_sha256(
                object(), "id", digest, enabled=True,
                profile=DriveCredentialProfile.DESTINATION_WRITE,
                content_reader=reader,
            ),
            VerificationLevel.DESTINATION_SHA256_VERIFIED,
        )
        with self.assertRaises(DestinationConflict):
            verify_destination_sha256(
                object(), "id", "0" * 64, enabled=True,
                profile=DriveCredentialProfile.DESTINATION_WRITE,
                content_reader=reader,
            )
        with self.assertRaises(DestinationAccessDenied):
            verify_destination_sha256(
                object(), "id", digest, enabled=False,
                profile=DriveCredentialProfile.DESTINATION_WRITE,
                content_reader=reader,
            )


class TransferTests(unittest.TestCase):
    def setUp(self):
        self.asset = asset()
        self.plan = build_destination_plan(
            self.asset, selected(), ROOT, destination_record_id=str(uuid4())
        )
        self.source_service = MagicMock()
        self.destination_service = MagicMock()
        self.parent = "images-folder"
        self.guard = DestinationRootGuard(ROOT, {"Images": self.parent})
        request = self.destination_service.files.return_value.create.return_value
        request.next_chunk.return_value = (
            None,
            {
                "id": "dest-1",
                "name": self.plan.filename,
                "mimeType": self.plan.mime_type,
                "size": "6",
                "parents": [self.parent],
                "trashed": False,
                "appProperties": dict(self.plan.app_properties),
            },
        )

    def test_small_multichunk_transfer_and_cleanup(self):
        with tempfile.TemporaryDirectory() as directory:
            seen_paths = []
            def media(path, **kwargs):
                seen_paths.append(Path(path))
                self.assertTrue(Path(path).is_file())
                return {"path": path, **kwargs}
            adapter = DriveResumableTransfer(
                chunk_size=256 * 1024,
                temp_root=Path(directory),
                content_reader=lambda *_a, **_k: iter([b"ab", b"cd", b"ef"]),
                media_upload_factory=media,
            )
            result = adapter.transfer(
                source_service=self.source_service,
                destination_service=self.destination_service,
                source_profile=DriveCredentialProfile.SOURCE_READONLY,
                destination_profile=DriveCredentialProfile.DESTINATION_WRITE,
                source_file_id="source-1",
                destination_parent_id=self.parent,
                plan=self.plan,
                guard=self.guard,
            )
            self.assertEqual(result.transferred_bytes, 6)
            self.assertFalse(seen_paths[0].exists())

    def test_empty_file(self):
        empty_plan = build_destination_plan(
            self.asset,
            selected(size_bytes=0),
            ROOT,
            destination_record_id=str(uuid4()),
        )
        request = self.destination_service.files.return_value.create.return_value
        request.next_chunk.return_value = (None, {"id": "empty"})
        with tempfile.TemporaryDirectory() as directory:
            adapter = DriveResumableTransfer(
                chunk_size=256 * 1024,
                temp_root=Path(directory),
                content_reader=lambda *_a, **_k: iter([]),
                media_upload_factory=lambda *_a, **_k: object(),
            )
            self.assertEqual(
                adapter.transfer(
                    source_service=self.source_service,
                    destination_service=self.destination_service,
                    source_profile=DriveCredentialProfile.SOURCE_READONLY,
                    destination_profile=DriveCredentialProfile.DESTINATION_WRITE,
                    source_file_id="source",
                    destination_parent_id=self.parent,
                    plan=empty_plan,
                    guard=self.guard,
                ).transferred_bytes,
                0,
            )

    def test_partial_stream_and_wrong_profiles_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            adapter = DriveResumableTransfer(
                chunk_size=256 * 1024,
                temp_root=Path(directory),
                content_reader=lambda *_a, **_k: iter([b"abc"]),
                media_upload_factory=lambda *_a, **_k: object(),
            )
            kwargs = dict(
                source_service=self.source_service,
                destination_service=self.destination_service,
                source_profile=DriveCredentialProfile.SOURCE_READONLY,
                destination_profile=DriveCredentialProfile.DESTINATION_WRITE,
                source_file_id="source",
                destination_parent_id=self.parent,
                plan=self.plan,
                guard=self.guard,
            )
            with self.assertRaises(RetryableTransferError):
                adapter.transfer(**kwargs)
            with self.assertRaises(DestinationAccessDenied):
                adapter.transfer(**{**kwargs, "source_profile": DriveCredentialProfile.DESTINATION_WRITE})
            with self.assertRaises(Exception):
                adapter.transfer(**{**kwargs, "destination_profile": DriveCredentialProfile.SOURCE_READONLY})
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_interrupted_source_cleans_temp(self):
        def broken(*_a, **_k):
            yield b"ab"
            raise RetryableTransferError("interrupted")
        with tempfile.TemporaryDirectory() as directory:
            adapter = DriveResumableTransfer(
                chunk_size=256 * 1024,
                temp_root=Path(directory),
                content_reader=broken,
            )
            with self.assertRaises(RetryableTransferError):
                adapter.transfer(
                    source_service=self.source_service,
                    destination_service=self.destination_service,
                    source_profile=DriveCredentialProfile.SOURCE_READONLY,
                    destination_profile=DriveCredentialProfile.DESTINATION_WRITE,
                    source_file_id="source",
                    destination_parent_id=self.parent,
                    plan=self.plan,
                    guard=self.guard,
                )
            self.assertEqual(list(Path(directory).iterdir()), [])


class RetryAndAuditTests(unittest.TestCase):
    def test_retry_delay_and_exhaustion(self):
        self.assertEqual(retry_delay(1, jitter=lambda: 0), 1)
        self.assertEqual(retry_delay(1, retry_after=9, jitter=lambda: 0), 9)
        with self.assertRaises(PermanentTransferError):
            retry_delay(6)

    def test_retry_operation(self):
        attempts = []
        def operation():
            attempts.append(1)
            if len(attempts) < 3:
                raise RetryableTransferError("retry")
            return "ok"
        delays = []
        self.assertEqual(run_with_retry(operation, sleep=delays.append), "ok")
        self.assertEqual(len(attempts), 3)
        self.assertEqual(len(delays), 2)

    def test_event_types_and_sanitization(self):
        self.assertIn("UPLOAD_CLAIMED", AUDIT_EVENT_TYPES)
        self.assertIn("DESTINATION_CONFLICT", AUDIT_EVENT_TYPES)
        for event_type in (
            "LIFECYCLE_INITIALIZED",
            "CLAIM_RENEWED",
            "CLAIM_RELEASED",
            "CLAIM_RECOVERED",
        ):
            self.assertIn(event_type, AUDIT_EVENT_TYPES)
        safe = sanitize_event_details(
            {
                "asset_id": "safe",
                "access_token": "secret",
                "nested": {"authorization": "Bearer secret"},
                "message": "password=secret details",
            }
        )
        self.assertNotIn("access_token", safe)
        self.assertNotIn("authorization", safe["nested"])
        self.assertNotIn("secret", str(safe))

    def test_static_safety_no_delete_trash_permission_or_source_update(self):
        import inspect
        import kdi_media.step10_upload as module
        text = inspect.getsource(module).lower()
        self.assertNotIn(".delete(", text)
        self.assertNotIn("permissions().", text)
        self.assertNotIn('table("source_files").update', text)
        self.assertNotIn('table("asset_sources").update', text)


if __name__ == "__main__":
    unittest.main()
