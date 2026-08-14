"""Fail-closed manifest contract for a reviewed semantic-indexing pilot."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
from typing import Any, Iterable
from uuid import UUID


MAX_PILOT_ASSETS = 20
RISK_FLAGS = frozenset(
    {"LOW_RISK_FOR_PILOT", "NEEDS_REVIEW", "DO_NOT_SEND_EXTERNALLY"}
)


class PilotManifestError(ValueError):
    """The pilot manifest is missing, malformed, or not explicitly approved."""


@dataclass(frozen=True)
class LocalPilotAsset:
    """A separate, explicit approval for processing on the controlled KDI host."""

    asset_id: str
    media_type: str
    approved_for_local_ai: bool
    approval_reason: str | None
    approved_by: str | None
    approval_timestamp: str | None


@dataclass(frozen=True)
class LocalPilotManifest:
    """Fail-closed local-only allowlist; it never confers external-AI approval."""

    tier: str
    assets: tuple[LocalPilotAsset, ...]

    @classmethod
    def load(cls, path: str | Path) -> "LocalPilotManifest":
        manifest_path = Path(path)
        if not manifest_path.is_file():
            raise PilotManifestError("Local pilot manifest does not exist")
        try:
            raw = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise PilotManifestError("Local pilot manifest is not valid JSON") from exc
        rows = raw.get("assets") if isinstance(raw, dict) else None
        tier = raw.get("tier") if isinstance(raw, dict) else None
        if tier not in {"low-risk", "clinical"}:
            raise PilotManifestError("Local pilot tier must be low-risk or clinical")
        if not isinstance(rows, list) or not rows:
            raise PilotManifestError("Local pilot manifest must contain assets")
        assets: list[LocalPilotAsset] = []
        seen: set[str] = set()
        for row in rows:
            asset = _parse_local_asset(row)
            if asset.asset_id not in seen:
                seen.add(asset.asset_id)
                assets.append(asset)
        if len(assets) > MAX_PILOT_ASSETS:
            raise PilotManifestError(f"Local pilot manifest exceeds {MAX_PILOT_ASSETS} assets")
        return cls(tier, tuple(assets))

    def selected_ids(self, requested_ids: Iterable[str] | None = None) -> list[str]:
        allowed = {asset.asset_id for asset in self.assets if asset.approved_for_local_ai}
        if requested_ids is None:
            return [asset.asset_id for asset in self.assets if asset.asset_id in allowed]
        selected: list[str] = []
        for value in dict.fromkeys(requested_ids):
            try:
                normalized = str(UUID(value))
            except ValueError as exc:
                raise PilotManifestError("Requested local pilot asset ID is not a UUID") from exc
            if normalized not in allowed:
                raise PilotManifestError(
                    "Requested asset is absent from the local manifest or not locally approved"
                )
            selected.append(normalized)
        return selected


@dataclass(frozen=True)
class PilotAsset:
    asset_id: str
    filename: str
    media_type: str
    extension: str
    size_bytes: int
    duration_ms: int | None
    selection_reason: str
    risk_flag: str
    approved_for_external_ai: bool


@dataclass(frozen=True)
class PilotManifest:
    tier: str
    assets: tuple[PilotAsset, ...]

    @classmethod
    def load(cls, path: str | Path) -> "PilotManifest":
        manifest_path = Path(path)
        if not manifest_path.is_file():
            raise PilotManifestError("Pilot manifest does not exist")
        try:
            raw = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise PilotManifestError("Pilot manifest is not valid JSON") from exc
        rows = raw.get("assets") if isinstance(raw, dict) else None
        tier = raw.get("tier", "clinical") if isinstance(raw, dict) else None
        if tier not in {"low-risk", "clinical"}:
            raise PilotManifestError("Pilot manifest tier must be low-risk or clinical")
        if not isinstance(rows, list) or not rows:
            raise PilotManifestError("Pilot manifest must contain a non-empty assets list")
        # Preserve the first occurrence. A duplicated ID can never expand the
        # paid-call scope or cause the same asset to be processed twice.
        assets: list[PilotAsset] = []
        seen: set[str] = set()
        for row in rows:
            asset = _parse_asset(row)
            if asset.asset_id in seen:
                continue
            seen.add(asset.asset_id)
            assets.append(asset)
        if len(assets) > MAX_PILOT_ASSETS:
            raise PilotManifestError(f"Pilot manifest exceeds {MAX_PILOT_ASSETS} assets")
        if tier == "low-risk" and any(
            asset.risk_flag == "DO_NOT_SEND_EXTERNALLY" for asset in assets
        ):
            raise PilotManifestError("Low-risk manifest cannot contain DO_NOT_SEND_EXTERNALLY assets")
        return cls(tier, tuple(assets))

    def selected_ids(
        self, *, approved_only: bool, requested_ids: Iterable[str] | None = None
    ) -> list[str]:
        allowed = {
            asset.asset_id: asset
            for asset in self.assets
            if not approved_only or asset.approved_for_external_ai
        }
        if requested_ids is None:
            return list(allowed)
        selected: list[str] = []
        for value in dict.fromkeys(requested_ids):
            try:
                normalized = str(UUID(value))
            except ValueError as exc:
                raise PilotManifestError("Requested asset ID is not a UUID") from exc
            if normalized not in allowed:
                raise PilotManifestError(
                    "Requested asset is absent from the manifest or is not approved"
                )
            selected.append(normalized)
        return selected


def _parse_asset(raw: Any) -> PilotAsset:
    if not isinstance(raw, dict):
        raise PilotManifestError("Every manifest asset must be an object")
    try:
        asset_id = str(UUID(str(raw["asset_id"])))
        filename = str(raw["filename"]).strip()
        media_type = str(raw["media_type"]).strip().lower()
        extension = str(raw["extension"]).strip().lower().lstrip(".")
        size_bytes = int(raw["size_bytes"])
        duration_raw = raw.get("duration_ms")
        duration_ms = int(duration_raw) if duration_raw is not None else None
        reason = str(raw["selection_reason"]).strip()
        risk_flag = str(raw["risk_flag"]).strip()
        approved = raw["approved_for_external_ai"]
    except (KeyError, TypeError, ValueError) as exc:
        raise PilotManifestError("Manifest asset has invalid required fields") from exc
    if not filename or not extension or not reason:
        raise PilotManifestError("Manifest text fields must not be empty")
    if media_type not in {"image", "video"}:
        raise PilotManifestError("Pilot assets must be images or videos")
    if size_bytes < 0 or (duration_ms is not None and duration_ms < 0):
        raise PilotManifestError("Manifest sizes and durations must be non-negative")
    if risk_flag not in RISK_FLAGS:
        raise PilotManifestError("Manifest risk_flag is not recognized")
    if not isinstance(approved, bool):
        raise PilotManifestError("approved_for_external_ai must be boolean")
    if approved and risk_flag == "DO_NOT_SEND_EXTERNALLY":
        raise PilotManifestError("DO_NOT_SEND_EXTERNALLY assets cannot be approved")
    return PilotAsset(
        asset_id, filename, media_type, extension, size_bytes, duration_ms,
        reason, risk_flag, approved,
    )


def _parse_local_asset(raw: Any) -> LocalPilotAsset:
    if not isinstance(raw, dict):
        raise PilotManifestError("Every local pilot asset must be an object")
    try:
        asset_id = str(UUID(str(raw["asset_id"])))
        media_type = str(raw["media_type"]).strip().lower()
        approved = raw.get("approved_for_local_ai", False)
    except (KeyError, TypeError, ValueError) as exc:
        raise PilotManifestError("Local pilot asset has invalid required fields") from exc
    if media_type not in {"image", "video"}:
        raise PilotManifestError("Local pilot assets must be images or videos")
    if not isinstance(approved, bool):
        raise PilotManifestError("approved_for_local_ai must be boolean")
    reason = _optional_text(raw.get("approval_reason"))
    reviewer = _optional_text(raw.get("approved_by"))
    timestamp = _optional_text(raw.get("approval_timestamp"))
    if approved:
        if not reason or not reviewer or not timestamp:
            raise PilotManifestError(
                "Local approval requires approval_reason, approved_by, and approval_timestamp"
            )
        try:
            datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        except ValueError as exc:
            raise PilotManifestError("approval_timestamp must be ISO-8601") from exc
    return LocalPilotAsset(
        asset_id, media_type, approved, reason, reviewer, timestamp
    )


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None
