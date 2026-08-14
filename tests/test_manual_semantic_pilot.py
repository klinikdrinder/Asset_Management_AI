from __future__ import annotations

import json
import math
from pathlib import Path
import tempfile
import unittest

from kdi_media.manual_semantic_pilot import (
    MANUAL_DESCRIPTION_PROVIDER,
    ManualPilotValidationError,
    build_manual_index_result,
    dry_run_report,
    load_and_review_manifest,
)
from kdi_media.providers.base import ProviderRetryableError
from kdi_media.semantic_indexing import AssetCandidate


ASSET_ID = "11111111-1111-4111-8111-111111111111"


def row(**changes):
    value = {
        "asset_id": ASSET_ID,
        "content_type": "Clinic Environment",
        "treatment": "",
        "subject": "Clinic interior",
        "doctor_name": "",
        "ai_description": "A human-reviewed description of a generic clinic interior.",
        "short_caption": "Clinic interior.",
        "reviewed_by": "Human Reviewer",
        "reviewed_at": "2026-08-11T12:00:00+08:00",
    }
    value.update(changes)
    return value


def load(payload):
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "manual.json"
        path.write_text(json.dumps({"assets": payload}), encoding="utf-8")
        return load_and_review_manifest(path)


def candidate():
    return AssetCandidate(
        asset_id=ASSET_ID, file_name="opaque.mp4", mime_type="video/mp4",
        file_extension="mp4", content_hash="a" * 64,
        updated_at="2026-01-01T00:00:00Z", size_bytes=100,
        google_file_id="verified-destination", media_category="video",
    )


class FakeEmbedding:
    provider_name = "ollama"
    model_name = "qwen3-embedding:0.6b"
    embedding_dimensions = 1024
    version = "v1"

    def __init__(self, values=None, error=None):
        self.values = values if values is not None else [0.0] * 1024
        self.error = error
        self.calls = []

    def embed_text(self, text):
        self.calls.append(text)
        if self.error:
            raise self.error
        return self.values, None


class ManualManifestTests(unittest.TestCase):
    def test_valid_human_metadata(self):
        review = load([row()])[0]
        self.assertEqual(review.errors, ())
        self.assertEqual(review.entry.metadata.doctor_name, None)

    def test_missing_reviewer_fails_closed(self):
        review = load([row(reviewed_by="")])[0]
        self.assertIsNone(review.entry)
        self.assertIn("reviewed_by is required", review.errors)

    def test_missing_timestamp_fails_closed(self):
        review = load([row(reviewed_at="")])[0]
        self.assertIsNone(review.entry)
        self.assertIn("reviewed_at is required", review.errors)

    def test_malformed_or_extra_semantic_field_is_rejected(self):
        review = load([row(content_type="Invented Type", audience="public")])[0]
        self.assertIsNone(review.entry)
        self.assertTrue(any("unapproved fields" in error for error in review.errors))
        self.assertIn("content_type is not in the controlled list", review.errors)

    def test_unknown_or_noncanonical_asset_is_not_importable(self):
        reviews = load([row()])
        report = dry_run_report(reviews, {ASSET_ID: None})
        self.assertEqual(report["assets_missing_or_noncanonical"], 1)
        self.assertEqual(report["semantic_rows_would_create"], 0)
        self.assertEqual(report["database_writes"], 0)
        self.assertEqual(report["embedding_calls"], 0)

    def test_twenty_asset_benchmark_preserves_five_and_validates_fifteen_reviews(self):
        benchmark = load_and_review_manifest("data/semantic_manual_benchmark_20.json")
        baseline = load_and_review_manifest("data/semantic_manual_search_pilot.json")
        self.assertEqual(len(benchmark), 20)
        self.assertEqual(sum(review.entry is not None for review in benchmark), 20)
        self.assertEqual(sum(review.entry is None for review in benchmark), 0)
        for expected, actual in zip(baseline, benchmark[:5], strict=True):
            self.assertEqual(actual.entry, expected.entry)
        raw = json.loads(Path("data/semantic_manual_benchmark_20.json").read_text())
        self.assertEqual(sum(row["reviewed_by"] == "Codex-assisted evidence review" for row in raw["assets"][5:]), 14)

    def test_benchmark_dry_run_reports_reviewed_rows_without_calls_or_writes(self):
        reviews = load_and_review_manifest("data/semantic_manual_benchmark_20.json")
        candidates = {review.asset_id: candidate() for review in reviews}
        baseline_ids = {review.asset_id for review in reviews[:5]}
        report = dry_run_report(
            reviews,
            candidates,
            existing_semantic_ids=baseline_ids,
            existing_embedding_ids=baseline_ids,
        )
        self.assertEqual(report["entries_valid"], 20)
        self.assertEqual(report["entries_invalid"], 0)
        self.assertEqual(report["semantic_rows_would_create"], 15)
        self.assertEqual(report["embedding_rows_would_create"], 15)
        self.assertEqual(report["embedding_calls"], 0)
        self.assertEqual(report["vision_calls"], 0)

    def test_query_benchmark_has_twenty_ready_filename_independent_queries(self):
        payload = json.loads(Path("data/semantic_search_benchmark_20.json").read_text())
        self.assertEqual(len(payload["queries"]), 20)
        self.assertTrue(all(row["status"] == "ready" for row in payload["queries"]))
        self.assertGreaterEqual(sum(row["type"] in {"semantic_paraphrase", "natural_conversational"} for row in payload["queries"]), 8)
        forbidden = ("IMG_", "DSC", "PHOTO-", "00000000-")
        self.assertTrue(all(not any(value in row["query"] for value in forbidden) for row in payload["queries"]))
        self.assertEqual(payload["success_standard"]["top_3_target"], 18)

    def test_assisted_description_provenance_is_preserved_for_future_import(self):
        review = load([row(description_provider="codex-assisted", description_model="evidence-reviewed", description_version="codex-review-v1")])[0]
        result = build_manual_index_result(review.entry, candidate(), FakeEmbedding())
        self.assertEqual(result.description_provider, "codex-assisted")
        self.assertEqual(result.description_model, "evidence-reviewed")
        self.assertEqual(result.description_version, "codex-review-v1")


class ManualEmbeddingTests(unittest.TestCase):
    def entry(self):
        return load([row()])[0].entry

    def test_embedding_text_uses_only_approved_fields_and_manual_provenance(self):
        provider = FakeEmbedding()
        result = build_manual_index_result(self.entry(), candidate(), provider)
        self.assertEqual(result.description_provider, MANUAL_DESCRIPTION_PROVIDER)
        self.assertEqual(provider.calls, [
            "Clinic Environment Clinic interior A human-reviewed description of a generic clinic interior."
        ])
        self.assertNotIn("opaque.mp4", provider.calls[0])

    def test_embedding_dimension_mismatch_is_rejected_without_padding(self):
        provider = FakeEmbedding([0.0] * 1000)
        with self.assertRaises(ManualPilotValidationError):
            build_manual_index_result(self.entry(), candidate(), provider)

    def test_non_finite_embedding_is_rejected(self):
        values = [0.0] * 1024
        values[5] = math.nan
        with self.assertRaises(ManualPilotValidationError):
            build_manual_index_result(self.entry(), candidate(), FakeEmbedding(values))

    def test_ollama_unavailable_is_propagated_without_vision_fallback(self):
        provider = FakeEmbedding(error=ProviderRetryableError("local endpoint unavailable"))
        with self.assertRaises(ProviderRetryableError):
            build_manual_index_result(self.entry(), candidate(), provider)

    def test_external_embedding_provider_is_blocked_before_call(self):
        provider = FakeEmbedding()
        provider.provider_name = "openai"
        with self.assertRaises(ManualPilotValidationError):
            build_manual_index_result(self.entry(), candidate(), provider)
        self.assertEqual(provider.calls, [])


if __name__ == "__main__":
    unittest.main()
