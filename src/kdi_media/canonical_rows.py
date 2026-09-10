"""Canonical row construction for the production semantic indexer.

This is not a second indexing design: it is the persistence-shaping step of the existing pipeline,
turning a validated 18-layer Claude package plus locally produced evidence into the exact canonical
rows the certified schema already uses.

Every identifier is a deterministic uuid5 over (analysis run, unit, concept), so a resumed or
repeated run converges on the same rows instead of duplicating them.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
import uuid
from typing import Any, Mapping, Sequence

SPEC = "semantic_index_v1"
ONTOLOGY = "KDI_SEMANTIC_V2"
E5_MODEL = "intfloat/multilingual-e5-small"
E5_VERSION = "hf-main-pinned-runtime-v1"
CLIP_MODEL = "ViT-B-32"
CLIP_VERSION = "laion2b_s34b_b79k"
TEXT_NORMALIZATION = "unicode_nfkc_whitespace_v1"
DOCUMENT_VERSION = "kdi_search_document_v1"
NAMESPACE = uuid.UUID("6b1a9f27-4c3d-4a58-9e70-2d5c8f1b3a64")

LAYER_IDS = (
    "ASSET_IDENTITY_PROVENANCE", "GLOBAL_ASSET_UNDERSTANDING",
    "TEMPORAL_SCENE_STRUCTURE", "PEOPLE_ROLES", "PERSON_APPEARANCE",
    "ANATOMY", "TREATMENT_PROCEDURE", "ACTIONS_EVENTS", "RELATIONSHIPS",
    "CLINICAL_VISUAL_OBSERVATIONS", "ENVIRONMENT", "CINEMATOGRAPHY",
    "COMPOSITION", "SPEECH_TRANSCRIPT_AUDIO", "OCR_VISIBLE_TEXT",
    "MARKETING_CONTENT_USAGE", "SEMANTIC_NARRATIVE", "SEARCH_EMBEDDINGS",
)
UNSAFE = (
    "surgery", "procedure", "treatment", "hair transplant", "fue", "implantation",
    "extraction", "graft harvesting", "graft placement", "prp", "laser treatment", "injection",
)


def uid(seed: str) -> str:
    return str(uuid.uuid5(NAMESPACE, seed))


def unit_uid(asset_id: str, source_fingerprint: str, *parts: Any) -> str:
    """Identity for a physical unit of an asset - a scene, a keyframe, a visual vector.

    These units come out of local preprocessing and do not change when the semantic run changes,
    so they are keyed on the asset and its content hash rather than on the analysis run. That is
    what lets local preparation persist them now and the later semantic stage upsert the very same
    rows instead of creating a second copy. Semantic artefacts stay keyed on the run.
    """
    return uid("unit:" + ":".join([asset_id, source_fingerprint, *(str(p) for p in parts)]))


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", text)).strip()


def fingerprint(*parts: Any) -> str:
    return hashlib.sha256("\x1f".join(str(p) for p in parts).encode()).hexdigest()


def clinical_terms(text: str) -> list[str]:
    low = " " + " ".join(str(text).lower().split()) + " "
    return sorted({term for term in UNSAFE if term in low})


def grounded_clinical_text(text: str, positives: Sequence[Mapping[str, Any]]) -> str:
    grounded_terms = {term for concept in positives
                      for term in clinical_terms(str(concept.get("display_text", "")))}
    if not set(clinical_terms(text)) - grounded_terms:
        return text
    return re.sub(
        r"(?i)\b(?:surger(?:y|ies)|procedures?|treatments?|hair transplants?|fue|implantations?|"
        r"extraction|graft harvesting|graft placement|prp|laser treatment|injection)\b",
        "observation",
        text,
    )


def _concept(layer: Mapping[str, Any]) -> str:
    """A stable canonical concept code for a layer evaluation."""
    code = layer.get("canonical_code") or layer.get("concept") or layer.get("layer_id")
    return re.sub(r"[^A-Z0-9_]", "_", str(code).upper())[:120]


def _display(layer: Mapping[str, Any]) -> str:
    for key in ("display_text", "summary", "description", "value_text"):
        value = layer.get(key)
        if isinstance(value, str) and value.strip():
            return normalize(value)[:400]
    return normalize(str(layer.get("layer_id", "")).replace("_", " ").lower())


def layer_rows(asset_id: str, run_id: str, package: Mapping[str, Any]) -> list[dict[str, Any]]:
    """All 18 layers, each with an explicit evaluated terminal state."""
    rows = []
    for layer in package["layers"]:
        state = layer["state"]
        rows.append({
            "asset_id": asset_id, "layer_id": layer["layer_id"], "analysis_run_id": run_id,
            "applicability": "NOT_APPLICABLE" if state == "NOT_APPLICABLE" else "APPLICABLE",
            "semantic_state": state, "processing_status": "COMPLETE", "completeness_status": "COMPLETE",
            "confidence_summary": {"provider": package.get("provider", "claude"),
                                   "model": package.get("model"),
                                   "images": package.get("image_count", 0)},
            "human_review_status": "PENDING", "ontology_version": ONTOLOGY,
            "semantic_spec_version": SPEC, "active": False,
        })
    return rows


def assertion_rows(asset_id: str, run_id: str, package: Mapping[str, Any], source_fingerprint: str,
                   *, scene_id: str | None = None, keyframe_id: str | None = None,
                   start_time: float | None = None, end_time: float | None = None
                   ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Assertions, their evidence, and the positive concepts for the search document.

    Assertions are emitted with `search_critical` false; the caller raises it after evidence lands,
    because the database evidence guard is a deferred constraint and PostgREST commits per request.
    """
    assertions: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []
    positives: list[dict[str, Any]] = []
    unit = f"scene:{scene_id}" if scene_id else "asset"
    for layer in package["layers"]:
        state = layer["state"]
        if state not in {"OBSERVED", "FALSE"}:
            continue  # UNKNOWN and NOT_APPLICABLE assert nothing and need no evidence
        code = _concept(layer)
        assertion_id = uid(f"{run_id}:{unit}:{layer['layer_id']}:{code}")
        critical = state == "OBSERVED" and layer["layer_id"] not in {"SEARCH_EMBEDDINGS", "ASSET_IDENTITY_PROVENANCE"}
        assertions.append({
            "id": assertion_id, "asset_id": asset_id, "scene_id": scene_id, "keyframe_id": keyframe_id,
            "layer_id": layer["layer_id"], "subject_type": "SCENE" if scene_id else "ASSET",
            "predicate": code, "canonical_concept_code": code, "canonical_concept_type": layer["layer_id"],
            "value_text": _display(layer), "semantic_state": state,
            "confidence": 0.8, "confidence_source": "MEDIUM", "search_critical": critical,
            "analysis_run_id": run_id, "origin": "AI_MODEL", "ontology_version": ONTOLOGY,
            "semantic_spec_version": SPEC, "human_review_status": "PENDING", "active": False,
            "source_fingerprint": source_fingerprint,
            "idempotency_key": f"production:{run_id}:{unit}:{layer['layer_id']}",
        })
        evidence.append({
            "assertion_id": assertion_id,
            "evidence_type": "KEYFRAME_LEVEL" if keyframe_id else ("SCENE_LEVEL" if scene_id else "ASSET_LEVEL"),
            "polarity": "POSITIVE" if state == "OBSERVED" else "NEGATIVE",
            "completeness": "COMPLETE", "asset_id": asset_id, "scene_id": scene_id,
            "keyframe_id": keyframe_id, "start_time": start_time, "end_time": end_time,
            "evidence_score": 0.8, "source_fingerprint": source_fingerprint, "analysis_run_id": run_id,
        })
        if state == "OBSERVED":
            positives.append({"assertion_id": assertion_id, "canonical_code": code,
                              "display_text": _display(layer), "concept_type": layer["layer_id"],
                              "semantic_state": "OBSERVED", "confidence": 0.8, "origin": "AI_MODEL",
                              "search_critical": critical, "resolution_source": "UNVERIFIED_AI"})
    return assertions, evidence, positives


def searchable_text(filename: str, package: Mapping[str, Any], extra: Sequence[str] = (),
                    positives: Sequence[Mapping[str, Any]] = ()) -> str:
    """Grounded search text. Clinical wording only survives if the layer actually asserted it."""
    parts = [filename, grounded_clinical_text(normalize(str(package.get("narrative", ""))), positives)]
    for layer in package["layers"]:
        if layer["state"] == "OBSERVED":
            parts.append(_display(layer))
    parts.extend(grounded_clinical_text(normalize(x), positives) for x in extra if x)
    return normalize(" ".join(p for p in parts if p))[:8000]


def scene_row(asset_id: str, run_id: str, scene, package: Mapping[str, Any],
              description: str, source_fingerprint: str = "") -> dict[str, Any]:
    """One canonical scene. `duration_seconds` is a generated column and is never written."""
    return {
        "id": unit_uid(asset_id, source_fingerprint, "scene", scene.scene_index), "asset_id": asset_id,
        "scene_index": scene.scene_index, "start_seconds": round(scene.start_seconds, 3),
        "end_seconds": round(scene.end_seconds, 3), "scene_type": "CANONICAL_SEMANTIC_SCENE",
        "literal_description": description, "short_description": description,
        "detection_method": "LOCAL_SHOT_CHANGE_AND_QUALITY_V1", "confidence": 0.8,
        "review_status": "NOT_REVIEWED", "source": "PRODUCTION_INDEXER",
        "processor_version": "kdi_production_indexer_v1", "configuration_version": "kdi_production_indexer_v1",
        "semantic_label": "CANONICAL_SEMANTIC_SCENE",
        "semantic_state": "OBSERVED" if any(l["state"] == "OBSERVED" for l in package["layers"]) else "UNKNOWN",
        "semantic_version": SPEC, "canonical_active": False, "semantic_analysis_run_id": run_id,
        "metadata": {"keyframes": len(scene.keyframe_paths)},
    }


def keyframe_rows(asset_id: str, run_id: str, scene, scene_id: str,
                  source_fingerprint: str) -> list[dict[str, Any]]:
    rows = []
    for index, path in enumerate(scene.keyframe_paths):
        rows.append({
            "id": unit_uid(asset_id, source_fingerprint, "kf", scene.scene_index, index),
            "asset_id": asset_id,
            "scene_id": scene_id, "timestamp_seconds": round(scene.start_seconds, 3),
            "frame_index": index, "selection_reason": "REPRESENTATIVE_SCENE_KEYFRAME",
            "visual_description": None, "is_representative": True, "review_status": "NOT_REVIEWED",
            "source_fingerprint": source_fingerprint, "processor_version": "kdi_production_indexer_v1",
            "semantic_analysis_run_id": run_id, "semantic_version": SPEC,
            "metadata": {"local_path_basename": path.rsplit("\\", 1)[-1].rsplit("/", 1)[-1]},
        })
    return rows


def document_row(document_id: str, run_id: str, asset_id: str, filename: str, media_type: str,
                 text: str, positives: Sequence[Mapping[str, Any]], *, document_type: str,
                 scene_id: str | None = None, start_time: float | None = None,
                 end_time: float | None = None, source_fingerprint: str = "") -> dict[str, Any]:
    leaked = clinical_terms(text)
    supported = {term for concept in positives for term in clinical_terms(str(concept.get("display_text", "")))}
    if set(leaked) - supported:
        raise RuntimeError(f"SEARCH_DOCUMENT_CLINICAL_LEAKAGE:{sorted(set(leaked) - supported)}")
    return {
        "id": document_id, "asset_id": asset_id, "scene_id": scene_id, "document_type": document_type,
        "filename": filename, "media_type": media_type, "start_time": start_time, "end_time": end_time,
        "normalized_document": {"filename": filename, "concepts": [c["canonical_code"] for c in positives]},
        "search_text": text, "positive_concepts": list(positives), "negative_concepts": [],
        "search_document_version": DOCUMENT_VERSION, "builder_version": "kdi_production_indexer_v1",
        "configuration_version": "kdi_production_indexer_v1",
        "semantic_spec_fingerprint": fingerprint(SPEC, ONTOLOGY),
        "semantic_spec_version": SPEC, "ontology_version": ONTOLOGY, "source_semantic_version": SPEC,
        "source_fingerprint": source_fingerprint, "source_semantic_fingerprint": source_fingerprint,
        "document_fingerprint": hashlib.sha256(text.encode()).hexdigest(), "status": "READY",
        "review_status": "AI_UNREVIEWED", "human_approved": False, "review_required": False,
        "active": False, "stale": False, "build_run_id": run_id,
    }


def text_embedding_row(row_id: str, run_id: str, asset_id: str, vector: Sequence[float], text: str,
                       document_fingerprint: str, *, scope: str, scene_id: str | None = None,
                       source_unit_id: str | None = None) -> dict[str, Any]:
    if len(vector) != 384:
        raise RuntimeError(f"E5_DIMENSION_MISMATCH:{len(vector)}")
    text_fp = fingerprint(text, TEXT_NORMALIZATION, document_fingerprint)
    return {
        "id": row_id, "asset_id": asset_id, "scene_id": scene_id, "embedding_scope": scope,
        "representation_type": scope, "provider": "sentence_transformers", "model": E5_MODEL,
        "model_version": E5_VERSION, "version": "kdi_text_embedding_v1",
        "embedding_version": "kdi_text_embedding_v1", "embedding_bundle_version": "kdi_embedding_bundle_v1",
        "dimensions": 384, "embedding": list(vector), "source_fingerprint": text_fp,
        "source_text_fingerprint": text_fp, "source_document_fingerprint": document_fingerprint,
        "vector_fingerprint": fingerprint(E5_MODEL, E5_VERSION, 384, text_fp),
        "text_normalization_version": TEXT_NORMALIZATION, "semantic_spec_version": SPEC,
        "source_semantic_version": SPEC, "ontology_version": ONTOLOGY, "analysis_run_id": run_id,
        "active": False, "stale": False, "review_status": "AI_UNREVIEWED",
        "metadata": {"source_kind": scope, "source_unit_id": source_unit_id,
                     "construction": "passage_prefix_canonical_search_text_v1"},
    }


def visual_embedding_row(row_id: str, run_id: str, asset_id: str, vector: Sequence[float],
                         source_fingerprint: str, *, scope: str, scene_id: str | None = None,
                         keyframe_id: str | None = None, metadata: Mapping[str, Any] | None = None
                         ) -> dict[str, Any]:
    if len(vector) != 512:
        raise RuntimeError(f"OPENCLIP_DIMENSION_MISMATCH:{len(vector)}")
    return {
        "id": row_id, "asset_id": asset_id, "scene_id": scene_id, "keyframe_id": keyframe_id,
        "embedding_scope": scope, "representation_type": scope, "provider": "open_clip",
        "model": CLIP_MODEL, "model_version": CLIP_VERSION, "version": "kdi_visual_embedding_v1",
        "embedding_version": "kdi_visual_embedding_v1", "embedding_bundle_version": "kdi_embedding_bundle_v1",
        "dimensions": 512, "embedding": list(vector), "source_fingerprint": source_fingerprint,
        "vector_fingerprint": fingerprint(CLIP_MODEL, CLIP_VERSION, 512, row_id),
        "preprocessing_version": "openclip_exif_rgb_bicubic_v1" if keyframe_id else "l2_mean_pool_l2_v1",
        "semantic_spec_version": SPEC, "source_semantic_version": SPEC, "ontology_version": ONTOLOGY,
        "analysis_run_id": run_id, "active": False, "stale": False, "review_status": "AI_UNREVIEWED",
        "metadata": dict(metadata or {}),
    }


def narrative_row(run_id: str, asset_id: str, package: Mapping[str, Any], text: str,
                  positives: Sequence[Mapping[str, Any]] = ()) -> dict[str, Any]:
    grounded_terms = {term for concept in positives
                      for term in clinical_terms(str(concept.get("display_text", "")))}
    narrative_terms = set(clinical_terms(text))
    if narrative_terms - grounded_terms:
        text = grounded_clinical_text(text, positives)
    return {
        "id": uid(f"{run_id}:narrative"), "asset_id": asset_id, "narrative_type": "ASSET_NARRATIVE",
        "text": normalize(text)[:4000] or "No determinate narrative was supported by the evidence.",
        "search_status": "ACCEPTED_FOR_SEARCH",
        "input_evidence_fingerprint": fingerprint(package.get("model"), len(package["layers"])),
        "generator_version": "kdi_production_indexer_v1", "configuration_version": "kdi_production_indexer_v1",
        "analysis_run_id": run_id, "human_review_status": "PENDING", "active": False, "stale": False,
    }
