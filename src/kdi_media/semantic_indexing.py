"""Semantic-indexing worker: AI metadata + embeddings for natural-language search.

Reads existing canonical assets from the `assets` table instead of creating a
parallel inventory. All writes are confined to `asset_semantic_index` and
`asset_embeddings`; original media is only ever read (never modified).
Mirrors the claim-lease worker shape used by Step 9 hashing
(`step9_hashing.py`) and Step 10 upload (`step10_upload.py`): a
Protocol-typed repository, injected dependencies, and a retry/backoff loop
around a single external call.

Videos never leave this process as a complete file: for a video asset, the
worker downloads the source bytes (read-only, from Drive) purely to extract
a small number of representative frames locally (see kdi_media.video_frames)
before calling the description provider with only those frames plus an
optional, length-limited transcript excerpt.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import hashlib
import random
import time
from typing import Any, Callable, Mapping, Protocol, Sequence

from kdi_media.providers.base import (
    DescriptionProvider,
    DescriptionValidationError,
    EmbeddingProvider,
    ProviderPermanentError,
    ProviderRetryableError,
    StructuredMetadata,
)
from kdi_media.image_input import (
    ImagePreparationError,
    ImagePreprocessor,
    PillowImagePreprocessor,
)
from kdi_media.rules import FORMAT_POLICY, normalize_extension
from kdi_media.step9_hashing import iter_drive_content
from kdi_media.supabase_store import utc_now
from kdi_media.video_frames import (
    DEFAULT_MAX_FRAMES,
    FfmpegFrameExtractor,
    FrameExtractionError,
    VideoFrameExtractor,
    limit_transcript,
)

DEFAULT_RETRY_DELAYS = (1.0, 2.0, 4.0, 8.0, 16.0)
SEARCHABLE_TEXT_MAX_LEN = 4000
TRANSCRIPT_MAX_CHARS = 2000

AI_ANALYSIS_EXTENSIONS = frozenset(
    extension
    for extension, policy in FORMAT_POLICY.items()
    if policy.accepted_for_ai_analysis
)
VIDEO_EXTENSIONS = frozenset(
    extension
    for extension, policy in FORMAT_POLICY.items()
    if policy.accepted_for_ai_analysis and policy.media_category == "video"
)


class IndexingStatus(StrEnum):
    PENDING = "PENDING"
    QUEUED = "QUEUED"
    PROCESSING = "PROCESSING"
    INDEXED = "INDEXED"
    FAILED_RETRYABLE = "FAILED_RETRYABLE"
    FAILED_PERMANENT = "FAILED_PERMANENT"
    SKIPPED_INELIGIBLE = "SKIPPED_INELIGIBLE"


class SemanticIndexingError(RuntimeError):
    code = "SEMANTIC_INDEXING_ERROR"
    retryable = False


class RetryableIndexingError(SemanticIndexingError):
    code = "RETRYABLE"
    retryable = True


class PermanentIndexingError(SemanticIndexingError):
    code = "PERMANENT"
    retryable = False


@dataclass(frozen=True)
class FailureInfo:
    status: IndexingStatus
    code: str
    reason: str
    retryable: bool


@dataclass(frozen=True)
class AssetCandidate:
    asset_id: str
    file_name: str
    mime_type: str | None
    file_extension: str | None
    content_hash: str | None
    updated_at: str | None
    size_bytes: int | None
    google_file_id: str
    media_category: str  # "image" | "video"
    # Optional, already-available transcript text (e.g. from
    # assets.metadata->>'transcript' once a future step populates it). No
    # new schema/column is introduced for this - only the existing jsonb
    # metadata column is read, and only when present. limit_transcript()
    # bounds it before it is ever sent to a description provider.
    transcript: str | None = None


@dataclass(frozen=True)
class IndexResult:
    metadata: StructuredMetadata
    embedding: Sequence[float]
    embedding_provider: str
    embedding_model: str
    embedding_dimensions: int
    embedding_version: str
    description_provider: str
    description_model: str
    description_version: str
    searchable_text: str
    searchable_text_hash: str
    fingerprint: str
    cost_usd: float | None


def normalized_extension_category(file_extension: str | None) -> str | None:
    """Return "image"/"video" for AI-analysis-eligible extensions, else None."""
    extension = normalize_extension(file_extension or "")
    policy = FORMAT_POLICY.get(extension)
    if policy is None or not policy.accepted_for_ai_analysis:
        return None
    return policy.media_category


def compute_fingerprint(
    candidate: AssetCandidate,
    *,
    description_provider: str = "",
    description_model: str = "",
    description_version: str = "",
    embedding_provider: str = "",
    embedding_model: str = "",
    embedding_version: str = "",
) -> str:
    """Deterministic fingerprint used to skip re-indexing unchanged assets."""
    basis = "|".join(
        [
            candidate.content_hash or "",
            # Canonical content identity, not mutable discovery metadata, is
            # the re-indexing boundary. Renames/moves must not invoke AI.
            # updated_at is retained only as a legacy fallback for rows that
            # predate SHA-256 canonicalization.
            "" if candidate.content_hash else (candidate.updated_at or ""),
            description_provider,
            description_model,
            description_version,
            embedding_provider,
            embedding_model,
            embedding_version,
        ]
    )
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()


def build_searchable_text(*, metadata: StructuredMetadata, file_name: str | None = None) -> str:
    """Deterministic concatenation of approved fields only, whitespace-normalized
    and capped to satisfy asset_semantic_index_searchable_text_len_check.
    Never includes transcript text - only the approved metadata contract."""
    del file_name  # compatibility only; filenames deliberately remain a separate rank signal
    parts = [
        metadata.content_type,
        metadata.treatment or "",
        metadata.subject or "",
        metadata.doctor_name or "",
        metadata.ai_description or "",
    ]
    text = " ".join(" ".join(parts).split())
    return text[:SEARCHABLE_TEXT_MAX_LEN]


def compute_searchable_text_hash(searchable_text: str) -> str:
    """Fingerprint of the exact text that was embedded, stored alongside the
    vector so a future rebuild can detect whether re-embedding is actually
    necessary without recomputing AI metadata."""
    return hashlib.sha256(searchable_text.encode("utf-8")).hexdigest()


def requires_pilot_confirmation(*, asset_ids: Sequence[str] | None, confirmed: bool) -> bool:
    """True if an explicit non-clinical eligibility confirmation is still
    needed before any external AI call may be made.

    No automated clinical/patient-identifiable classification exists in the
    current schema, so nothing is eligible for the pilot by default: file
    ownership/presence in the library is never treated as consent or
    external-AI approval. Callers (the CLI) must pass an explicit,
    manually-reviewed asset_id allowlist plus confirmed=True before any
    description/embedding provider is invoked.
    """
    return not (asset_ids and confirmed)


class SemanticIndexRepository(Protocol):
    def discover_eligible_asset_ids(self, limit: int) -> tuple[list[str], list[str]]: ...
    def seed_pending(self, asset_ids: Sequence[str]) -> None: ...
    def requeue_changed(self, asset_ids: Sequence[str]) -> None: ...
    def mark_ineligible(self, asset_id: str, reason: str) -> None: ...
    def claim_batch(
        self,
        claim_owner: str,
        limit: int,
        lease_seconds: int,
        asset_ids: Sequence[str] | None = None,
    ) -> list[Mapping[str, Any]]: ...
    def fetch_candidate(self, asset_id: str) -> AssetCandidate | None: ...
    def complete(self, asset_id: str, claim_owner: str, result: IndexResult) -> bool: ...
    def fail(self, asset_id: str, claim_owner: str, failure: FailureInfo) -> bool: ...


class ContentFetcher(Protocol):
    def fetch(self, candidate: AssetCandidate) -> bytes: ...


class DriveContentFetcher:
    """Reads original bytes from Google Drive. Read-only; never writes back.

    For video assets this is only ever used locally to extract representative
    frames (see SemanticIndexingWorker._attempt) - the full bytes fetched
    here are never themselves sent to a description provider.
    """

    def __init__(self, service: Any) -> None:
        self.service = service

    def fetch(self, candidate: AssetCandidate) -> bytes:
        chunks = list(iter_drive_content(self.service, candidate.google_file_id))
        return b"".join(chunks)


class SemanticIndexingWorker:
    def __init__(
        self,
        repository: SemanticIndexRepository,
        content_fetcher: ContentFetcher,
        description_provider: DescriptionProvider,
        embedding_provider: EmbeddingProvider,
        *,
        frame_extractor: VideoFrameExtractor | None = None,
        image_preprocessor: ImagePreprocessor | None = None,
        max_video_frames: int = DEFAULT_MAX_FRAMES,
        retry_delays: tuple[float, ...] = DEFAULT_RETRY_DELAYS,
        jitter: Callable[[], float] = random.random,
        sleeper: Callable[[float], None] = time.sleep,
        max_cost_usd: float | None = None,
        event_observer: Callable[[str, Mapping[str, Any]], None] | None = None,
    ) -> None:
        self.repository = repository
        self.content_fetcher = content_fetcher
        self.description_provider = description_provider
        self.embedding_provider = embedding_provider
        self.frame_extractor = frame_extractor or FfmpegFrameExtractor()
        self.image_preprocessor = image_preprocessor or PillowImagePreprocessor()
        self.max_video_frames = max_video_frames
        self.retry_delays = retry_delays
        self.jitter = jitter
        self.sleeper = sleeper
        self.max_cost_usd = max_cost_usd
        self.event_observer = event_observer or (lambda _event, _details: None)
        self.total_cost_usd = 0.0

    def process_one(self, asset_id: str, claim_owner: str) -> IndexResult | None:
        candidate = self.repository.fetch_candidate(asset_id)
        if candidate is None:
            self.repository.fail(
                asset_id,
                claim_owner,
                FailureInfo(
                    IndexingStatus.FAILED_PERMANENT,
                    "CANDIDATE_NOT_FOUND",
                    "Asset no longer eligible for semantic indexing",
                    False,
                ),
            )
            return None

        for attempt in range(len(self.retry_delays) + 1):
            try:
                return self._attempt(candidate, claim_owner)
            except SemanticIndexingError as exc:
                if exc.retryable and attempt < len(self.retry_delays):
                    self.event_observer(
                        "retry",
                        {"attempt": attempt + 1, "asset_id": asset_id, "code": exc.code},
                    )
                    self.sleeper(self.retry_delays[attempt] * (1 + self.jitter()))
                    continue
                status = (
                    IndexingStatus.FAILED_RETRYABLE
                    if exc.retryable
                    else IndexingStatus.FAILED_PERMANENT
                )
                self.repository.fail(
                    asset_id,
                    claim_owner,
                    FailureInfo(status, exc.code, _sanitize_reason(str(exc)), exc.retryable),
                )
                return None
        raise AssertionError("unreachable")

    def _attempt(self, candidate: AssetCandidate, claim_owner: str) -> IndexResult:
        if self.max_cost_usd is not None and self.total_cost_usd >= self.max_cost_usd:
            raise PermanentIndexingError("Cost cap reached for this run")

        images, transcript = self.prepare_description_input(candidate)

        try:
            metadata, description_cost = self.description_provider.describe_media(
                file_name=candidate.file_name,
                mime_type=candidate.mime_type or "application/octet-stream",
                media_category=candidate.media_category,
                images=images,
                transcript=transcript,
            )
        except DescriptionValidationError as exc:
            # Malformed/invalid model responses are recorded as retryable
            # failures, never saved.
            raise RetryableIndexingError(f"Invalid model response: {exc}") from exc
        except ProviderPermanentError as exc:
            raise PermanentIndexingError(str(exc)) from exc
        except ProviderRetryableError as exc:
            raise RetryableIndexingError(str(exc)) from exc
        except SemanticIndexingError:
            raise
        except Exception as exc:
            raise RetryableIndexingError(f"Description generation failed: {exc}") from exc

        searchable_text = build_searchable_text(metadata=metadata)
        try:
            embedding, embedding_cost = self.embedding_provider.embed_text(searchable_text)
        except ProviderPermanentError as exc:
            raise PermanentIndexingError(str(exc)) from exc
        except ProviderRetryableError as exc:
            raise RetryableIndexingError(str(exc)) from exc
        except SemanticIndexingError:
            raise
        except Exception as exc:
            raise RetryableIndexingError(f"Embedding generation failed: {exc}") from exc

        cost = (description_cost or 0.0) + (embedding_cost or 0.0)
        self.total_cost_usd += cost

        result = IndexResult(
            metadata=metadata,
            embedding=embedding,
            embedding_provider=self.embedding_provider.provider_name,
            embedding_model=self.embedding_provider.model_name,
            embedding_dimensions=self.embedding_provider.embedding_dimensions,
            embedding_version=self.embedding_provider.version,
            description_provider=self.description_provider.provider_name,
            description_model=self.description_provider.model_name,
            description_version=self.description_provider.schema_version,
            searchable_text=searchable_text,
            searchable_text_hash=compute_searchable_text_hash(searchable_text),
            fingerprint=compute_fingerprint(
                candidate,
                description_provider=self.description_provider.provider_name,
                description_model=self.description_provider.model_name,
                description_version=self.description_provider.schema_version,
                embedding_provider=self.embedding_provider.provider_name,
                embedding_model=self.embedding_provider.model_name,
                embedding_version=self.embedding_provider.version,
            ),
            cost_usd=cost or None,
        )
        if not self.repository.complete(candidate.asset_id, claim_owner, result):
            raise PermanentIndexingError("Semantic index claim was lost before completion")
        return result

    def prepare_description_input(
        self, candidate: AssetCandidate
    ) -> tuple[list[bytes], str | None]:
        """Builds the (images, transcript) pair ever sent to the description
        provider. Images downloaded from Drive are used only to extract
        local frames for video assets - the full video bytes are discarded
        after extraction and never passed to describe_media()."""
        try:
            content = self.content_fetcher.fetch(candidate)
        except Exception as exc:
            raise RetryableIndexingError(f"Content fetch failed: {exc}") from exc

        if candidate.media_category != "video":
            try:
                return [self.image_preprocessor.prepare(content)], None
            except ImagePreparationError as exc:
                raise PermanentIndexingError(f"Image preparation failed: {exc}") from exc

        try:
            frames = self.frame_extractor.extract_frames(content, max_frames=self.max_video_frames)
        except FrameExtractionError as exc:
            raise RetryableIndexingError(f"Frame extraction failed: {exc}") from exc
        transcript = limit_transcript(candidate.transcript, max_chars=TRANSCRIPT_MAX_CHARS)
        return frames, transcript


class SupabaseSemanticIndexRepository:
    """Supabase REST/RPC adapter; writes are confined to asset_semantic_index
    and asset_embeddings."""

    def __init__(self, client: Any) -> None:
        self.client = client
        self.index_identity: dict[str, str] = {}

    def configure_index_identity(
        self, description_provider: DescriptionProvider, embedding_provider: EmbeddingProvider
    ) -> None:
        self.index_identity = {
            "description_provider": description_provider.provider_name,
            "description_model": description_provider.model_name,
            "description_version": description_provider.schema_version,
            "embedding_provider": embedding_provider.provider_name,
            "embedding_model": embedding_provider.model_name,
            "embedding_version": embedding_provider.version,
        }

    def current_fingerprint(self, candidate: AssetCandidate) -> str:
        return compute_fingerprint(candidate, **self.index_identity)

    def prepare_explicit_assets(self, asset_ids: Sequence[str]) -> list[str]:
        """Return only new/outdated IDs, requeueing outdated indexed rows.

        This is the paid-call idempotency gate used before claiming an explicit
        pilot allowlist. Current rows are skipped without reading Drive media.
        """
        ready: list[str] = []
        for asset_id in asset_ids:
            candidate = self.fetch_candidate(asset_id)
            if candidate is None:
                continue
            response = (
                self.client.table("asset_semantic_index")
                .select("indexing_status,source_fingerprint")
                .eq("asset_id", asset_id)
                .limit(1)
                .execute()
            )
            rows = response.data or []
            if not rows:
                ready.append(asset_id)
                continue
            state = rows[0]
            if (
                state.get("indexing_status") == IndexingStatus.INDEXED.value
                and state.get("source_fingerprint") == self.current_fingerprint(candidate)
            ):
                continue
            if state.get("indexing_status") == IndexingStatus.INDEXED.value:
                self.requeue_changed([asset_id])
            ready.append(asset_id)
        return ready

    def require_schema(self) -> None:
        """Zero-row probe: fail clearly if the migration has not been applied yet."""
        self.client.table("asset_semantic_index").select("asset_id").limit(1).execute()
        self.client.table("asset_embeddings").select("id").limit(1).execute()

    def list_eligible_candidates(
        self, limit: int, *, videos_only: bool = False
    ) -> list[AssetCandidate]:
        """Read-only preview of not-yet-indexed eligible assets. Used by --dry-run;
        never writes (unlike discover_eligible_asset_ids, which seeds/marks rows)."""
        indexed_response = (
            self.client.table("asset_semantic_index").select("asset_id").execute()
        )
        already_indexed = {row["asset_id"] for row in (indexed_response.data or [])}

        assets_response = (
            self.client.table("assets")
            .select("id,file_extension")
            .execute()
        )
        candidates: list[AssetCandidate] = []
        for row in assets_response.data or []:
            asset_id = row["id"]
            if asset_id in already_indexed:
                continue
            category = normalized_extension_category(row.get("file_extension"))
            if category is None:
                continue
            if videos_only and category != "video":
                continue
            candidate = self.fetch_candidate(asset_id)
            if candidate is None:
                continue
            candidates.append(candidate)
            if len(candidates) >= limit:
                break
        return candidates

    def discover_eligible_asset_ids(self, limit: int) -> tuple[list[str], list[str]]:
        """Returns (new_asset_ids, changed_asset_ids), combined count <= limit.

        Unchanged already-indexed assets (fingerprint match) are skipped
        entirely - no read of their content, no write. Assets whose
        fingerprint no longer matches the stored one are queued for
        re-indexing rather than treated as brand new.
        """
        indexed_response = (
            self.client.table("asset_semantic_index")
            .select("asset_id,indexing_status,source_fingerprint")
            .execute()
        )
        indexed_state = {row["asset_id"]: row for row in (indexed_response.data or [])}

        assets_response = (
            self.client.table("assets")
            .select("id,file_name,file_extension,content_hash,updated_at")
            .execute()
        )
        new_ids: list[str] = []
        changed_ids: list[str] = []
        for row in assets_response.data or []:
            asset_id = row["id"]
            existing = indexed_state.get(asset_id)
            if existing is not None:
                if existing.get("indexing_status") != IndexingStatus.INDEXED.value:
                    # Already PENDING/QUEUED/PROCESSING/FAILED*/SKIPPED_INELIGIBLE:
                    # left for claim_batch (or --retry-failed) to pick up, not reseeded here.
                    continue
                current_fingerprint = self.current_fingerprint(
                    AssetCandidate(
                        asset_id=asset_id,
                        file_name=row.get("file_name") or "",
                        mime_type=None,
                        file_extension=row.get("file_extension"),
                        content_hash=row.get("content_hash"),
                        updated_at=row.get("updated_at"),
                        size_bytes=None,
                        google_file_id="",
                        media_category="",
                    )
                )
                if current_fingerprint == existing.get("source_fingerprint"):
                    continue  # unchanged - skip re-indexing entirely
                if normalized_extension_category(row.get("file_extension")) is None:
                    self.mark_ineligible(asset_id, "UNSUPPORTED_MEDIA_TYPE")
                    continue
                if not self._has_active_source(asset_id):
                    self.mark_ineligible(asset_id, "NO_ACTIVE_SOURCE")
                    continue
                changed_ids.append(asset_id)
            else:
                if normalized_extension_category(row.get("file_extension")) is None:
                    self.mark_ineligible(asset_id, "UNSUPPORTED_MEDIA_TYPE")
                    continue
                if not self._has_active_source(asset_id):
                    self.mark_ineligible(asset_id, "NO_ACTIVE_SOURCE")
                    continue
                new_ids.append(asset_id)
            if len(new_ids) + len(changed_ids) >= limit:
                break
        return new_ids, changed_ids

    def requeue_changed(self, asset_ids: Sequence[str]) -> None:
        """Reset previously-INDEXED rows back to PENDING for re-indexing."""
        for asset_id in asset_ids:
            (
                self.client.table("asset_semantic_index")
                .update({"indexing_status": IndexingStatus.PENDING.value, "attempt_count": 0})
                .eq("asset_id", asset_id)
                .eq("indexing_status", IndexingStatus.INDEXED.value)
                .execute()
            )

    def _has_active_source(self, asset_id: str) -> bool:
        response = (
            self.client.table("asset_sources")
            .select(
                "source_files(is_missing,sync_classification,google_file_id,"
                "source_folders(active))"
            )
            .eq("asset_id", asset_id)
            .execute()
        )
        for row in response.data or []:
            source_file = row.get("source_files") or {}
            folder = source_file.get("source_folders") or {}
            if (
                source_file.get("is_missing") is not True
                and source_file.get("sync_classification") != "REMOVED_FROM_SOURCE"
                and folder.get("active") is True
                and source_file.get("google_file_id")
            ):
                return True
        return False

    def seed_pending(self, asset_ids: Sequence[str]) -> None:
        if not asset_ids:
            return
        rows = [
            {"asset_id": asset_id, "indexing_status": IndexingStatus.PENDING.value}
            for asset_id in asset_ids
        ]
        (
            self.client.table("asset_semantic_index")
            .upsert(rows, on_conflict="asset_id", ignore_duplicates=True)
            .execute()
        )

    def mark_ineligible(self, asset_id: str, reason: str) -> None:
        (
            self.client.table("asset_semantic_index")
            .upsert(
                {
                    "asset_id": asset_id,
                    "indexing_status": IndexingStatus.SKIPPED_INELIGIBLE.value,
                    "last_error": reason,
                },
                on_conflict="asset_id",
            )
            .execute()
        )

    def claim_batch(
        self,
        claim_owner: str,
        limit: int,
        lease_seconds: int,
        asset_ids: Sequence[str] | None = None,
    ) -> list[Mapping[str, Any]]:
        response = self.client.rpc(
            "claim_semantic_index_batch",
            {
                "requested_claim_owner": claim_owner,
                "requested_limit": limit,
                "requested_lease_seconds": lease_seconds,
                "requested_asset_ids": list(asset_ids) if asset_ids else None,
            },
        ).execute()
        return response.data or []

    def fetch_candidate(self, asset_id: str) -> AssetCandidate | None:
        asset_response = (
            self.client.table("assets")
            .select(
                "id,file_name,mime_type,file_extension,content_hash,updated_at,"
                "size_bytes,metadata"
            )
            .eq("id", asset_id)
            .limit(1)
            .execute()
        )
        asset_rows = asset_response.data or []
        if not asset_rows:
            return None
        asset = asset_rows[0]
        category = normalized_extension_category(asset.get("file_extension"))
        if category is None:
            return None

        destination_response = (
            self.client.table("asset_destinations")
            .select("destination_google_file_id,upload_status,verified_at")
            .eq("asset_id", asset_id)
            .eq("upload_status", "VERIFIED")
            .order("verified_at", desc=True)
            .execute()
        )
        google_file_id = next(
            (
                row.get("destination_google_file_id")
                for row in destination_response.data or []
                if row.get("destination_google_file_id")
            ),
            None,
        )
        if google_file_id is None:
            return None

        raw_metadata = asset.get("metadata") or {}
        transcript = raw_metadata.get("transcript") if isinstance(raw_metadata, dict) else None

        return AssetCandidate(
            asset_id=asset["id"],
            file_name=asset["file_name"],
            mime_type=asset.get("mime_type"),
            file_extension=asset.get("file_extension"),
            content_hash=asset.get("content_hash"),
            updated_at=asset.get("updated_at"),
            size_bytes=asset.get("size_bytes"),
            google_file_id=google_file_id,
            media_category=category,
            transcript=transcript if isinstance(transcript, str) else None,
        )

    def complete(self, asset_id: str, claim_owner: str, result: IndexResult) -> bool:
        payload = {
            "requested_asset_id": asset_id,
            "requested_claim_owner": claim_owner,
            "requested_metadata": {
            "content_type": result.metadata.content_type,
            "treatment": result.metadata.treatment,
            "subject": result.metadata.subject,
            "doctor_name": result.metadata.doctor_name,
            "short_caption": result.metadata.short_caption,
            "ai_description": result.metadata.ai_description,
            "searchable_text": result.searchable_text,
            "description_provider": result.description_provider,
            "description_model": result.description_model,
            "description_version": result.description_version,
            "source_fingerprint": result.fingerprint,
            "indexing_status": IndexingStatus.INDEXED.value,
            "indexed_at": utc_now(),
            "last_error": None,
            "last_cost_usd": result.cost_usd,
            "claim_owner": None,
            "claimed_at": None,
            },
            "requested_embedding": {
                    "asset_id": asset_id,
                    "embedding_provider": result.embedding_provider,
                    "embedding_model": result.embedding_model,
                    "embedding_dimensions": result.embedding_dimensions,
                    "embedding_version": result.embedding_version,
                    "embedding": list(result.embedding),
                    "searchable_text_hash": result.searchable_text_hash,
                    "embedded_at": utc_now(),
            },
        }
        response = self.client.rpc("complete_semantic_index_atomically", payload).execute()
        data = response.data
        return data is True or data == [True] or data == [{"complete_semantic_index_atomically": True}]

    def fail(self, asset_id: str, claim_owner: str, failure: FailureInfo) -> bool:
        response = (
            self.client.table("asset_semantic_index")
            .update(
                {
                    "indexing_status": failure.status.value,
                    "last_error": f"{failure.code}: {failure.reason}",
                    "claim_owner": None,
                    "claimed_at": None,
                    "claim_expires_at": None,
                }
            )
            .eq("asset_id", asset_id)
            .eq("indexing_status", IndexingStatus.PROCESSING.value)
            .eq("claim_owner", claim_owner)
            .execute()
        )
        return len(response.data or []) == 1

    def release_staging(self, asset_id: str, claim_owner: str) -> bool:
        """Release a staging-only claim without importing generated output."""
        response = (
            self.client.table("asset_semantic_index")
            .update({
                "indexing_status": IndexingStatus.PENDING.value,
                "claim_owner": None, "claimed_at": None, "claim_expires_at": None,
                "last_error": None,
            })
            .eq("asset_id", asset_id)
            .eq("indexing_status", IndexingStatus.PROCESSING.value)
            .eq("claim_owner", claim_owner)
            .execute()
        )
        return len(response.data or []) == 1


def _sanitize_reason(value: str) -> str:
    clean = " ".join(value.replace("\r", " ").replace("\n", " ").split())
    return clean[:500]
