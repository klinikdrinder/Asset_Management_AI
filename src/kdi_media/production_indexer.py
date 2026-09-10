"""Reusable production semantic-indexing orchestration primitives.

The orchestrator is intentionally adapter-based so canonical database writes,
media acquisition, and embedding implementations are injected from the
trusted worker. It enforces privacy eligibility and publication ordering before
any caller can activate SEARCH_READY.

Privacy scope: eligibility gates the *external transmission* only. Local
preprocessing - decode, scene detection, keyframe extraction, audio evaluation,
transcript and OCR - never leaves the machine and always runs, so an asset
awaiting approval still has complete local evidence ready.

Video contract: the encoded video is never transmitted. Each canonical scene is
evaluated from its own representative JPEG keyframes, and the asset-level
package is synthesised from a cross-scene keyframe sample plus the scene
results.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, Sequence

from .claude_code_provider import ClaudeCodeUsageLimitError
from .claude_provider import ClaudeSemanticProvider, ClaudeConfigurationError, LAYER_IDS
from .semantic_provider_factory import build_semantic_provider

# A named procedure must never be inferred from generic equipment or anatomy.
CLINICAL_TERMS = (
    "surgery", "procedure", "treatment", "hair transplant", "fue", "implantation",
    "extraction", "graft harvesting", "graft placement", "prp", "laser treatment", "injection",
)


@dataclass(frozen=True)
class AssetEligibility:
    asset_id: str
    media_type: str
    classification_status: str
    internal_usage_status: str
    external_ai_status: str

    @property
    def may_use_external_ai(self) -> bool:
        return (self.classification_status == "VERIFIED" and
                self.internal_usage_status == "ALLOWED" and
                self.external_ai_status in {"ALLOWED", "APPROVED"})

    @property
    def is_video(self) -> bool:
        return self.media_type.lower().startswith("video")


@dataclass
class SceneEvidence:
    """One canonical scene and the local evidence that grounds it."""
    scene_index: int
    start_seconds: float
    end_seconds: float
    keyframe_paths: list[str] = field(default_factory=list)
    ocr_texts: list[str] = field(default_factory=list)
    transcript_texts: list[str] = field(default_factory=list)

    def frames(self) -> list[bytes]:
        return [Path(p).read_bytes() for p in self.keyframe_paths if Path(p).is_file()]

    def evidence_text(self, asset_id: str, filename: str, technical: dict[str, Any]) -> str:
        return json.dumps({
            "unit": "SCENE",
            "asset_id": asset_id,
            "filename": filename,
            "scene_index": self.scene_index,
            "start_seconds": round(self.start_seconds, 3),
            "end_seconds": round(self.end_seconds, 3),
            "keyframes_supplied": len(self.keyframe_paths),
            "technical": technical,
            "readable_text_detected": self.ocr_texts,
            "spoken_content": self.transcript_texts,
            "instruction": (
                "The attached JPEG images are the representative keyframes for this scene of the "
                "video. Evaluate all 18 locked layers for this scene from that visual evidence plus "
                "the readable text and spoken content supplied above."
            ),
        }, ensure_ascii=False)


@dataclass
class VideoEvidence:
    """Complete local evidence for one video, produced without any external call."""
    asset_id: str
    filename: str
    technical: dict[str, Any]
    scenes: list[SceneEvidence]
    audio_stream: bool
    audio_state: str
    transcript_state: str
    ocr_evaluated: bool
    ocr_observations: int

    @property
    def keyframe_count(self) -> int:
        return sum(len(s.keyframe_paths) for s in self.scenes)

    def asset_frames(self, limit: int = 12) -> list[bytes]:
        """A deterministic cross-scene sample for asset-level synthesis."""
        paths = [p for scene in self.scenes for p in scene.keyframe_paths[:1]] or \
                [p for scene in self.scenes for p in scene.keyframe_paths]
        if len(paths) > limit:
            step = len(paths) / limit
            paths = [paths[int(i * step)] for i in range(limit)]
        return [Path(p).read_bytes() for p in paths if Path(p).is_file()]

    def asset_evidence_text(self, scene_packages: Sequence[dict[str, Any]]) -> str:
        return json.dumps({
            "unit": "ASSET",
            "asset_id": self.asset_id,
            "filename": self.filename,
            "technical": self.technical,
            "canonical_scenes": len(self.scenes),
            "canonical_keyframes": self.keyframe_count,
            "audio_stream_present": self.audio_stream,
            "audio_state": self.audio_state,
            "transcript_state": self.transcript_state,
            "ocr_evaluated": self.ocr_evaluated,
            "ocr_observations": self.ocr_observations,
            "scene_results": [
                {"scene_index": index,
                 "layers": {layer["layer_id"]: layer["state"] for layer in package["layers"]},
                 "narrative": package.get("narrative", "")}
                for index, package in enumerate(scene_packages)
            ],
            "instruction": (
                "The attached JPEG images sample the keyframes across every scene of this video. "
                "Synthesise the asset-level evaluation of all 18 locked layers from that visual "
                "evidence and the per-scene results above. A layer that no scene observed must not "
                "become OBSERVED at asset level."
            ),
        }, ensure_ascii=False)


class CanonicalIndexerAdapters(Protocol):
    def eligibility(self, asset_id: str) -> AssetEligibility: ...
    def acquire(self, asset_id: str) -> tuple[bytes, dict[str, Any]]: ...
    def prepare_video_evidence(self, asset_id: str) -> VideoEvidence: ...
    def stage(self, asset_id: str, package: dict[str, Any]) -> None: ...
    def completeness(self, asset_id: str) -> bool: ...
    def publish(self, asset_id: str) -> None: ...
    def fail(self, asset_id: str, code: str, detail: str) -> None: ...


def validate_clinical_claims(package: dict[str, Any], evidence_terms: Sequence[str]) -> list[str]:
    """Rejects a named clinical claim that the supplied evidence does not carry.

    Returns the offending layer ids. Generic equipment, gloves, anatomy or contact wording in the
    evidence never licenses a named procedure: the term itself must be present in the grounded
    evidence for the layer to assert it.
    """
    haystack = " ".join(evidence_terms).lower()
    offenders: list[str] = []
    for layer in package.get("layers", []):
        if layer.get("state") != "OBSERVED":
            continue
        claim = json.dumps(layer, ensure_ascii=False).lower()
        named = [term for term in CLINICAL_TERMS if term in claim]
        if named and not any(term in haystack for term in named):
            offenders.append(str(layer.get("layer_id")))
    return offenders

def downgrade_unsupported_clinical_claims(package: dict[str, Any], offenders: Sequence[str]) -> None:
    for layer in package.get("layers", []):
        if layer.get("layer_id") in offenders:
            layer["state"] = "UNKNOWN"
            layer["evidence"] = ["DOWNGRADED_UNSUPPORTED_CLINICAL_CLAIM"]


class ProductionSemanticIndexer:
    """One-asset state machine; publication is impossible before completeness."""

    def __init__(self, adapters: CanonicalIndexerAdapters,
                 provider: ClaudeSemanticProvider | None = None) -> None:
        self.adapters = adapters
        self.provider = provider if provider is not None else build_semantic_provider()

    # ---------------------------------------------------------------- video
    def _analyze_video(self, asset_id: str, evidence: VideoEvidence) -> dict[str, Any]:
        """Per-scene keyframe analysis followed by asset-level synthesis."""
        if not evidence.scenes:
            raise RuntimeError("NO_CANONICAL_SCENE")
        scene_packages: list[dict[str, Any]] = []
        for scene in evidence.scenes:
            frames = scene.frames()
            if not frames:
                raise RuntimeError(f"NO_KEYFRAME_EVIDENCE_FOR_SCENE_{scene.scene_index}")
            package = self.provider.analyze(
                asset_id=asset_id,
                evidence_text=scene.evidence_text(asset_id, evidence.filename, evidence.technical),
                images=frames,
                request_type=f"scene:{scene.scene_index}",
            )
            offenders = validate_clinical_claims(package, scene.ocr_texts + scene.transcript_texts)
            downgrade_unsupported_clinical_claims(package, offenders)
            scene_packages.append(package)

        asset_frames = evidence.asset_frames()
        if not asset_frames:
            raise RuntimeError("NO_KEYFRAME_EVIDENCE_FOR_ASSET")
        asset_package = self.provider.analyze(
            asset_id=asset_id,
            evidence_text=evidence.asset_evidence_text(scene_packages),
            images=asset_frames,
            request_type="asset",
        )
        grounded = [t for scene in evidence.scenes for t in scene.ocr_texts + scene.transcript_texts]
        offenders = validate_clinical_claims(asset_package, grounded)
        downgrade_unsupported_clinical_claims(asset_package, offenders)
        # An asset layer cannot exceed what any scene actually observed.
        observed_by_scene = {
            layer_id: any(
                next((l for l in package["layers"] if l["layer_id"] == layer_id), {}).get("state") == "OBSERVED"
                for package in scene_packages
            )
            for layer_id in LAYER_IDS
        }
        for layer in asset_package["layers"]:
            if layer["state"] == "OBSERVED" and not observed_by_scene.get(layer["layer_id"], False):
                layer["state"] = "UNKNOWN"
                layer.setdefault("evidence", []).append("DOWNGRADED_NO_SCENE_OBSERVATION")
        asset_package["scene_packages"] = scene_packages
        return asset_package

    # ---------------------------------------------------------------- entry
    def index_asset_fully(self, asset_id: str) -> dict[str, Any]:
        eligibility = self.adapters.eligibility(asset_id)
        try:
            # Local evidence preparation is never gated by external-AI approval.
            if eligibility.is_video:
                evidence = self.adapters.prepare_video_evidence(asset_id)
                metadata: dict[str, Any] = {
                    "technical": evidence.technical,
                    "canonical_scenes": len(evidence.scenes),
                    "canonical_keyframes": evidence.keyframe_count,
                    "audio_state": evidence.audio_state,
                    "transcript_state": evidence.transcript_state,
                    "ocr_evaluated": evidence.ocr_evaluated,
                }
                media: bytes | None = None
            else:
                evidence = None
                media, metadata = self.adapters.acquire(asset_id)

            if not eligibility.may_use_external_ai:
                detail = (f"external inference denied: classification={eligibility.classification_status}, "
                          f"internal_usage={eligibility.internal_usage_status}, "
                          f"external_ai={eligibility.external_ai_status}")
                self.adapters.fail(asset_id, "PRIVACY_ELIGIBILITY_REQUIRED", detail)
                return {"asset_id": asset_id, "status": "BLOCKED", "code": "PRIVACY_ELIGIBILITY_REQUIRED",
                        "local_evidence_complete": True,
                        "canonical_scenes": metadata.get("canonical_scenes"),
                        "canonical_keyframes": metadata.get("canonical_keyframes")}

            if eligibility.is_video:
                package = self._analyze_video(asset_id, evidence)  # type: ignore[arg-type]
            else:
                package = self.provider.analyze(asset_id=asset_id, evidence_text=json.dumps(metadata, default=str),
                                                image_bytes=media)
                offenders = validate_clinical_claims(package, [json.dumps(metadata, default=str)])
                downgrade_unsupported_clinical_claims(package, offenders)

            self.adapters.stage(asset_id, {"metadata": metadata, "semantic": package,
                                           "evidence": evidence,
                                           "provider_usage": list(self.provider.usage)})
            if not self.adapters.completeness(asset_id):
                self.adapters.fail(asset_id, "COMPLETENESS_GATE_FAILED", "18-layer contract or representations incomplete")
                return {"asset_id": asset_id, "status": "FAILED", "code": "COMPLETENESS_GATE_FAILED"}
            self.adapters.publish(asset_id)
            return {"asset_id": asset_id, "status": "SEARCH_READY", "model": package["model"],
                    "canonical_scenes": metadata.get("canonical_scenes"),
                    "canonical_keyframes": metadata.get("canonical_keyframes")}
        except ClaudeCodeUsageLimitError:
            # Not an asset fault: leave the asset untouched and let the runner pause.
            raise
        except ClaudeConfigurationError as exc:
            self.adapters.fail(asset_id, "CLAUDE_CONFIGURATION", str(exc))
            return {"asset_id": asset_id, "status": "BLOCKED", "code": "CLAUDE_CONFIGURATION"}
        except Exception as exc:
            self.adapters.fail(asset_id, "INDEXING_FAILURE", str(exc))
            return {"asset_id": asset_id, "status": "FAILED", "code": "INDEXING_FAILURE", "detail": str(exc)}
