"""Deterministic KDI 18-layer completeness evaluation.

This module evaluates database evidence only.  It never opens media or invokes an
extractor.  Callers must first verify the locked specification fingerprint.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from hashlib import sha256
import json

SPEC_VERSION = "kdi_semantic_18_layer_v1"
SPEC_FINGERPRINT = "6da50e2153f6fcb6c9ef27c308ad44d0d2024e702e3faad47586b0068ba64fd7"
EVALUATOR_VERSION = "kdi_completeness_v1.0.0"


@dataclass(frozen=True)
class LayerEvidence:
    asset_id: str
    filename: str
    layer_id: str
    media_kind: str
    processing_status: str = "COMPLETE"
    current_status: str = "PARTIAL"
    semantic_state: str = "UNKNOWN"
    assertion_count: int = 0
    evidence_count: int = 0
    evaluation_marker: bool = False
    modality_assessed: bool = False
    has_audio: bool | None = None
    has_speech: bool | None = None
    speech_intelligible: bool | None = None
    transcript_processed: bool = False
    visible_text: bool | None = None
    text_readable: bool | None = None
    ocr_processed: bool = False
    temporal_coverage_percent: float | None = None
    temporal_review_required: bool = False
    short_description: bool = False
    master_description: bool = False
    narrative_grounded: bool = False
    search_document: bool = False
    normalized_search_text: bool = False
    concepts: bool = False
    text_embedding: bool = False
    visual_embedding_applicable: bool = False
    visual_embedding: bool = False
    scene_embedding_applicable: bool = False
    scene_embedding: bool = False
    representation_metadata: bool = False
    evidence_lineage: bool = False
    representation_spec_version: str | None = None


@dataclass(frozen=True)
class CompletenessDecision:
    asset_id: str
    filename: str
    layer_id: str
    previous_status: str
    new_status: str
    semantic_resolution: str
    applicable: str
    requirements_total: int
    requirements_satisfied: int
    requirements_not_applicable: int
    requirements_unknown_but_evaluated: int
    missing_requirements: tuple[str, ...] = field(default_factory=tuple)
    evidence_sources: tuple[str, ...] = field(default_factory=tuple)
    failure_type: str | None = None
    rationale: str = ""
    spec_version: str = SPEC_VERSION
    spec_fingerprint: str = SPEC_FINGERPRINT
    evaluator_version: str = EVALUATOR_VERSION

    @property
    def requirements_missing(self) -> int:
        return len(self.missing_requirements)

    def fingerprint(self) -> str:
        value = asdict(self)
        value["missing_requirements"] = list(self.missing_requirements)
        value["evidence_sources"] = list(self.evidence_sources)
        return sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def verify_spec(spec: dict) -> None:
    if not (spec.get("spec_version") == SPEC_VERSION and
            spec.get("spec_fingerprint") == SPEC_FINGERPRINT and
            spec.get("locked") is True and spec.get("status") == "LOCKED" and
            spec.get("definition_count") == 18 and spec.get("descriptions_populated") == 18):
        raise RuntimeError("locked semantic specification verification failed")


def _decision(e: LayerEvidence, missing: list[str], total: int, *, applicable="TRUE",
              unknown=0, na=0, sources=(), failure=None, rationale="") -> CompletenessDecision:
    status = "COMPLETE" if not missing else "PARTIAL"
    if status == "COMPLETE" and e.current_status == "PARTIAL":
        failure = "STATUS_BUG"
    return CompletenessDecision(
        e.asset_id, e.filename, e.layer_id, e.current_status, status,
        "NOT_APPLICABLE" if applicable == "FALSE" else e.semantic_state,
        applicable, total, total-len(missing)-na, na, unknown, tuple(missing),
        tuple(sources), failure, rationale)


def evaluate_layer_completeness(e: LayerEvidence) -> CompletenessDecision:
    if e.processing_status != "COMPLETE":
        return _decision(e, ["processing job did not complete"], 1,
                         failure="EXTRACTION_GAP", rationale="Processing cannot prove evaluation coverage.")

    lid = e.layer_id
    sources = ["asset_semantic_layers"]
    if e.assertion_count:
        sources.append("semantic_assertions")
    if e.evidence_count:
        sources.append("semantic_assertion_evidence")

    if lid == "ASSET_IDENTITY_PROVENANCE":
        missing=[] if e.evaluation_marker else ["required deterministic metadata/provenance linkage evaluation"]
        return _decision(e,missing,1,sources=sources+(["assets","asset_sources"] if not missing else []),failure="EXTRACTION_GAP")
    if lid == "TEMPORAL_SCENE_STRUCTURE":
        if e.media_kind == "image":
            return _decision(e,[],1,applicable="FALSE",na=1,sources=sources+["assets"],rationale="Still-image temporal segmentation is not applicable.")
        missing=[]
        if not e.evaluation_marker or (e.temporal_coverage_percent or 0) < 100:
            missing.append("full usable-duration temporal coverage")
        if e.temporal_review_required:
            missing.append("segmentation-policy review/possible under-segmentation resolution")
        return _decision(e,missing,2,sources=sources+["asset_scenes"],failure="EXTRACTION_GAP")
    if lid == "SPEECH_TRANSCRIPT_AUDIO":
        if not e.modality_assessed:
            return _decision(e,["audio-track applicability assessment"],2,failure="INFRASTRUCTURE_GAP",sources=sources)
        if e.has_audio is False:
            return _decision(e,[],2,applicable="FALSE",na=2,sources=sources,rationale="No audio track; transcript is not applicable.")
        missing=[]
        if e.has_speech and e.speech_intelligible and not e.transcript_processed:
            missing.append("transcription of understandable speech")
        return _decision(e,missing,2,unknown=int(e.has_speech is True and e.speech_intelligible is False),sources=sources,failure="EXTRACTION_GAP")
    if lid == "OCR_VISIBLE_TEXT":
        if not (e.modality_assessed and e.ocr_processed):
            return _decision(e,["OCR applicability/frame evaluation"],2,failure="EXTRACTION_GAP",sources=sources)
        if e.visible_text is False:
            return _decision(e,[],2,applicable="FALSE",na=2,sources=sources,rationale="Explicit OCR evaluation found no visible text.")
        return _decision(e,[],2,unknown=int(e.visible_text is True and e.text_readable is False),sources=sources)
    if lid == "SEMANTIC_NARRATIVE":
        missing=[]
        if not e.short_description: missing.append("short description")
        if not e.master_description: missing.append("genuine detailed/master description")
        if not e.narrative_grounded: missing.append("claim-to-evidence grounding")
        return _decision(e,missing,3,sources=sources+["semantic_narratives","narrative_claims","narrative_claim_evidence"],failure="EXTRACTION_GAP")
    if lid == "SEARCH_EMBEDDINGS":
        checks=((e.search_document,"canonical search document"),(e.normalized_search_text,"normalized search text"),
                (e.concepts,"search concepts"),(e.text_embedding,"text embedding"),
                (not e.visual_embedding_applicable or e.visual_embedding,"applicable visual embedding"),
                (not e.scene_embedding_applicable or e.scene_embedding,"applicable scene embedding"),
                (e.representation_metadata,"embedding provider/model/version/dimension"),(e.evidence_lineage,"evidence lineage"),
                (e.representation_spec_version==SPEC_VERSION,"locked V1 representation linkage"))
        missing=[name for ok,name in checks if not ok]
        return _decision(e,missing,len(checks),sources=sources+["search_document_builds","semantic_embeddings"],failure="INFRASTRUCTURE_GAP")
    if lid == "GLOBAL_ASSET_UNDERSTANDING":
        missing=[]
        if not e.evaluation_marker: missing.append("global-category evaluation marker")
        if not e.short_description: missing.append("concise short description")
        if not e.master_description: missing.append("richer master description")
        return _decision(e,missing,3,sources=sources,failure="EXTRACTION_GAP")

    # Layers 4-13 and 16 have a persisted phase-wide evaluation marker plus
    # explicit assertions. UNKNOWN assertions are evaluated outcomes and do
    # not require positive evidence.
    missing=[] if e.evaluation_marker and e.assertion_count > 0 else ["persisted layer evaluation outcome"]
    unknown=int(e.semantic_state == "UNKNOWN" and not missing)
    return _decision(e,missing,1,unknown=unknown,sources=sources,failure="EXTRACTION_GAP",
                     rationale="Explicit evaluated UNKNOWN is complete; positive assertion count is not a completeness metric.")
