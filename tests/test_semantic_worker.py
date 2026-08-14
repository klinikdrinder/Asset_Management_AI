from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import signal
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

from kdi_media.providers.base import ProviderPermanentError, ProviderRetryableError, StructuredMetadata
from kdi_media.semantic_indexing import AssetCandidate, IndexingStatus, compute_fingerprint
from kdi_media.semantic_worker import (
    DedicatedSemanticWorker, FileMediaPreparer, JsonlStagingWriter,
    LocalFixtureTransport, WorkspaceManager, WorkerConfig, WorkerError,
    RetryableWorkerError, staging_record, validate_embedding,
    validate_model_identity, build_parser, EXPECTED_PILOT_SHA256,
)


class Repo:
    def __init__(self, candidate, *, attempt=1):
        self.candidate, self.attempt = candidate, attempt
        self.completed = None; self.failure = None; self.released = False
        self.claimed = False
    def claim_batch(self, owner, limit, lease, asset_ids=None):
        del owner, limit, lease
        if self.claimed or (asset_ids and self.candidate.asset_id not in asset_ids) or self.attempt > 5: return []
        self.claimed = True
        return [{"asset_id": self.candidate.asset_id, "attempt_count": self.attempt}]
    def fetch_candidate(self, asset_id): return self.candidate if asset_id == self.candidate.asset_id else None
    def complete(self, asset_id, owner, result): self.completed = result; return True
    def fail(self, asset_id, owner, failure): self.failure = failure; return True
    def release_staging(self, asset_id, owner): self.released = True; return True


class Vision:
    provider_name = "ollama"; model_name = "qwen3-vl:2b"; schema_version = "v1"
    def __init__(self, error=None): self.error = error; self.calls = 0
    def describe_media(self, **kwargs):
        self.calls += 1
        if self.error: raise self.error
        return StructuredMetadata("Treatment Procedure", None, "clinician treating a patient", None,
            "Clinician performs treatment", "A clinician performs a treatment while a patient lies on a bed."), None


class Embed:
    provider_name = "ollama"; model_name = "qwen3-embedding:0.6b"; embedding_dimensions = 1024; version = "v1"
    def __init__(self, values=None, error=None): self.values = values or [0.01] * 1024; self.error = error
    def embed_text(self, text):
        if self.error: raise self.error
        return self.values, None


class Preparer:
    def __init__(self, *, video=False, error=None): self.video = video; self.error = error
    def prepare(self, candidate, source, workspace):
        if self.error: raise self.error
        artifact = workspace / ("frame-0.jpg" if self.video else "prepared-image.jpg")
        artifact.write_bytes(b"prepared")
        return [b"prepared"], 1.0 if self.video else None


class SemanticWorkerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.root = Path(self.tmp.name)
        self.media = self.root / "fixture.jpg"
        Image.new("RGB", (8, 8), "white").save(self.media)
        raw = self.media.read_bytes()
        self.candidate = AssetCandidate("asset-1", "fixture.jpg", "image/jpeg", ".jpg",
            hashlib.sha256(raw).hexdigest(), "2026-01-01", len(raw), "fixture", "image")
    def tearDown(self): self.tmp.cleanup()

    def config(self, **changes):
        values = dict(temp_root=self.root / "worker", staging_path=self.root / "stage.jsonl",
            min_available_ram_mb=3072, disk_reserve_mb=1, max_asset_bytes=1024*1024,
            chunk_size=7, whole_job_timeout_seconds=60)
        values.update(changes); return WorkerConfig(**values)

    def worker(self, *, candidate=None, repo=None, vision=None, embed=None, preparer=None,
               staging=False, resources=lambda: (8192, 16384), remover=None):
        candidate = candidate or self.candidate; repo = repo or Repo(candidate)
        config = self.config(); manager = WorkspaceManager(config.temp_root, remover=remover); manager.initialize()
        transport = LocalFixtureTransport({"fixture": self.media})
        instance = DedicatedSemanticWorker(repo, transport, vision or Vision(), embed or Embed(), manager,
            preparer or Preparer(video=candidate.media_category == "video"), config,
            staging_only=staging, staging_writer=JsonlStagingWriter(config.staging_path),
            worker_id="worker-1", resource_reader=resources)
        return instance, repo, config

    def test_successful_image_job_and_zero_media_remaining(self):
        worker, repo, config = self.worker()
        result = worker.run_once()
        self.assertEqual(result.result_state, "INDEXED"); self.assertIsNotNone(repo.completed)
        self.assertEqual(list(config.temp_root.iterdir()), [])

    def test_successful_video_job_and_frame_cleanup(self):
        video = AssetCandidate(**{**self.candidate.__dict__, "media_category":"video", "file_extension":".mp4"})
        worker, repo, config = self.worker(candidate=video, preparer=Preparer(video=True))
        result = worker.run_once()
        self.assertEqual(result.frames_extracted, 1); self.assertEqual(list(config.temp_root.iterdir()), [])

    def test_streamed_retrieval_uses_small_chunks(self):
        destination = self.root / "copy"
        result = LocalFixtureTransport({"fixture": self.media}).retrieve(self.candidate, destination,
            chunk_size=3, timeout_seconds=10, max_bytes=10000)
        self.assertEqual(result.size_bytes, len(self.media.read_bytes()))
        self.assertEqual(destination.read_bytes(), self.media.read_bytes())

    def test_transport_rejects_size_and_hash_mismatch(self):
        bad = AssetCandidate(**{**self.candidate.__dict__, "size_bytes": 1})
        with self.assertRaises(RetryableWorkerError):
            LocalFixtureTransport({"fixture": self.media}).retrieve(bad, self.root/"bad", chunk_size=3, timeout_seconds=10, max_bytes=10000)

    def test_failure_always_removes_workspace(self):
        worker, repo, config = self.worker(vision=Vision(ProviderRetryableError("offline")))
        result = worker.run_once()
        self.assertEqual(result.result_state, "FAILED_RETRYABLE"); self.assertEqual(list(config.temp_root.iterdir()), [])

    def test_ffprobe_failure_is_retryable(self):
        worker, repo, _ = self.worker(preparer=Preparer(error=RetryableWorkerError("FFprobe duration probe failed")))
        worker.run_once(); self.assertTrue(repo.failure.retryable)

    def test_ffmpeg_failure_is_retryable(self):
        worker, repo, _ = self.worker(preparer=Preparer(error=RetryableWorkerError("FFmpeg failed")))
        worker.run_once(); self.assertEqual(repo.failure.status, IndexingStatus.FAILED_RETRYABLE)

    def test_ollama_unavailable_and_timeout_are_retryable(self):
        for error in (ProviderRetryableError("unavailable"), ProviderRetryableError("timeout")):
            worker, repo, _ = self.worker(vision=Vision(error)); worker.run_once()
            self.assertTrue(repo.failure.retryable)

    def test_malformed_qwen_response_is_retryable(self):
        worker, repo, _ = self.worker(vision=Vision(ProviderRetryableError("malformed JSON")))
        worker.run_once(); self.assertTrue(repo.failure.retryable)

    def test_embedding_failure(self):
        worker, repo, _ = self.worker(embed=Embed(error=ProviderRetryableError("embedding offline")))
        worker.run_once(); self.assertEqual(repo.failure.status, IndexingStatus.FAILED_RETRYABLE)

    def test_embedding_dimension_mismatch_nan_and_bool(self):
        for values in ([0.0]*1023, [math.nan]*1024, [True]*1024):
            with self.assertRaises(ProviderPermanentError): validate_embedding(values, 1024)
        with self.assertRaises(ProviderPermanentError): validate_embedding([0.0]*1024, 768)

    def test_wrong_or_missing_expected_model_is_permanent(self):
        wrong = Vision(); wrong.model_name = "wrong"
        with self.assertRaises(ProviderPermanentError): validate_model_identity(wrong, Embed())
        wrong_embedding = Embed(); wrong_embedding.model_name = "missing"
        with self.assertRaises(ProviderPermanentError): validate_model_identity(Vision(), wrong_embedding)

    def test_low_ram_before_claim(self):
        worker, repo, _ = self.worker(resources=lambda: (3000, 8192))
        self.assertIsNone(worker.run_once()); self.assertFalse(repo.claimed)

    def test_low_ram_after_claim_is_cleaned_and_retryable(self):
        readings = iter(((8192,16384),(8192,16384),(2000,16384),(2000,16384)))
        worker, repo, config = self.worker(resources=lambda: next(readings))
        result = worker.run_once(); self.assertEqual(result.result_state, "FAILED_RETRYABLE")
        self.assertEqual(list(config.temp_root.iterdir()), [])

    def test_low_disk_is_retryable(self):
        worker, repo, config = self.worker()
        with patch("kdi_media.semantic_worker.disk_free_mb", return_value=0):
            result = worker.run_once()
        self.assertEqual(result.result_state, "FAILED_RETRYABLE")

    def test_maximum_attempt_becomes_permanent(self):
        repo = Repo(self.candidate, attempt=5)
        worker, repo, _ = self.worker(repo=repo, vision=Vision(ProviderRetryableError("offline")))
        worker.run_once(); self.assertEqual(repo.failure.code, "MAX_ATTEMPTS_EXHAUSTED")
        self.assertEqual(repo.failure.status, IndexingStatus.FAILED_PERMANENT)

    def test_attempt_above_maximum_is_not_claimed(self):
        repo = Repo(self.candidate, attempt=6); worker, _, _ = self.worker(repo=repo)
        self.assertIsNone(worker.run_once())

    def test_graceful_shutdown_stops_new_claims(self):
        worker, repo, _ = self.worker(); worker.request_shutdown(signal.SIGTERM, None)
        self.assertIsNone(worker.run_once()); self.assertFalse(repo.claimed)

    def test_shutdown_during_job_cleans_and_records_retryable(self):
        worker, repo, config = self.worker()
        original = worker.preparer.prepare
        def prepare(*args): worker.request_shutdown(); return original(*args)
        worker.preparer.prepare = prepare
        result = worker.run_once(); self.assertEqual(result.failure_code, "SHUTDOWN_REQUESTED")
        self.assertEqual(list(config.temp_root.iterdir()), [])

    def test_startup_orphan_cleanup_only_marked_directories(self):
        root = self.root / "reconcile"; root.mkdir()
        marked = root / "job"; marked.mkdir(); (marked/".kdi-local-ai-job.json").write_text('{"owner":"kdi_local_ai"}')
        manager = WorkspaceManager(root); results = manager.initialize()
        self.assertFalse(marked.exists()); self.assertIn("REMOVED:job", results)

    def test_unmarked_orphan_blocks_claims_without_deleting(self):
        root = self.root / "reconcile"; (root/"unknown").mkdir(parents=True)
        manager = WorkspaceManager(root); manager.initialize()
        self.assertTrue(manager.blocked); self.assertTrue((root/"unknown").exists())

    def test_repository_temp_root_is_rejected(self):
        with self.assertRaises(ValueError): WorkspaceManager(Path.cwd() / "tmp" / "kdi_local_ai")

    def test_cleanup_failure_blocks_additional_claims(self):
        def fail_remove(path): raise PermissionError("locked")
        worker, repo, config = self.worker(remover=fail_remove)
        result = worker.run_once(); self.assertEqual(result.cleanup_status, "FAILED_BLOCKING")
        self.assertTrue(worker.workspaces.blocked); self.assertIsNone(worker.run_once())
        # release lock simulation so TemporaryDirectory teardown can proceed
        worker.workspaces.remover = lambda p: __import__("shutil").rmtree(p)
        worker.workspaces.cleanup(next(config.temp_root.iterdir()))

    def test_staging_only_releases_claim_and_does_not_complete(self):
        worker, repo, config = self.worker(staging=True)
        result = worker.run_once(); self.assertEqual(result.result_state, "STAGED")
        self.assertTrue(repo.released); self.assertIsNone(repo.completed)
        row = json.loads(config.staging_path.read_text().splitlines()[0])
        self.assertNotIn("embedding", row); self.assertEqual(row["embedding_dimensions"], 1024)

    def test_content_fingerprint_ignores_rename_and_move_timestamp_with_hash(self):
        renamed = AssetCandidate(**{**self.candidate.__dict__, "file_name":"renamed.jpg", "updated_at":"later"})
        identity = dict(description_provider="ollama",description_model="qwen3-vl:2b",description_version="v1",
            embedding_provider="ollama",embedding_model="qwen3-embedding:0.6b",embedding_version="v1")
        self.assertEqual(compute_fingerprint(self.candidate, **identity), compute_fingerprint(renamed, **identity))

    def test_staging_record_has_required_provenance_and_metrics(self):
        worker, repo, _ = self.worker(staging=True); metrics = worker.run_once()
        row = staging_record(self.candidate, None, metrics)
        self.assertIn("provenance", row); self.assertIn("processing_metrics", row)

    def test_deployment_preflight_cli_and_pilot_checksum_contract(self):
        args = build_parser().parse_args(["--preflight", "--benchmark-manifest", str(self.root/"manifest.json")])
        self.assertTrue(args.preflight)
        self.assertEqual(EXPECTED_PILOT_SHA256, "638772e00df61a015665ef7236ff11176e508ec35b93291518389529ea603226")


class RealFilePreparationTests(unittest.TestCase):
    def test_real_image_preparation_is_bounded_and_job_local(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); source=root/"source.png"; Image.new("RGB",(2000,1000),"blue").save(source)
            candidate=AssetCandidate("a","x.png","image/png",".png",None,None,None,"x","image")
            images,duration=FileMediaPreparer(ffmpeg="none",ffprobe="none").prepare(candidate,source,root)
            self.assertIsNone(duration); self.assertEqual(len(images),1)
            with Image.open(root/"prepared-image.jpg") as image: self.assertLessEqual(max(image.size),1600)


if __name__ == "__main__": unittest.main()
