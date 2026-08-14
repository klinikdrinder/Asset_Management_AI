"""Fail-closed human-curated semantic metadata import helpers.

This path never reads media and never constructs a description provider. It
validates reviewed metadata, embeds only the approved five-field contract, and
uses explicit manual provenance for the existing semantic tables.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence
from uuid import UUID

from kdi_media.providers.base import (
    CONTROLLED_CONTENT_TYPES,
    EmbeddingProvider,
    StructuredMetadata,
)
from kdi_media.semantic_indexing import (
    AssetCandidate,
    IndexResult,
    build_searchable_text,
    compute_fingerprint,
    compute_searchable_text_hash,
)


MANUAL_DESCRIPTION_PROVIDER = "manual"
MANUAL_DESCRIPTION_MODEL = "human-reviewed"
MANUAL_DESCRIPTION_VERSION = "manual-v1"
REQUIRED_MANIFEST_FIELDS = frozenset({
    "asset_id", "content_type", "treatment", "subject", "doctor_name",
    "ai_description", "short_caption", "reviewed_by", "reviewed_at",
})
OPTIONAL_OPERATIONAL_FIELDS = frozenset({
    "filename", "media_type", "description_provider", "description_model",
    "description_version", "evidence_reviewed_by", "evidence_reviewed_at",
    "owner_approved_by", "owner_approved_at",
})
MANIFEST_FIELDS = REQUIRED_MANIFEST_FIELDS | OPTIONAL_OPERATIONAL_FIELDS
SEMANTIC_FIELDS = (
    "content_type", "treatment", "subject", "doctor_name", "ai_description"
)


class ManualPilotValidationError(ValueError):
    pass


@dataclass(frozen=True)
class ManualPilotEntry:
    asset_id: str
    metadata: StructuredMetadata
    reviewed_by: str
    reviewed_at: str
    description_provider: str = MANUAL_DESCRIPTION_PROVIDER
    description_model: str = MANUAL_DESCRIPTION_MODEL
    description_version: str = MANUAL_DESCRIPTION_VERSION


@dataclass(frozen=True)
class ManualPilotReview:
    asset_id: str | None
    entry: ManualPilotEntry | None
    errors: tuple[str, ...]


def load_and_review_manifest(path: str | Path) -> list[ManualPilotReview]:
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ManualPilotValidationError("Manual pilot manifest is not valid JSON") from exc
    rows = raw.get("assets") if isinstance(raw, dict) else None
    if not isinstance(rows, list) or not rows:
        raise ManualPilotValidationError("Manual pilot manifest must contain assets")
    seen: set[str] = set()
    reviews: list[ManualPilotReview] = []
    for raw_entry in rows:
        review = review_manifest_entry(raw_entry)
        if review.asset_id and review.asset_id in seen:
            review = ManualPilotReview(
                review.asset_id, None, review.errors + ("duplicate asset_id in manifest",)
            )
        if review.asset_id:
            seen.add(review.asset_id)
        reviews.append(review)
    return reviews


def review_manifest_entry(raw: Any) -> ManualPilotReview:
    if not isinstance(raw, dict):
        return ManualPilotReview(None, None, ("entry must be an object",))
    errors: list[str] = []
    extras = set(raw) - MANIFEST_FIELDS
    missing = REQUIRED_MANIFEST_FIELDS - set(raw)
    if extras:
        errors.append(f"unapproved fields: {sorted(extras)}")
    if missing:
        errors.append(f"missing fields: {sorted(missing)}")
    if "filename" in raw and (
        not isinstance(raw["filename"], str) or not raw["filename"].strip()
    ):
        errors.append("filename must be a non-empty string when present")
    if "media_type" in raw and raw["media_type"] not in {"image", "video"}:
        errors.append("media_type must be image or video when present")
    asset_id: str | None = None
    try:
        asset_id = str(UUID(str(raw.get("asset_id", ""))))
    except ValueError:
        errors.append("asset_id must be a UUID")

    reviewed_by = _required_text(raw.get("reviewed_by"), "reviewed_by", errors)
    reviewed_at = _required_text(raw.get("reviewed_at"), "reviewed_at", errors)
    if reviewed_at:
        try:
            parsed = datetime.fromisoformat(reviewed_at.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                errors.append("reviewed_at must include a timezone")
        except ValueError:
            errors.append("reviewed_at must be ISO-8601")

    content_type = _required_text(raw.get("content_type"), "content_type", errors)
    short_caption = _required_text(raw.get("short_caption"), "short_caption", errors)
    description = _required_text(raw.get("ai_description"), "ai_description", errors)
    if content_type and content_type not in CONTROLLED_CONTENT_TYPES:
        errors.append("content_type is not in the controlled list")
    optional: dict[str, str | None] = {}
    for field in ("treatment", "subject", "doctor_name"):
        value = raw.get(field)
        if value is not None and not isinstance(value, str):
            errors.append(f"{field} must be a string, blank, or null")
            optional[field] = None
        else:
            optional[field] = value.strip() or None if isinstance(value, str) else None
    if errors or not all((asset_id, reviewed_by, reviewed_at, content_type, short_caption, description)):
        return ManualPilotReview(asset_id, None, tuple(errors))
    try:
        metadata = StructuredMetadata(
            content_type=content_type,
            treatment=optional["treatment"],
            subject=optional["subject"],
            doctor_name=optional["doctor_name"],
            short_caption=short_caption,
            ai_description=description,
        )
    except ValueError as exc:
        return ManualPilotReview(asset_id, None, (str(exc),))
    provenance = {}
    for field, default in (
        ("description_provider", MANUAL_DESCRIPTION_PROVIDER),
        ("description_model", MANUAL_DESCRIPTION_MODEL),
        ("description_version", MANUAL_DESCRIPTION_VERSION),
    ):
        value = raw.get(field, default)
        if not isinstance(value, str) or not value.strip():
            return ManualPilotReview(asset_id, None, (f"{field} must be a non-empty string when present",))
        provenance[field] = value.strip()
    return ManualPilotReview(
        asset_id,
        ManualPilotEntry(asset_id, metadata, reviewed_by, reviewed_at, **provenance),
        (),
    )


def build_manual_index_result(
    entry: ManualPilotEntry,
    candidate: AssetCandidate,
    embedding_provider: EmbeddingProvider,
) -> IndexResult:
    if embedding_provider.provider_name != "ollama":
        raise ManualPilotValidationError("Manual pilot embedding provider must be Ollama")
    if embedding_provider.embedding_dimensions != 1024:
        raise ManualPilotValidationError("Manual pilot embeddings must be 1024 dimensions")
    searchable_text = build_searchable_text(metadata=entry.metadata)
    embedding, cost = embedding_provider.embed_text(searchable_text)
    _validate_embedding(embedding, embedding_provider.embedding_dimensions)
    text_hash = compute_searchable_text_hash(searchable_text)
    fingerprint = compute_manual_fingerprint(entry, candidate, embedding_provider)
    return IndexResult(
        metadata=entry.metadata,
        embedding=embedding,
        embedding_provider=embedding_provider.provider_name,
        embedding_model=embedding_provider.model_name,
        embedding_dimensions=embedding_provider.embedding_dimensions,
        embedding_version=embedding_provider.version,
        description_provider=entry.description_provider,
        description_model=entry.description_model,
        description_version=entry.description_version,
        searchable_text=searchable_text,
        searchable_text_hash=text_hash,
        fingerprint=fingerprint,
        cost_usd=cost,
    )


def compute_manual_fingerprint(
    entry: ManualPilotEntry,
    candidate: AssetCandidate,
    embedding_provider: EmbeddingProvider,
) -> str:
    searchable_text = build_searchable_text(metadata=entry.metadata)
    text_hash = compute_searchable_text_hash(searchable_text)
    base_fingerprint = compute_fingerprint(
        candidate,
        description_provider=entry.description_provider,
        description_model=entry.description_model,
        description_version=entry.description_version,
        embedding_provider=embedding_provider.provider_name,
        embedding_model=embedding_provider.model_name,
        embedding_version=embedding_provider.version,
    )
    return hashlib.sha256(
        "|".join((base_fingerprint, text_hash, entry.reviewed_by, entry.reviewed_at))
        .encode("utf-8")
    ).hexdigest()


def dry_run_report(
    reviews: Sequence[ManualPilotReview],
    candidates: Mapping[str, AssetCandidate | None],
    *,
    existing_semantic_ids: set[str] | None = None,
    existing_embedding_ids: set[str] | None = None,
) -> dict[str, Any]:
    valid = [review for review in reviews if review.entry is not None]
    found = [review for review in reviews if review.asset_id and candidates.get(review.asset_id)]
    importable = [
        review for review in valid
        if review.asset_id and candidates.get(review.asset_id) is not None
    ]
    existing_semantic_ids = existing_semantic_ids or set()
    existing_embedding_ids = existing_embedding_ids or set()
    return {
        "mode": "DRY_RUN",
        "database_writes": 0,
        "embedding_calls": 0,
        "vision_calls": 0,
        "entries_valid": len(valid),
        "entries_invalid": len(reviews) - len(valid),
        "assets_found": len(found),
        "assets_missing_or_noncanonical": len(reviews) - len(found),
        "semantic_rows_would_create": sum(
            review.asset_id not in existing_semantic_ids for review in importable
        ),
        "embedding_rows_would_create": sum(
            review.asset_id not in existing_embedding_ids for review in importable
        ),
        "embedding_fields": list(SEMANTIC_FIELDS),
        "entries": [
            {
                "asset_id": review.asset_id,
                "valid": review.entry is not None,
                "asset_found": bool(review.asset_id and candidates.get(review.asset_id)),
                "errors": list(review.errors),
            }
            for review in reviews
        ],
    }


def _required_text(value: Any, field: str, errors: list[str]) -> str | None:
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{field} is required")
        return None
    return value.strip()


def _validate_embedding(values: Sequence[float], dimensions: int) -> None:
    if len(values) != dimensions:
        raise ManualPilotValidationError(
            f"Embedding returned {len(values)} dimensions; expected {dimensions}"
        )
    if any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in values):
        raise ManualPilotValidationError("Embedding contains non-numeric values")
    if any(not math.isfinite(float(value)) for value in values):
        raise ManualPilotValidationError("Embedding contains non-finite values")
