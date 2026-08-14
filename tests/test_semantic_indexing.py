from __future__ import annotations

import unittest

from kdi_media.providers.base import (
    AI_DESCRIPTION_MAX_LEN,
    CONTROLLED_CONTENT_TYPES,
    SHORT_CAPTION_MAX_LEN,
    AIProviderNotConfiguredError,
    DescriptionValidationError,
    StructuredMetadata,
    get_description_provider,
    get_embedding_provider,
    parse_structured_metadata,
)
from kdi_media.semantic_indexing import (
    AssetCandidate,
    FailureInfo,
    IndexResult,
    IndexingStatus,
    SemanticIndexingWorker,
    build_searchable_text,
    compute_fingerprint,
    compute_searchable_text_hash,
    requires_pilot_confirmation,
)
from kdi_media.video_frames import FrameExtractionError


def metadata(**changes: object) -> StructuredMetadata:
    values: dict[str, object] = {
        "content_type": "Patient Testimonial",
        "treatment": "Long Hair FUE",
        "subject": "Female patient",
        "doctor_name": "Datuk Dr Inder",
        "short_caption": "Female patient shares her Long Hair FUE recovery experience.",
        "ai_description": "A female patient discusses her Long Hair FUE treatment experience.",
    }
    values.update(changes)
    return StructuredMetadata(**values)  # type: ignore[arg-type]


def candidate(**changes: object) -> AssetCandidate:
    values: dict[str, object] = {
        "asset_id": "asset-1",
        "file_name": "testimonial.mp4",
        "mime_type": "video/mp4",
        "file_extension": "mp4",
        "content_hash": "a" * 64,
        "updated_at": "2026-08-01T00:00:00Z",
        "size_bytes": 1000,
        "google_file_id": "drive-file-1",
        "media_category": "video",
    }
    values.update(changes)
    return AssetCandidate(**values)  # type: ignore[arg-type]


class ParseStructuredMetadataTests(unittest.TestCase):
    def test_valid_full_response_is_accepted(self) -> None:
        result = parse_structured_metadata(
            {
                "content_type": "Patient Testimonial",
                "treatment": "Long Hair FUE",
                "subject": "Female patient",
                "doctor_name": "Datuk Dr Inder",
                "short_caption": "Female patient shares her Long Hair FUE recovery experience.",
                "ai_description": "A detailed factual description.",
            }
        )
        self.assertEqual(result.content_type, "Patient Testimonial")
        self.assertEqual(result.doctor_name, "Datuk Dr Inder")

    def test_unrecognized_content_type_falls_back_to_other(self) -> None:
        result = parse_structured_metadata({"content_type": "Something Made Up", "short_caption": "Caption.", "ai_description": "Description."})
        self.assertEqual(result.content_type, "Other")

    def test_missing_content_type_falls_back_to_other(self) -> None:
        result = parse_structured_metadata({"short_caption": "Caption.", "ai_description": "Description."})
        self.assertEqual(result.content_type, "Other")

    def test_all_controlled_content_types_are_accepted_verbatim(self) -> None:
        for value in CONTROLLED_CONTENT_TYPES:
            result = parse_structured_metadata({"content_type": value, "short_caption": "Caption.", "ai_description": "Description."})
            self.assertEqual(result.content_type, value)

    def test_null_fields_are_preserved_as_none_not_fabricated(self) -> None:
        result = parse_structured_metadata(
            {
                "content_type": "Other",
                "treatment": None,
                "subject": None,
                "doctor_name": None,
                "short_caption": "Caption.",
                "ai_description": "Description.",
            }
        )
        self.assertIsNone(result.treatment)
        self.assertIsNone(result.subject)
        self.assertIsNone(result.doctor_name)

    def test_blank_string_fields_are_normalized_to_none(self) -> None:
        result = parse_structured_metadata({"content_type": "Other", "doctor_name": "   ", "short_caption": "Caption.", "ai_description": "Description."})
        self.assertIsNone(result.doctor_name)

    def test_short_caption_over_max_length_is_rejected(self) -> None:
        with self.assertRaises(DescriptionValidationError):
            parse_structured_metadata({"content_type": "Other", "short_caption": "x" * (SHORT_CAPTION_MAX_LEN + 50), "ai_description": "Description."})

    def test_ai_description_over_max_length_is_rejected(self) -> None:
        with self.assertRaises(DescriptionValidationError):
            parse_structured_metadata({"content_type": "Other", "short_caption": "Caption.", "ai_description": "x" * (AI_DESCRIPTION_MAX_LEN + 50)})

    def test_non_object_response_is_rejected(self) -> None:
        with self.assertRaises(DescriptionValidationError):
            parse_structured_metadata("not a dict")

    def test_non_string_field_is_rejected(self) -> None:
        with self.assertRaises(DescriptionValidationError):
            parse_structured_metadata({"content_type": "Other", "doctor_name": 12345})


class BuildSearchableTextTests(unittest.TestCase):
    def test_deterministic_construction_from_approved_fields_only(self) -> None:
        text = build_searchable_text(file_name="testimonial.mp4", metadata=metadata())
        self.assertNotIn("testimonial.mp4", text)
        self.assertIn("Patient Testimonial", text)
        self.assertIn("Long Hair FUE", text)
        self.assertIn("Datuk Dr Inder", text)

    def test_same_inputs_produce_identical_text(self) -> None:
        first = build_searchable_text(file_name="a.mp4", metadata=metadata())
        second = build_searchable_text(file_name="a.mp4", metadata=metadata())
        self.assertEqual(first, second)

    def test_whitespace_is_normalized(self) -> None:
        text = build_searchable_text(
            file_name="a.mp4", metadata=metadata(subject="  female   patient  ")
        )
        self.assertNotIn("  ", text)

    def test_null_fields_do_not_appear_as_none_literal(self) -> None:
        text = build_searchable_text(
            file_name="a.mp4",
            metadata=metadata(treatment=None, subject=None, doctor_name=None),
        )
        self.assertNotIn("None", text)

    def test_result_is_capped_within_db_constraint(self) -> None:
        # ai_description is already capped at AI_DESCRIPTION_MAX_LEN by
        # parse_structured_metadata; this checks build_searchable_text's own
        # cap holds even when every field is at its individual maximum.
        parsed = parse_structured_metadata(
            {
                "content_type": "Other",
                "treatment": "x" * 200,
                "subject": "x" * 200,
                "doctor_name": "x" * 200,
                "short_caption": "x" * SHORT_CAPTION_MAX_LEN,
                "ai_description": "x" * AI_DESCRIPTION_MAX_LEN,
            }
        )
        text = build_searchable_text(file_name="a.mp4", metadata=parsed)
        self.assertLessEqual(len(text), 4000)


class ComputeFingerprintTests(unittest.TestCase):
    """These equality/inequality semantics are what the repository's
    discover_eligible_asset_ids relies on to skip unchanged assets and
    re-queue changed ones."""

    def test_identical_inputs_produce_identical_fingerprint(self) -> None:
        self.assertEqual(compute_fingerprint(candidate()), compute_fingerprint(candidate()))

    def test_changed_content_hash_changes_fingerprint(self) -> None:
        self.assertNotEqual(
            compute_fingerprint(candidate()),
            compute_fingerprint(candidate(content_hash="b" * 64)),
        )

    def test_changed_updated_at_does_not_change_hashed_content_fingerprint(self) -> None:
        self.assertEqual(
            compute_fingerprint(candidate()),
            compute_fingerprint(candidate(updated_at="2026-09-01T00:00:00Z")),
        )

    def test_changed_filename_does_not_change_fingerprint(self) -> None:
        self.assertEqual(
            compute_fingerprint(candidate()),
            compute_fingerprint(candidate(file_name="renamed.mp4")),
        )

    def test_mime_type_and_google_file_id_do_not_affect_fingerprint(self) -> None:
        # A source-file relocation (new google_file_id) without a real content
        # change should not force re-indexing.
        self.assertEqual(
            compute_fingerprint(candidate()),
            compute_fingerprint(candidate(google_file_id="drive-file-2", mime_type="video/quicktime")),
        )


class FakeRepository:
    def __init__(self) -> None:
        self.completed: IndexResult | None = None
        self.failure: FailureInfo | None = None
        self.fetch_result: AssetCandidate | None = candidate()

    def discover_eligible_asset_ids(self, limit: int):
        return [], []

    def seed_pending(self, asset_ids):
        pass

    def requeue_changed(self, asset_ids):
        pass

    def mark_ineligible(self, asset_id: str, reason: str) -> None:
        pass

    def claim_batch(self, claim_owner, limit, lease_seconds, asset_ids=None):
        return []

    def fetch_candidate(self, asset_id: str) -> AssetCandidate | None:
        return self.fetch_result

    def complete(self, asset_id: str, claim_owner: str, result: IndexResult) -> bool:
        self.completed = result
        return True

    def fail(self, asset_id: str, claim_owner: str, failure: FailureInfo) -> bool:
        self.failure = failure
        return True


class FakeContentFetcher:
    def fetch(self, candidate: AssetCandidate) -> bytes:
        return b"fake-bytes"


class FakeFrameExtractor:
    """Never shells out to ffmpeg - returns fixed fake frame bytes."""

    def __init__(self, *, frame_count: int = 3, error: Exception | None = None) -> None:
        self.frame_count = frame_count
        self.error = error
        self.calls: list[tuple[bytes, int]] = []

    def extract_frames(self, video_bytes: bytes, *, max_frames: int) -> list[bytes]:
        self.calls.append((video_bytes, max_frames))
        if self.error is not None:
            raise self.error
        return [f"frame-{i}".encode() for i in range(min(self.frame_count, max_frames))]


class PassthroughImagePreprocessor:
    def prepare(self, image_bytes: bytes) -> bytes:
        return image_bytes


class FlakyDescriptionProvider:
    """Fails with a retryable error `fail_times` times, then succeeds. Also
    doubles as the embedding provider in worker tests (both roles filled by
    the same fake), hence the embedding-side self-report attributes too."""

    provider_name = "fake"
    model_name = "fake-model"
    schema_version = "v1"
    embedding_dimensions = 768
    version = "v1"

    def __init__(self, fail_times: int = 0, *, permanent: bool = False) -> None:
        self.fail_times = fail_times
        self.permanent = permanent
        self.calls = 0

    def describe_media(self, *, file_name, mime_type, media_category, images, transcript=None):
        self.calls += 1
        if self.calls <= self.fail_times:
            if self.permanent:
                from kdi_media.semantic_indexing import PermanentIndexingError

                raise PermanentIndexingError("permanent failure")
            raise RuntimeError("transient description failure")
        return metadata(), 0.001

    def embed_text(self, text: str):
        return [0.1] * 768, 0.0001


class SemanticIndexingWorkerTests(unittest.TestCase):
    def _worker(self, provider, repository=None, **kwargs) -> tuple[SemanticIndexingWorker, FakeRepository]:
        repo = repository or FakeRepository()
        kwargs.setdefault("frame_extractor", FakeFrameExtractor())
        worker = SemanticIndexingWorker(
            repo,
            FakeContentFetcher(),
            provider,
            provider,
            sleeper=lambda _seconds: None,
            jitter=lambda: 0.0,
            **kwargs,
        )
        return worker, repo

    def test_successful_first_attempt_completes_and_indexes(self) -> None:
        provider = FlakyDescriptionProvider(fail_times=0)
        worker, repo = self._worker(provider)
        result = worker.process_one("asset-1", "owner-1")
        self.assertIsNotNone(result)
        self.assertIsNotNone(repo.completed)
        self.assertIsNone(repo.failure)

    def test_transient_failure_is_retried_then_succeeds(self) -> None:
        provider = FlakyDescriptionProvider(fail_times=2)
        worker, repo = self._worker(provider)
        result = worker.process_one("asset-1", "owner-1")
        self.assertIsNotNone(result)
        self.assertEqual(provider.calls, 3)
        self.assertIsNotNone(repo.completed)

    def test_retries_exhausted_marks_failed_retryable(self) -> None:
        provider = FlakyDescriptionProvider(fail_times=99)
        worker, repo = self._worker(provider, retry_delays=(0.0, 0.0))
        result = worker.process_one("asset-1", "owner-1")
        self.assertIsNone(result)
        assert repo.failure is not None
        self.assertEqual(repo.failure.status, IndexingStatus.FAILED_RETRYABLE)
        self.assertTrue(repo.failure.retryable)

    def test_permanent_error_is_not_retried(self) -> None:
        provider = FlakyDescriptionProvider(fail_times=1, permanent=True)
        worker, repo = self._worker(provider, retry_delays=(0.0, 0.0))
        result = worker.process_one("asset-1", "owner-1")
        self.assertIsNone(result)
        self.assertEqual(provider.calls, 1)
        assert repo.failure is not None
        self.assertEqual(repo.failure.status, IndexingStatus.FAILED_PERMANENT)
        self.assertFalse(repo.failure.retryable)

    def test_embedding_failure_is_retryable(self) -> None:
        class FailingEmbeddingProvider:
            provider_name = "fake"
            model_name = "fake-model"
            schema_version = "v1"
            embedding_dimensions = 768
            version = "v1"

            def describe_media(self, **_kwargs):
                return metadata(), 0.001

            def embed_text(self, text: str):
                raise RuntimeError("embedding service unavailable")

        worker, repo = self._worker(FailingEmbeddingProvider(), retry_delays=(0.0,))
        result = worker.process_one("asset-1", "owner-1")
        self.assertIsNone(result)
        assert repo.failure is not None
        self.assertEqual(repo.failure.status, IndexingStatus.FAILED_RETRYABLE)

    def test_cost_cap_stops_further_work_permanently(self) -> None:
        provider = FlakyDescriptionProvider(fail_times=0)
        worker, repo = self._worker(provider, max_cost_usd=0.0)
        result = worker.process_one("asset-1", "owner-1")
        self.assertIsNone(result)
        assert repo.failure is not None
        self.assertEqual(repo.failure.status, IndexingStatus.FAILED_PERMANENT)

    def test_candidate_not_found_fails_permanently_without_calling_provider(self) -> None:
        provider = FlakyDescriptionProvider(fail_times=0)
        repo = FakeRepository()
        repo.fetch_result = None
        worker, _ = self._worker(provider, repository=repo)
        result = worker.process_one("missing-asset", "owner-1")
        self.assertIsNone(result)
        self.assertEqual(provider.calls, 0)
        assert repo.failure is not None
        self.assertEqual(repo.failure.status, IndexingStatus.FAILED_PERMANENT)


class ProviderNotConfiguredTests(unittest.TestCase):
    """No AI provider is approved for this project yet - these factories must
    fail clearly rather than silently defaulting to any specific vendor."""

    def setUp(self) -> None:
        import os

        self._removed = {
            name: os.environ.pop(name, None)
            for name in ("AI_DESCRIPTION_PROVIDER", "AI_EMBEDDING_PROVIDER")
        }

    def tearDown(self) -> None:
        import os

        for name, value in self._removed.items():
            if value is not None:
                os.environ[name] = value

    def test_description_provider_raises_when_unset(self) -> None:
        with self.assertRaises(AIProviderNotConfiguredError):
            get_description_provider()

    def test_embedding_provider_raises_when_unset(self) -> None:
        with self.assertRaises(AIProviderNotConfiguredError):
            get_embedding_provider()

    def test_unknown_description_provider_name_raises_clearly(self) -> None:
        import os

        os.environ["AI_DESCRIPTION_PROVIDER"] = "not-a-real-provider"
        with self.assertRaises(AIProviderNotConfiguredError):
            get_description_provider()

    def test_unknown_embedding_provider_name_raises_clearly(self) -> None:
        import os

        os.environ["AI_EMBEDDING_PROVIDER"] = "not-a-real-provider"
        with self.assertRaises(AIProviderNotConfiguredError):
            get_embedding_provider()

    def test_no_provider_defaults_to_gemini_or_any_other_vendor(self) -> None:
        # Regression guard: unset must never silently resolve to a concrete
        # adapter for any vendor (Gemini or otherwise).
        with self.assertRaises(AIProviderNotConfiguredError) as ctx:
            get_description_provider()
        self.assertNotIn("gemini", str(ctx.exception).lower())


class ComputeSearchableTextHashTests(unittest.TestCase):
    def test_identical_text_produces_identical_hash(self) -> None:
        self.assertEqual(compute_searchable_text_hash("hello world"), compute_searchable_text_hash("hello world"))

    def test_different_text_produces_different_hash(self) -> None:
        self.assertNotEqual(compute_searchable_text_hash("hello"), compute_searchable_text_hash("world"))


class RequiresPilotConfirmationTests(unittest.TestCase):
    """No automated clinical/patient-identifiable classification exists, so
    nothing is eligible for an external AI call by default."""

    def test_no_asset_ids_and_not_confirmed_requires_confirmation(self) -> None:
        self.assertTrue(requires_pilot_confirmation(asset_ids=None, confirmed=False))

    def test_asset_ids_present_but_not_confirmed_requires_confirmation(self) -> None:
        self.assertTrue(requires_pilot_confirmation(asset_ids=["asset-1"], confirmed=False))

    def test_confirmed_but_no_asset_ids_requires_confirmation(self) -> None:
        self.assertTrue(requires_pilot_confirmation(asset_ids=None, confirmed=True))

    def test_empty_asset_id_list_requires_confirmation(self) -> None:
        self.assertTrue(requires_pilot_confirmation(asset_ids=[], confirmed=True))

    def test_asset_ids_and_confirmed_does_not_require_confirmation(self) -> None:
        self.assertFalse(requires_pilot_confirmation(asset_ids=["asset-1"], confirmed=True))


class PrepareDescriptionInputTests(unittest.TestCase):
    def _worker(self, *, media_category: str, frame_extractor=None) -> SemanticIndexingWorker:
        provider = FlakyDescriptionProvider()
        return SemanticIndexingWorker(
            FakeRepository(),
            FakeContentFetcher(),
            provider,
            provider,
            frame_extractor=frame_extractor or FakeFrameExtractor(),
            image_preprocessor=PassthroughImagePreprocessor(),
        )

    def test_image_asset_sends_a_single_image_and_no_transcript(self) -> None:
        worker = self._worker(media_category="image")
        images, transcript = worker.prepare_description_input(candidate(media_category="image"))
        self.assertEqual(images, [b"fake-bytes"])
        self.assertIsNone(transcript)

    def test_video_asset_uses_extracted_frames_never_the_raw_video_bytes(self) -> None:
        extractor = FakeFrameExtractor(frame_count=4)
        worker = self._worker(media_category="video", frame_extractor=extractor)
        images, _transcript = worker.prepare_description_input(candidate(media_category="video"))
        self.assertEqual(len(extractor.calls), 1)
        self.assertNotIn(b"fake-bytes", images)  # the raw fetched video bytes are never in `images`
        self.assertTrue(all(image.startswith(b"frame-") for image in images))

    def test_video_transcript_is_limited_before_being_returned(self) -> None:
        worker = self._worker(media_category="video")
        long_transcript = "word " * 1000
        _images, transcript = worker.prepare_description_input(
            candidate(media_category="video", transcript=long_transcript)
        )
        assert transcript is not None
        self.assertLess(len(transcript), len(long_transcript))

    def test_video_frame_extraction_failure_is_retryable(self) -> None:
        provider = FlakyDescriptionProvider()
        repo = FakeRepository()
        worker = SemanticIndexingWorker(
            repo,
            FakeContentFetcher(),
            provider,
            provider,
            frame_extractor=FakeFrameExtractor(error=FrameExtractionError("ffmpeg not found")),
            retry_delays=(0.0,),
            sleeper=lambda _seconds: None,
        )
        result = worker.process_one("asset-1", "owner-1")
        self.assertIsNone(result)
        assert repo.failure is not None
        self.assertEqual(repo.failure.status, IndexingStatus.FAILED_RETRYABLE)


class IndexResultFieldsTests(unittest.TestCase):
    """The worker must record provider/model/dimensions/version for both
    description and embedding generation - required for future model
    rebuilds and for the asset_embeddings uniqueness contract."""

    def test_successful_run_records_full_provenance(self) -> None:
        provider = FlakyDescriptionProvider()
        repo = FakeRepository()
        worker = SemanticIndexingWorker(
            repo,
            FakeContentFetcher(),
            provider,
            provider,
            frame_extractor=FakeFrameExtractor(),
        )
        worker.process_one("asset-1", "owner-1")
        assert repo.completed is not None
        self.assertEqual(repo.completed.description_provider, "fake")
        self.assertEqual(repo.completed.description_model, "fake-model")
        self.assertEqual(repo.completed.description_version, "v1")
        self.assertEqual(repo.completed.embedding_provider, "fake")
        self.assertEqual(repo.completed.embedding_model, "fake-model")
        self.assertEqual(repo.completed.embedding_dimensions, 768)
        self.assertEqual(repo.completed.embedding_version, "v1")
        self.assertTrue(repo.completed.searchable_text_hash)


if __name__ == "__main__":
    unittest.main()
