"""Headless, local-only semantic indexing worker.

The worker streams one approved canonical asset into a disposable job
directory, prepares bounded images/frames, invokes loopback Ollama, and always
removes the job directory. It is intentionally independent of the dashboard,
nightly sync, and the legacy pilot importer.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
from typing import Any, Callable, Iterable, Mapping, Protocol, Sequence
from urllib.request import urlopen

from PIL import Image, ImageOps

from kdi_media.image_input import MAX_IMAGE_DIMENSION, MAX_IMAGE_PIXELS
from kdi_media.providers.base import (
    DescriptionProvider, EmbeddingProvider, ProviderPermanentError,
    ProviderRetryableError, StructuredMetadata,
)
from kdi_media.semantic_indexing import (
    AssetCandidate, FailureInfo, IndexResult, IndexingStatus,
    SemanticIndexRepository, build_searchable_text, compute_fingerprint,
    compute_searchable_text_hash,
)
from kdi_media.step9_hashing import iter_drive_content
from kdi_media.video_frames import DEFAULT_MAX_FRAMES, MAX_FRAME_DIMENSION, limit_transcript

EXPECTED_VISION_MODEL = "qwen3-vl:2b"
EXPECTED_EMBEDDING_MODEL = "qwen3-embedding:0.6b"
EXPECTED_EMBEDDING_DIMENSIONS = 1024
EXPECTED_PILOT_SHA256 = "638772e00df61a015665ef7236ff11176e508ec35b93291518389529ea603226"
MIN_AVAILABLE_RAM_MB = 3072
MAX_ATTEMPTS = 5
WORKER_MARKER = ".kdi-local-ai-job.json"


class WorkerError(RuntimeError):
    code = "WORKER_ERROR"
    retryable = False


class RetryableWorkerError(WorkerError):
    retryable = True


class CleanupBlockedError(WorkerError):
    code = "CLEANUP_BLOCKED"


class ShutdownRequested(RetryableWorkerError):
    code = "SHUTDOWN_REQUESTED"


@dataclass(frozen=True)
class DownloadResult:
    size_bytes: int
    sha256: str
    seconds: float


@dataclass
class JobMetrics:
    worker_id: str
    job_id: str
    asset_id: str
    media_type: str
    attempt_number: int
    file_size: int = 0
    video_duration: float | None = None
    frames_extracted: int = 0
    ram_before_mb: int = 0
    minimum_ram_mb: int = MIN_AVAILABLE_RAM_MB
    ram_after_mb: int = 0
    disk_before_mb: int = 0
    disk_after_mb: int = 0
    retrieval_time: float = 0.0
    preparation_time: float = 0.0
    vision_time: float = 0.0
    embedding_time: float = 0.0
    db_completion_time: float = 0.0
    total_time: float = 0.0
    result_state: str = IndexingStatus.PROCESSING.value
    failure_code: str | None = None
    cleanup_status: str = "PENDING"


@dataclass(frozen=True)
class WorkerConfig:
    temp_root: Path
    staging_path: Path
    min_available_ram_mb: int = MIN_AVAILABLE_RAM_MB
    disk_reserve_mb: int = 2048
    derivative_headroom_multiplier: float = 1.5
    max_asset_bytes: int = 20 * 1024 * 1024 * 1024
    chunk_size: int = 8 * 1024 * 1024
    download_timeout_seconds: int = 900
    ffprobe_timeout_seconds: int = 30
    ffmpeg_timeout_seconds: int = 30
    vision_timeout_seconds: int = 300
    whole_job_timeout_seconds: int = 1200
    lease_seconds: int = 1200
    poll_seconds: float = 5.0

    @classmethod
    def from_environment(cls) -> "WorkerConfig":
        root = Path(os.environ.get("KDI_LOCAL_AI_TEMP_ROOT", tempfile.gettempdir()))
        root = root.expanduser().resolve() / "kdi_local_ai"
        staging = Path(os.environ.get("KDI_LOCAL_AI_STAGING_PATH", "data/semantic_worker_staging.jsonl")).resolve()
        minimum = _env_int("LOCAL_AI_MIN_AVAILABLE_RAM_MB", MIN_AVAILABLE_RAM_MB)
        if minimum < MIN_AVAILABLE_RAM_MB:
            raise ValueError("LOCAL_AI_MIN_AVAILABLE_RAM_MB cannot be lower than 3072")
        return cls(
            temp_root=root, staging_path=staging, min_available_ram_mb=minimum,
            disk_reserve_mb=_env_int("KDI_LOCAL_AI_DISK_RESERVE_MB", 2048),
            max_asset_bytes=_env_int("KDI_LOCAL_AI_MAX_ASSET_BYTES", 20 * 1024**3),
            chunk_size=_env_int("KDI_LOCAL_AI_DOWNLOAD_CHUNK_BYTES", 8 * 1024**2),
            download_timeout_seconds=_env_int("KDI_LOCAL_AI_DOWNLOAD_TIMEOUT_SECONDS", 900),
            ffprobe_timeout_seconds=_env_int("KDI_FFPROBE_TIMEOUT_SECONDS", 30),
            ffmpeg_timeout_seconds=_env_int("KDI_FFMPEG_TIMEOUT_SECONDS", 30),
            vision_timeout_seconds=_env_int("OLLAMA_VISION_TIMEOUT_SECONDS", 300),
            whole_job_timeout_seconds=_env_int("KDI_LOCAL_AI_JOB_TIMEOUT_SECONDS", 1200),
            lease_seconds=_env_int("KDI_LOCAL_AI_LEASE_SECONDS", 1200),
            poll_seconds=float(os.environ.get("KDI_LOCAL_AI_POLL_SECONDS", "5")),
        )


class StreamTransport(Protocol):
    def retrieve(self, candidate: AssetCandidate, destination: Path, *,
                 chunk_size: int, timeout_seconds: int, max_bytes: int) -> DownloadResult: ...


class DriveStreamTransport:
    """Chunked, read-only Google Drive to job-local file transport."""

    def __init__(self, service: Any) -> None:
        self.service = service

    def retrieve(self, candidate: AssetCandidate, destination: Path, *,
                 chunk_size: int, timeout_seconds: int, max_bytes: int) -> DownloadResult:
        started = time.monotonic()
        digest, count = hashlib.sha256(), 0
        with destination.open("xb") as output:
            for chunk in iter_drive_content(self.service, candidate.google_file_id, chunk_size=chunk_size):
                if time.monotonic() - started > timeout_seconds:
                    raise RetryableWorkerError("Drive retrieval timed out")
                count += len(chunk)
                if count > max_bytes:
                    raise WorkerError("Asset exceeds configured maximum size")
                output.write(chunk)
                digest.update(chunk)
        _validate_download(candidate, count, digest.hexdigest())
        return DownloadResult(count, digest.hexdigest(), time.monotonic() - started)


class LocalFixtureTransport:
    """Synthetic-test transport with the same bounded chunked behavior."""

    def __init__(self, sources: Mapping[str, Path]) -> None:
        self.sources = sources

    def retrieve(self, candidate: AssetCandidate, destination: Path, *,
                 chunk_size: int, timeout_seconds: int, max_bytes: int) -> DownloadResult:
        started = time.monotonic()
        source = self.sources[candidate.google_file_id]
        digest, count = hashlib.sha256(), 0
        with source.open("rb") as incoming, destination.open("xb") as output:
            while chunk := incoming.read(chunk_size):
                if time.monotonic() - started > timeout_seconds:
                    raise RetryableWorkerError("Fixture retrieval timed out")
                count += len(chunk)
                if count > max_bytes:
                    raise WorkerError("Asset exceeds configured maximum size")
                digest.update(chunk)
                output.write(chunk)
        _validate_download(candidate, count, digest.hexdigest())
        return DownloadResult(count, digest.hexdigest(), time.monotonic() - started)


class WorkspaceManager:
    def __init__(self, root: Path, *, remover: Callable[[Path], None] | None = None) -> None:
        self.root = root.resolve()
        _validate_temp_root(self.root)
        self.remover = remover or (lambda path: shutil.rmtree(path))
        self.blocked = False

    def initialize(self) -> list[str]:
        self.root.mkdir(parents=True, exist_ok=True)
        probe = self.root / ".write-probe"
        probe.write_text("ok", encoding="ascii")
        probe.unlink()
        results: list[str] = []
        for child in self.root.iterdir():
            if not child.is_dir():
                continue
            marker = child / WORKER_MARKER
            if not marker.is_file():
                self.blocked = True
                results.append(f"UNRESOLVED_UNMARKED:{child.name}")
                continue
            try:
                marker_data = json.loads(marker.read_text(encoding="utf-8"))
                if marker_data.get("owner") != "kdi_local_ai":
                    raise ValueError("wrong owner")
                self._remove_verified(child)
                results.append(f"REMOVED:{child.name}")
            except Exception:
                self.blocked = True
                results.append(f"CLEANUP_FAILED:{child.name}")
        return results

    def create(self, job_id: str) -> Path:
        if self.blocked:
            raise CleanupBlockedError("Unresolved worker media blocks new claims")
        safe = "".join(c for c in job_id if c.isalnum() or c in "-_")
        if not safe or safe != job_id:
            raise WorkerError("Unsafe job id")
        path = (self.root / safe).resolve()
        if path.parent != self.root:
            raise WorkerError("Job workspace escaped configured root")
        path.mkdir(exist_ok=False)
        (path / WORKER_MARKER).write_text(json.dumps({"owner": "kdi_local_ai", "job_id": job_id}), encoding="utf-8")
        return path

    def cleanup(self, path: Path) -> None:
        try:
            self._remove_verified(path.resolve())
        except Exception as exc:
            self.blocked = True
            raise CleanupBlockedError(f"Job cleanup failed for {path.name}") from exc

    def _remove_verified(self, path: Path) -> None:
        if path.parent != self.root or not (path / WORKER_MARKER).is_file():
            raise CleanupBlockedError("Refusing cleanup outside marked worker directory")
        self.remover(path)
        if path.exists():
            raise CleanupBlockedError("Worker job directory remains after cleanup")


class FileMediaPreparer:
    def __init__(self, *, ffmpeg: str, ffprobe: str, probe_timeout: int = 30,
                 frame_timeout: int = 30, max_frames: int = DEFAULT_MAX_FRAMES) -> None:
        self.ffmpeg, self.ffprobe = ffmpeg, ffprobe
        self.probe_timeout, self.frame_timeout, self.max_frames = probe_timeout, frame_timeout, max_frames

    def prepare(self, candidate: AssetCandidate, source: Path, workspace: Path) -> tuple[list[bytes], float | None]:
        if candidate.media_category == "image":
            destination = workspace / "prepared-image.jpg"
            previous = Image.MAX_IMAGE_PIXELS
            Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS
            try:
                with Image.open(source) as opened:
                    image = ImageOps.exif_transpose(opened).convert("RGB")
                    image.thumbnail((MAX_IMAGE_DIMENSION, MAX_IMAGE_DIMENSION), Image.Resampling.LANCZOS)
                    image.save(destination, "JPEG", quality=88, optimize=True)
            except (OSError, ValueError) as exc:
                raise WorkerError("Corrupt or unsafe image") from exc
            finally:
                Image.MAX_IMAGE_PIXELS = previous
            return [destination.read_bytes()], None

        duration = self._duration(source)
        images: list[bytes] = []
        timestamps = _timestamps(duration, self.max_frames)
        for index, timestamp in enumerate(timestamps):
            frame = workspace / f"frame-{index}.jpg"
            try:
                subprocess.run([
                    self.ffmpeg, "-ss", f"{timestamp:.3f}", "-i", str(source),
                    "-frames:v", "1", "-vf",
                    f"scale={MAX_FRAME_DIMENSION}:{MAX_FRAME_DIMENSION}:force_original_aspect_ratio=decrease",
                    "-q:v", "3", "-y", str(frame),
                ], capture_output=True, timeout=self.frame_timeout, check=True)
            except (subprocess.SubprocessError, OSError) as exc:
                raise RetryableWorkerError("FFmpeg representative-frame extraction failed") from exc
            if frame.is_file():
                images.append(frame.read_bytes())
        if not images:
            raise WorkerError("No representative video frames were extracted")
        return images, duration

    def _duration(self, source: Path) -> float:
        try:
            result = subprocess.run([
                self.ffprobe, "-v", "error", "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1", str(source),
            ], capture_output=True, text=True, timeout=self.probe_timeout, check=True)
            return max(0.0, float(result.stdout.strip()))
        except (subprocess.SubprocessError, OSError, ValueError) as exc:
            raise RetryableWorkerError("FFprobe duration probe failed") from exc


class JsonlStagingWriter:
    def __init__(self, path: Path) -> None:
        self.path = path

    def write(self, record: Mapping[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as output:
            output.write(json.dumps(record, sort_keys=True, default=str) + "\n")


class DedicatedSemanticWorker:
    def __init__(self, repository: SemanticIndexRepository, transport: StreamTransport,
                 description_provider: DescriptionProvider, embedding_provider: EmbeddingProvider,
                 workspaces: WorkspaceManager, preparer: FileMediaPreparer, config: WorkerConfig,
                 *, staging_only: bool = False, staging_writer: JsonlStagingWriter | None = None,
                 worker_id: str | None = None, resource_reader: Callable[[], tuple[int, int]] | None = None) -> None:
        self.repository, self.transport = repository, transport
        self.description_provider, self.embedding_provider = description_provider, embedding_provider
        self.workspaces, self.preparer, self.config = workspaces, preparer, config
        self.staging_only, self.staging_writer = staging_only, staging_writer
        self.worker_id = worker_id or f"{socket.gethostname()}-{os.getpid()}"
        self.resource_reader = resource_reader or read_memory_mb
        self.stop_event = threading.Event()

    def request_shutdown(self, *_args: Any) -> None:
        self.stop_event.set()

    def run_once(self, *, allowlist: Sequence[str] | None = None) -> JobMetrics | None:
        if self.stop_event.is_set() or self.workspaces.blocked:
            return None
        available, _total = self.resource_reader()
        if available < self.config.min_available_ram_mb:
            return None  # no claim on low RAM
        claims = self.repository.claim_batch(self.worker_id, 1, self.config.lease_seconds, asset_ids=allowlist)
        if not claims:
            return None
        claim = claims[0]
        return self.process_claim(str(claim["asset_id"]), int(claim.get("attempt_count") or 1))

    def process_claim(self, asset_id: str, attempt: int) -> JobMetrics:
        started = time.monotonic()
        candidate = self.repository.fetch_candidate(asset_id)
        job_id = f"{asset_id}-{attempt}"
        media_type = candidate.media_category if candidate else "unknown"
        metrics = JobMetrics(self.worker_id, job_id, asset_id, media_type, attempt)
        workspace: Path | None = None
        failure: FailureInfo | None = None
        result: IndexResult | None = None
        try:
            if candidate is None:
                raise WorkerError("Candidate is no longer eligible")
            workspace = self.workspaces.create(job_id)
            metrics.ram_before_mb, _ = self.resource_reader()
            metrics.disk_before_mb = disk_free_mb(self.config.temp_root)
            self._resource_gate(candidate)
            source = workspace / ("source" + (candidate.file_extension or ".bin"))
            downloaded = self.transport.retrieve(candidate, source, chunk_size=self.config.chunk_size,
                                                  timeout_seconds=self.config.download_timeout_seconds,
                                                  max_bytes=self.config.max_asset_bytes)
            metrics.file_size, metrics.retrieval_time = downloaded.size_bytes, downloaded.seconds
            _deadline(started, self.config.whole_job_timeout_seconds)
            preparation = time.monotonic()
            images, duration = self.preparer.prepare(candidate, source, workspace)
            metrics.preparation_time = time.monotonic() - preparation
            metrics.video_duration, metrics.frames_extracted = duration, len(images) if duration is not None else 0
            if self.stop_event.is_set():
                raise ShutdownRequested("Shutdown requested after safe preparation boundary")
            vision = time.monotonic()
            metadata, vision_cost = self.description_provider.describe_media(
                file_name=candidate.file_name, mime_type=candidate.mime_type or "application/octet-stream",
                media_category=candidate.media_category, images=images,
                transcript=limit_transcript(candidate.transcript),
            )
            metrics.vision_time = time.monotonic() - vision
            searchable = build_searchable_text(metadata=metadata)
            embedding_started = time.monotonic()
            embedding, embedding_cost = self.embedding_provider.embed_text(searchable)
            metrics.embedding_time = time.monotonic() - embedding_started
            validate_embedding(embedding, self.embedding_provider.embedding_dimensions)
            result = IndexResult(
                metadata=metadata, embedding=embedding,
                embedding_provider=self.embedding_provider.provider_name,
                embedding_model=self.embedding_provider.model_name,
                embedding_dimensions=self.embedding_provider.embedding_dimensions,
                embedding_version=self.embedding_provider.version,
                description_provider=self.description_provider.provider_name,
                description_model=self.description_provider.model_name,
                description_version=self.description_provider.schema_version,
                searchable_text=searchable, searchable_text_hash=compute_searchable_text_hash(searchable),
                fingerprint=compute_fingerprint(candidate,
                    description_provider=self.description_provider.provider_name,
                    description_model=self.description_provider.model_name,
                    description_version=self.description_provider.schema_version,
                    embedding_provider=self.embedding_provider.provider_name,
                    embedding_model=self.embedding_provider.model_name,
                    embedding_version=self.embedding_provider.version),
                cost_usd=(vision_cost or 0) + (embedding_cost or 0) or None,
            )
            completion = time.monotonic()
            if self.staging_only:
                metrics.result_state = "STAGED"
                release = getattr(self.repository, "release_staging", None)
                if release and not release(asset_id, self.worker_id):
                    raise WorkerError("Claim lost while releasing staged result")
            elif not self.repository.complete(asset_id, self.worker_id, result):
                raise WorkerError("Claim lost before atomic completion")
            else:
                metrics.result_state = IndexingStatus.INDEXED.value
            metrics.db_completion_time = time.monotonic() - completion
        except (ProviderRetryableError, RetryableWorkerError, TimeoutError) as exc:
            failure = FailureInfo(IndexingStatus.FAILED_RETRYABLE, getattr(exc, "code", "TRANSIENT_FAILURE"), str(exc), True)
        except (ProviderPermanentError, WorkerError, ValueError) as exc:
            failure = FailureInfo(IndexingStatus.FAILED_PERMANENT, getattr(exc, "code", "PERMANENT_FAILURE"), str(exc), False)
        except Exception as exc:
            failure = FailureInfo(IndexingStatus.FAILED_RETRYABLE, "UNEXPECTED_FAILURE", type(exc).__name__, True)
        finally:
            cleanup_error: Exception | None = None
            if workspace is not None:
                try:
                    self.workspaces.cleanup(workspace)
                    metrics.cleanup_status = "VERIFIED_REMOVED"
                except Exception as exc:
                    cleanup_error = exc
                    metrics.cleanup_status = "FAILED_BLOCKING"
            else:
                metrics.cleanup_status = "NOT_CREATED"
            metrics.ram_after_mb, _ = self.resource_reader()
            metrics.disk_after_mb = disk_free_mb(self.config.temp_root)
            metrics.total_time = time.monotonic() - started
            if cleanup_error:
                failure = FailureInfo(IndexingStatus.FAILED_PERMANENT, "CLEANUP_BLOCKED", str(cleanup_error), False)
            if failure:
                if attempt >= MAX_ATTEMPTS:
                    failure = FailureInfo(IndexingStatus.FAILED_PERMANENT, "MAX_ATTEMPTS_EXHAUSTED", failure.reason, False)
                metrics.result_state, metrics.failure_code = failure.status.value, failure.code
                self.repository.fail(asset_id, self.worker_id, failure)
            if self.staging_writer:
                self.staging_writer.write(staging_record(candidate, result, metrics))
        return metrics

    def _resource_gate(self, candidate: AssetCandidate) -> None:
        available, _ = self.resource_reader()
        if available < self.config.min_available_ram_mb:
            raise RetryableWorkerError("Available RAM fell below configured minimum")
        required = self.config.disk_reserve_mb + math.ceil(((candidate.size_bytes or 0) * self.config.derivative_headroom_multiplier) / 1024**2)
        if disk_free_mb(self.config.temp_root) < required:
            raise RetryableWorkerError("Worker temporary disk headroom is insufficient")


def staging_record(candidate: AssetCandidate | None, result: IndexResult | None, metrics: JobMetrics) -> dict[str, Any]:
    metadata = result.metadata if result else None
    return {
        "job_id": metrics.job_id, "asset_id": metrics.asset_id,
        "source_reference": candidate.google_file_id if candidate else None,
        "filename": candidate.file_name if candidate else None,
        "media_type": metrics.media_type,
        "content_type": metadata.content_type if metadata else None,
        "treatment": metadata.treatment if metadata else None,
        "subject": metadata.subject if metadata else None,
        "doctor_name": metadata.doctor_name if metadata else None,
        "ai_description": metadata.ai_description if metadata else None,
        "short_caption": metadata.short_caption if metadata else None,
        "vision_provider": result.description_provider if result else None,
        "vision_model": result.description_model if result else None,
        "semantic_schema_version": result.description_version if result else None,
        "embedding_provider": result.embedding_provider if result else None,
        "embedding_model": result.embedding_model if result else None,
        "embedding_dimensions": result.embedding_dimensions if result else None,
        "provenance": {"content_sha256": candidate.content_hash if candidate else None,
                       "evidence": "prepared local media and trusted metadata" if result else None},
        "processing_metrics": asdict(metrics), "cleanup_result": metrics.cleanup_status,
        "result_state": metrics.result_state,
    }


def validate_embedding(values: Sequence[float], configured_dimensions: int) -> None:
    if configured_dimensions != EXPECTED_EMBEDDING_DIMENSIONS:
        raise ProviderPermanentError("Configured embedding dimensions must be exactly 1024")
    if len(values) != EXPECTED_EMBEDDING_DIMENSIONS:
        raise ProviderPermanentError(f"Embedding dimension mismatch: expected 1024, got {len(values)}")
    if not all(isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) for value in values):
        raise ProviderPermanentError("Embedding contains non-numeric or non-finite values")


def validate_model_identity(description: DescriptionProvider, embedding: EmbeddingProvider) -> None:
    if (description.provider_name, description.model_name) != ("ollama", EXPECTED_VISION_MODEL):
        raise ProviderPermanentError("Dedicated worker requires Ollama qwen3-vl:2b")
    if (embedding.provider_name, embedding.model_name, embedding.embedding_dimensions) != (
        "ollama", EXPECTED_EMBEDDING_MODEL, EXPECTED_EMBEDDING_DIMENSIONS
    ):
        raise ProviderPermanentError(
            "Dedicated worker requires Ollama qwen3-embedding:0.6b at 1024 dimensions"
        )


def startup_preflight(config: WorkerConfig, *, ffmpeg: str, ffprobe: str,
                      check_ollama: bool = True) -> dict[str, Any]:
    available, total = read_memory_mb()
    disk = disk_free_mb(config.temp_root)
    report = {"total_ram_mb": total, "available_ram_mb": available,
              "minimum_ram_mb": config.min_available_ram_mb, "disk_free_mb": disk,
              "disk_reserve_mb": config.disk_reserve_mb,
              "ffmpeg": bool(shutil.which(ffmpeg) or Path(ffmpeg).is_file()),
              "ffprobe": bool(shutil.which(ffprobe) or Path(ffprobe).is_file())}
    report["ram_ok"] = available >= config.min_available_ram_mb
    report["disk_ok"] = disk >= config.disk_reserve_mb
    if check_ollama:
        with urlopen("http://127.0.0.1:11434/api/tags", timeout=10) as response:  # noqa: S310
            payload = json.load(response)
        names = {row.get("name") for row in payload.get("models", [])}
        report["ollama_models_ok"] = {EXPECTED_VISION_MODEL, EXPECTED_EMBEDDING_MODEL}.issubset(names)
    report["ok"] = all(report.get(key, False) for key in ("ram_ok", "disk_ok", "ffmpeg", "ffprobe")) and report.get("ollama_models_ok", True)
    return report


def deployment_readiness(config: WorkerConfig, *, manifest_path: Path) -> dict[str, Any]:
    """Non-media deployment gate. Never logs credential values or invokes AI."""
    checks: dict[str, dict[str, Any]] = {}
    blockers: list[str] = []

    def record(name: str, ok: bool, detail: Any) -> None:
        checks[name] = {"ok": bool(ok), "detail": detail}
        if not ok:
            blockers.append(f"{name}: {detail}")

    record("python_runtime", sys.version_info >= (3, 11),
           f"Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")
    try:
        from kdi_media.video_frames import resolve_ffmpeg_paths
        ffmpeg, ffprobe = resolve_ffmpeg_paths()
        record("ffmpeg", True, "available")
        record("ffprobe", True, "available")
    except Exception as exc:
        ffmpeg = ffprobe = ""
        record("ffmpeg", False, _safe_detail(exc)); record("ffprobe", False, _safe_detail(exc))

    try:
        available, total = read_memory_mb()
        record("ram", available >= config.min_available_ram_mb,
               {"total_mb": total, "available_mb": available, "required_available_mb": config.min_available_ram_mb})
    except Exception as exc:
        record("ram", False, _safe_detail(exc))
    try:
        free = disk_free_mb(config.temp_root)
        record("temporary_disk", free >= config.disk_reserve_mb,
               {"free_mb": free, "reserve_mb": config.disk_reserve_mb})
        probe = config.temp_root / ".deployment-readiness-probe"
        probe.write_text("ok", encoding="ascii"); probe.unlink()
        record("temp_root_permissions", True, "writable")
    except Exception as exc:
        record("temporary_disk", False, _safe_detail(exc)); record("temp_root_permissions", False, _safe_detail(exc))

    try:
        if not ffmpeg or not ffprobe:
            raise RuntimeError("FFmpeg dependencies unresolved")
        local = startup_preflight(config, ffmpeg=ffmpeg, ffprobe=ffprobe, check_ollama=True)
        record("ollama_endpoint", True, "loopback endpoint reachable")
        record("ollama_models", bool(local.get("ollama_models_ok")),
               "qwen3-vl:2b and qwen3-embedding:0.6b installed" if local.get("ollama_models_ok") else "required exact models missing")
    except Exception as exc:
        record("ollama_endpoint", False, _safe_detail(exc)); record("ollama_models", False, "not verifiable")

    try:
        from supabase import create_client
        client = create_client(_required_config("SUPABASE_URL"), _required_config("SUPABASE_SERVICE_ROLE_KEY"))
        client.table("asset_semantic_index").select("asset_id").limit(1).execute()
        record("supabase_connectivity", True, "connected")
        try:
            client.rpc("complete_semantic_index_atomically", {
                "requested_asset_id": "00000000-0000-4000-8000-000000000000",
                "requested_claim_owner": "deployment-readiness",
                "requested_metadata": {},
                "requested_embedding": {"embedding": [], "embedding_dimensions": 1024},
            }).execute()
            record("atomic_completion_rpc", False, "invalid readiness probe unexpectedly succeeded")
        except Exception as exc:
            message = str(exc)
            exists = "embedding must contain exactly 1024 values" in message
            record("atomic_completion_rpc", exists,
                   "available and validation-enforced" if exists else "function unavailable or schema cache not refreshed")
    except Exception as exc:
        record("supabase_connectivity", False, _safe_detail(exc)); record("atomic_completion_rpc", False, "not verifiable")

    try:
        from kdi_media.google_drive import create_service_account_readonly_drive_service, verify_folder_access
        service = create_service_account_readonly_drive_service()
        verify_folder_access(service, _required_config("DESTINATION_FOLDER_ID"))
        record("google_drive_service_account", True, "read-only KDI Master folder accessible")
    except Exception as exc:
        record("google_drive_service_account", False, _safe_detail(exc))

    try:
        digest = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
        record("exact_20_manifest", digest == EXPECTED_PILOT_SHA256,
               {"present": True, "sha256": digest, "expected_sha256": EXPECTED_PILOT_SHA256})
    except Exception as exc:
        record("exact_20_manifest", False, _safe_detail(exc))
    return {"status": "READY" if not blockers else "BLOCKED", "checks": checks, "blockers": blockers,
            "media_downloads": 0, "ai_calls": 0}


def read_memory_mb() -> tuple[int, int]:
    import ctypes
    if os.name == "nt":
        class Status(ctypes.Structure):
            _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong),
                        ("total", ctypes.c_ulonglong), ("available", ctypes.c_ulonglong),
                        ("total_page", ctypes.c_ulonglong), ("available_page", ctypes.c_ulonglong),
                        ("total_virtual", ctypes.c_ulonglong), ("available_virtual", ctypes.c_ulonglong),
                        ("available_extended", ctypes.c_ulonglong)]
        status = Status(); status.length = ctypes.sizeof(status)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            raise OSError("Unable to read memory status")
        return status.available // 1024**2, status.total // 1024**2
    values: dict[str, int] = {}
    with open("/proc/meminfo", encoding="ascii") as source:
        for line in source:
            key, value, *_ = line.split()
            values[key.rstrip(":")] = int(value) // 1024
    return values["MemAvailable"], values["MemTotal"]


def disk_free_mb(path: Path) -> int:
    path.mkdir(parents=True, exist_ok=True)
    return shutil.disk_usage(path).free // 1024**2


def _validate_temp_root(path: Path) -> None:
    """Reject repository/profile media locations even if misconfigured."""
    project = Path.cwd().resolve()
    if path == project or project in path.parents:
        raise ValueError("KDI worker temporary root cannot be inside the repository")
    if os.name == "nt" and path.drive.upper() in {"D:", "E:"}:
        raise ValueError("KDI worker temporary root cannot use D: or E:")
    forbidden_names = {"desktop", "downloads", "documents", "pictures", "videos"}
    if any(part.casefold() in forbidden_names for part in path.parts):
        raise ValueError("KDI worker temporary root cannot use a permanent user-media directory")


def _validate_download(candidate: AssetCandidate, size: int, digest: str) -> None:
    if candidate.size_bytes is not None and size != candidate.size_bytes:
        raise RetryableWorkerError("Downloaded size does not match canonical metadata")
    if candidate.content_hash and len(candidate.content_hash) == 64 and digest.casefold() != candidate.content_hash.casefold():
        raise WorkerError("Downloaded SHA-256 does not match canonical content")


def _timestamps(duration: float, count: int) -> list[float]:
    if duration <= 0: return [0.0]
    margin, count = duration * 0.05, max(1, min(count, DEFAULT_MAX_FRAMES))
    span = max(0.0, duration - 2 * margin)
    if count == 1: return [margin + span / 2]
    return [margin + span * index / (count - 1) for index in range(count)]


def _deadline(started: float, seconds: int) -> None:
    if time.monotonic() - started > seconds:
        raise TimeoutError("Whole-job timeout exceeded")


def _env_int(name: str, default: int) -> int:
    try: value = int(os.environ.get(name, str(default)))
    except ValueError as exc: raise ValueError(f"{name} must be an integer") from exc
    if value <= 0: raise ValueError(f"{name} must be positive")
    return value


def _required_config(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ValueError(f"missing required configuration: {name}")
    return value


def _safe_detail(exc: Exception) -> str:
    text = " ".join(str(exc).replace("\r", " ").replace("\n", " ").split())
    for name in ("SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_URL", "GOOGLE_DRIVE_SERVICE_ACCOUNT_CREDENTIALS_PATH"):
        secret = os.environ.get(name, "")
        if secret: text = text.replace(secret, "[REDACTED]")
    return text[:300] or type(exc).__name__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--once", action="store_true", help="Claim at most one eligible job and exit")
    mode.add_argument("--poll", action="store_true", help="Continuously poll, one job at a time")
    mode.add_argument("--preflight", action="store_true", help="Check dedicated-machine deployment readiness; process no media")
    parser.add_argument("--benchmark-manifest", type=Path, help="Explicit approved local-AI allowlist")
    parser.add_argument("--staging-only", action="store_true", help="Write review JSONL; do not import semantic results")
    parser.add_argument("--confirm-clinical-local-processing", action="store_true",
                        help="Required when an approved manifest is clinical-tier")
    parser.add_argument("--concurrency", type=int, default=1)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.concurrency != 1:
        raise SystemExit("Initial dedicated-worker concurrency must be exactly 1")
    if not args.benchmark_manifest and os.environ.get("KDI_LOCAL_AI_QUEUE_ENABLED", "").casefold() != "true":
        raise SystemExit("Unrestricted queue processing is disabled; provide --benchmark-manifest")
    from dotenv import load_dotenv
    from supabase import create_client
    from kdi_media.google_drive import create_service_account_readonly_drive_service
    from kdi_media.providers.base import get_description_provider, get_embedding_provider
    from kdi_media.semantic_indexing import SupabaseSemanticIndexRepository
    from kdi_media.semantic_pilot import LocalPilotManifest
    from kdi_media.video_frames import resolve_ffmpeg_paths
    load_dotenv()
    config = WorkerConfig.from_environment()
    if args.preflight:
        manifest_path = args.benchmark_manifest or Path("data/semantic_local_automatic_pilot_20.json")
        result = deployment_readiness(config, manifest_path=manifest_path.resolve())
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result["status"] == "READY" else 2
    manifest = LocalPilotManifest.load(args.benchmark_manifest) if args.benchmark_manifest else None
    if manifest and manifest.tier == "clinical" and not args.confirm_clinical_local_processing:
        raise SystemExit("Clinical manifest requires --confirm-clinical-local-processing")
    allowlist = manifest.selected_ids() if manifest else None
    workspaces = WorkspaceManager(config.temp_root)
    reconciliation = workspaces.initialize()
    if workspaces.blocked:
        print(json.dumps({"status": "ORPHAN_RECONCILIATION_BLOCKED", "results": reconciliation}))
        return 2
    ffmpeg, ffprobe = resolve_ffmpeg_paths()
    report = startup_preflight(config, ffmpeg=ffmpeg, ffprobe=ffprobe)
    print(json.dumps({"event": "startup_preflight", **report}, sort_keys=True))
    if not report["ok"]: return 2
    description, embedding = get_description_provider(), get_embedding_provider()
    try:
        validate_model_identity(description, embedding)
    except ProviderPermanentError as exc:
        raise SystemExit(str(exc)) from exc
    client = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])
    repository = SupabaseSemanticIndexRepository(client)
    repository.require_schema()
    repository.configure_index_identity(description, embedding)
    drive_service = create_service_account_readonly_drive_service()
    if allowlist:
        repository.seed_pending(repository.prepare_explicit_assets(allowlist))
    worker = DedicatedSemanticWorker(repository, DriveStreamTransport(drive_service),
        description, embedding, workspaces,
        FileMediaPreparer(ffmpeg=ffmpeg, ffprobe=ffprobe, probe_timeout=config.ffprobe_timeout_seconds,
                          frame_timeout=config.ffmpeg_timeout_seconds), config,
        staging_only=args.staging_only, staging_writer=JsonlStagingWriter(config.staging_path))
    signal.signal(signal.SIGINT, worker.request_shutdown)
    if hasattr(signal, "SIGTERM"): signal.signal(signal.SIGTERM, worker.request_shutdown)
    if args.once:
        metrics = worker.run_once(allowlist=allowlist)
        if metrics: print(json.dumps({"event": "job_complete", **asdict(metrics)}, sort_keys=True))
    else:
        remaining_allowlist = list(allowlist) if allowlist is not None else None
        while not worker.stop_event.is_set() and not worker.workspaces.blocked:
            metrics = worker.run_once(allowlist=remaining_allowlist)
            if metrics:
                print(json.dumps({"event": "job_complete", **asdict(metrics)}, sort_keys=True))
                if remaining_allowlist is not None and metrics.result_state in {
                    "STAGED", IndexingStatus.INDEXED.value, IndexingStatus.FAILED_PERMANENT.value
                }:
                    remaining_allowlist = [value for value in remaining_allowlist if value != metrics.asset_id]
                    if not remaining_allowlist:
                        break
            else:
                if remaining_allowlist is not None:
                    break
                worker.stop_event.wait(config.poll_seconds)
    return 2 if worker.workspaces.blocked else 0


if __name__ == "__main__":
    raise SystemExit(main())
