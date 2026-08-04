"""Conflict-safe Step 9 canonicalization without Drive or hashing operations."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Callable, Iterable, Mapping, Protocol

from postgrest.exceptions import APIError


SHA256 = re.compile(r"^[0-9a-f]{64}$")


class CanonicalizationError(RuntimeError):
    pass


@dataclass(frozen=True)
class CanonicalSource:
    source_file_id: str
    source_folder_id: str
    google_file_id: str
    file_name: str
    mime_type: str
    file_extension: str
    size_bytes: int
    hash_algorithm: str
    content_hash: str
    hash_status: str
    decision: str
    processing_status: str
    relative_path: str | None = None

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> "CanonicalSource":
        value = cls(
            source_file_id=str(row.get("id") or ""),
            source_folder_id=str(row.get("source_folder_id") or ""),
            google_file_id=str(row.get("google_file_id") or ""),
            file_name=str(row.get("file_name") or ""),
            mime_type=str(row.get("mime_type") or "").lower(),
            file_extension=str(row.get("file_extension") or "").lower(),
            size_bytes=row.get("size_bytes"),
            hash_algorithm=str(row.get("hash_algorithm") or ""),
            content_hash=str(row.get("content_sha256") or "").lower(),
            hash_status=str(row.get("hash_status") or ""),
            decision=str(row.get("decision") or ""),
            processing_status=str(row.get("processing_status") or ""),
            relative_path=(
                str(row["relative_path"])
                if row.get("relative_path") is not None
                else None
            ),
        )
        value.validate()
        return value

    def validate(self) -> None:
        if not all(
            (
                self.source_file_id,
                self.source_folder_id,
                self.google_file_id,
                self.file_name,
            )
        ):
            raise CanonicalizationError("Source identity is incomplete")
        if (
            self.hash_status != "HASHED"
            or self.hash_algorithm != "SHA-256"
            or not SHA256.fullmatch(self.content_hash)
            or self.decision != "TAKE"
            or self.processing_status != "READY"
        ):
            raise CanonicalizationError(
                "Source is not a successfully hashed canonicalization input"
            )
        if not isinstance(self.size_bytes, int) or self.size_bytes < 0:
            raise CanonicalizationError("Source size is invalid")


@dataclass(frozen=True)
class CanonicalGroup:
    hash_algorithm: str
    content_hash: str
    sources: tuple[CanonicalSource, ...]
    representative: CanonicalSource

    @property
    def identity(self) -> tuple[str, str]:
        return self.hash_algorithm, self.content_hash

    def asset_values(self) -> dict[str, Any]:
        return {
            "content_hash": self.content_hash,
            # The deployed schema retains these legacy canonical fields.
            # Populate both names from the same complete SHA-256/metadata
            # source so either approved consumer observes identical values.
            "checksum_sha256": self.content_hash,
            "file_name": self.representative.file_name,
            "original_file_name": self.representative.file_name,
            "mime_type": self.representative.mime_type,
            "file_extension": self.representative.file_extension,
            "size_bytes": self.representative.size_bytes,
            "file_size_bytes": self.representative.size_bytes,
            "upload_status": "PENDING",
            "migration_status": "PENDING",
            "upload_attempts": 0,
            "metadata": {
                "hash_algorithm": self.hash_algorithm,
                "canonical_source_file_id": (
                    self.representative.source_file_id
                ),
                "media_category": _media_category(
                    self.representative.mime_type
                ),
                "canonicalization_rule": (
                    "min(source_folder_id,google_file_id,source_file_id)"
                ),
            },
        }


@dataclass(frozen=True)
class GroupResult:
    identity_prefix: str
    asset_id: str | None
    links_created_or_reused: int
    error: str | None


class CanonicalRepository(Protocol):
    def create_or_reuse_asset(
        self, values: Mapping[str, Any]
    ) -> Mapping[str, Any]: ...

    def create_or_reuse_link(
        self, *, asset_id: str, source_file_id: str, relationship_type: str
    ) -> Mapping[str, Any]: ...


def build_canonical_groups(
    rows: Iterable[Mapping[str, Any]],
) -> tuple[CanonicalGroup, ...]:
    grouped: dict[tuple[str, str], list[CanonicalSource]] = {}
    for row in rows:
        source = CanonicalSource.from_row(row)
        grouped.setdefault(
            (source.hash_algorithm, source.content_hash), []
        ).append(source)
    results = []
    for identity, sources in grouped.items():
        ordered = tuple(
            sorted(
                sources,
                key=lambda source: (
                    source.source_folder_id,
                    source.google_file_id,
                    source.source_file_id,
                ),
            )
        )
        sizes = {source.size_bytes for source in ordered}
        if len(sizes) != 1:
            raise CanonicalizationError(
                "Matching complete hashes have inconsistent sizes"
            )
        results.append(
            CanonicalGroup(identity[0], identity[1], ordered, ordered[0])
        )
    return tuple(sorted(results, key=lambda group: group.identity))


def canonicalize_groups(
    groups: Iterable[CanonicalGroup],
    repository: CanonicalRepository,
    *,
    checkpoint: Callable[[GroupResult], None] | None = None,
    continue_on_error: bool = True,
) -> tuple[GroupResult, ...]:
    """Create/reuse one asset and all links, independently per hash group."""
    save_checkpoint = checkpoint or (lambda _result: None)
    results = []
    for group in groups:
        try:
            asset = repository.create_or_reuse_asset(group.asset_values())
            asset_id = str(asset.get("id") or "")
            if not asset_id:
                raise CanonicalizationError("Canonical asset has no ID")
            linked = 0
            for source in group.sources:
                repository.create_or_reuse_link(
                    asset_id=asset_id,
                    source_file_id=source.source_file_id,
                    relationship_type=(
                        "ORIGINAL"
                        if source.source_file_id
                        == group.representative.source_file_id
                        else "DUPLICATE"
                    ),
                )
                linked += 1
            result = GroupResult(group.content_hash[:12], asset_id, linked, None)
        except Exception as exc:
            result = GroupResult(
                group.content_hash[:12],
                None,
                0,
                _sanitize_error(exc),
            )
            results.append(result)
            save_checkpoint(result)
            if not continue_on_error:
                raise
            continue
        results.append(result)
        save_checkpoint(result)
    return tuple(results)


class SupabaseCanonicalRepository:
    """Database-unique insert/reuse adapter; never touches source_files."""

    def __init__(self, client: Any) -> None:
        self.client = client

    def create_or_reuse_asset(
        self, values: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        try:
            response = (
                self.client.table("assets").insert(dict(values)).execute()
            )
            rows = response.data or []
            if len(rows) != 1:
                raise CanonicalizationError("Asset insert returned no row")
            return rows[0]
        except APIError as exc:
            if _api_code(exc) != "23505":
                raise
        rows = (
            self.client.table("assets")
            .select("*")
            .eq("content_hash", values["content_hash"])
            .limit(1)
            .execute()
            .data
            or []
        )
        if len(rows) != 1:
            raise CanonicalizationError(
                "Unique asset conflict could not be reconciled"
            )
        existing = rows[0]
        metadata = existing.get("metadata") or {}
        if metadata.get("hash_algorithm", "SHA-256") != "SHA-256":
            raise CanonicalizationError("Existing asset algorithm conflicts")
        return existing

    def create_or_reuse_link(
        self, *, asset_id: str, source_file_id: str, relationship_type: str
    ) -> Mapping[str, Any]:
        values = {
            "asset_id": asset_id,
            "source_file_id": source_file_id,
            "relationship_type": relationship_type,
            "is_first_discovered_source": relationship_type == "ORIGINAL",
        }
        try:
            response = (
                self.client.table("asset_sources").insert(values).execute()
            )
            rows = response.data or []
            if len(rows) != 1:
                raise CanonicalizationError("Asset-source insert returned no row")
            return rows[0]
        except APIError as exc:
            if _api_code(exc) != "23505":
                raise
        rows = (
            self.client.table("asset_sources")
            .select("*")
            .eq("source_file_id", source_file_id)
            .limit(1)
            .execute()
            .data
            or []
        )
        if len(rows) != 1 or rows[0].get("asset_id") != asset_id:
            raise CanonicalizationError(
                "Source file is linked to a different canonical asset"
            )
        return rows[0]


def _media_category(mime_type: str) -> str:
    if mime_type.startswith("image/"):
        return "image"
    if mime_type.startswith("video/"):
        return "video"
    return "document"


def _api_code(exc: APIError) -> str | None:
    value = getattr(exc, "code", None)
    if value:
        return str(value)
    details = exc.args[0] if exc.args else None
    return str(details.get("code")) if isinstance(details, dict) else None


def _sanitize_error(exc: Exception) -> str:
    return " ".join(str(exc).replace("\r", " ").replace("\n", " ").split())[
        :500
    ]
