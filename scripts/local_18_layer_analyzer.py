"""Grounded LOCAL assembler for the locked KDI 18-layer contract.

The VLM supplies only atomic visual observations. Deterministic database/local
evidence supplies provenance, time, transcript, OCR, narratives and search.
"""
from __future__ import annotations

import re
from typing import Any, Mapping, Sequence

PROCESSOR_VERSION = "kdi_local_18_layer_scene_analyzer_v4"
PROVIDER = "LOCAL_TRANSFORMERS"
MODEL = "HuggingFaceTB/SmolVLM2-500M-Video-Instruct"
SPEC = "kdi_semantic_18_layer_v1"
STATES = {"OBSERVED", "FALSE", "UNKNOWN", "NOT_APPLICABLE"}
LAYER_IDS = (
    "ASSET_IDENTITY_PROVENANCE", "GLOBAL_ASSET_UNDERSTANDING",
    "TEMPORAL_SCENE_STRUCTURE", "PEOPLE_ROLES", "PERSON_APPEARANCE",
    "ANATOMY", "TREATMENT_PROCEDURE", "ACTIONS_EVENTS", "RELATIONSHIPS",
    "CLINICAL_VISUAL_OBSERVATIONS", "ENVIRONMENT", "CINEMATOGRAPHY",
    "COMPOSITION", "SPEECH_TRANSCRIPT_AUDIO", "OCR_VISIBLE_TEXT",
    "MARKETING_CONTENT_USAGE", "SEMANTIC_NARRATIVE", "SEARCH_EMBEDDINGS",
)
NAMED_TREATMENTS = ("hair transplant", "fue", "implantation", "graft harvesting",
                    "graft placement", "prp", "laser treatment", "injection")


def _layer(layer_id: str, state: str, text: str, source: str) -> dict[str, Any]:
    if state not in STATES:
        raise ValueError(f"invalid semantic state: {state}")
    return {"layer_id": layer_id, "state": state, "display_text": text,
            "evidence_source": source, "processing_status": "COMPLETE"}


def _state(observations: Mapping[str, str], key: str) -> str:
    value = str(observations.get(key, "UNKNOWN")).upper()
    return value if value in {"OBSERVED", "FALSE", "UNKNOWN"} else "UNKNOWN"


def _named_treatment(texts: Sequence[str]) -> str | None:
    haystack = " ".join(texts).lower()
    return next((term for term in NAMED_TREATMENTS if re.search(r"\b" + re.escape(term) + r"\b", haystack)), None)


def assemble(record: Mapping[str, Any], observations: Mapping[str, str], *,
             scene_index: int | None = None) -> dict[str, Any]:
    """Assemble exactly 18 evaluated layers from grounded evidence."""
    video = str(record.get("media_type")) == "VIDEO"
    scenes = list(record.get("scenes") or [])
    transcript = [str(x.get("text") or "") for x in record.get("transcript_chunks", [])]
    ocr_items = list(record.get("ocr_observations_list") or [])
    ocr = [str(x.get("text") or x.get("raw_text") or "") for x in ocr_items]
    grounded_text = transcript + ocr
    treatment = _named_treatment(grounded_text)
    people, anatomy, action = (_state(observations, x) for x in ("people", "anatomy", "action"))
    environment = _state(observations, "environment")
    closeup = _state(observations, "closeup")
    centered = _state(observations, "centered")
    direct = _state(observations, "direct_to_camera")
    transcript_state = str(record.get("transcript_state") or "UNKNOWN")
    identity_text = (f"{record.get('filename','')} ({record.get('mime_type','')}); "
                     f"checksum {record.get('checksum','UNKNOWN')}")
    temporal_text = (f"{len(scenes)} canonical scenes with {len(record.get('keyframes') or [])} keyframes"
                     if video else "Temporal structure does not apply to a still image")
    global_state = "OBSERVED" if any(x == "OBSERVED" for x in observations.values()) or grounded_text else "UNKNOWN"
    global_text = "Grounded visual asset with evaluated local evidence" if global_state == "OBSERVED" else "Visual content remains indeterminate"
    speech_state = ("NOT_APPLICABLE" if transcript_state == "NOT_APPLICABLE" else
                    "OBSERVED" if transcript_state == "MEANINGFUL_SPEECH" else
                    "FALSE" if transcript_state in {"NO_MEANINGFUL_SPEECH", "NO_SPEECH"} else "UNKNOWN")
    speech_text = ("Meaningful speech is represented by grounded transcript chunks" if speech_state == "OBSERVED" else
                   "No meaningful speech detected" if speech_state == "FALSE" else
                   "No audio track" if speech_state == "NOT_APPLICABLE" else "Speech evidence is indeterminate")
    ocr_state = "OBSERVED" if ocr else ("NOT_APPLICABLE" if record.get("ocr_evaluated") is True else "UNKNOWN")
    ocr_text = "Visible text: " + " | ".join(ocr)[:300] if ocr else "No readable visible text detected"
    layers = [
        _layer(LAYER_IDS[0], "OBSERVED", identity_text, "DATABASE_METADATA"),
        _layer(LAYER_IDS[1], global_state, global_text, "LOCAL_VISUAL_AND_TEXT_EVIDENCE"),
        _layer(LAYER_IDS[2], "OBSERVED" if video else "NOT_APPLICABLE", temporal_text, "SCENE_TECHNICAL_METADATA"),
        _layer(LAYER_IDS[3], people, "One or more people/body parts visible" if people == "OBSERVED" else "People/roles not reliably resolved", "KEYFRAME"),
        _layer(LAYER_IDS[4], "UNKNOWN" if people == "OBSERVED" else "NOT_APPLICABLE" if people == "FALSE" else "UNKNOWN", "Appearance categories not safely resolved", "KEYFRAME"),
        _layer(LAYER_IDS[5], anatomy, "A visible body region is supported" if anatomy == "OBSERVED" else "Anatomy not reliably resolved", "KEYFRAME"),
        _layer(LAYER_IDS[6], "OBSERVED" if treatment else "UNKNOWN", treatment or "Named treatment is not grounded", "TRANSCRIPT_OR_OCR" if treatment else "EVALUATED_NO_GROUNDED_TREATMENT"),
        _layer(LAYER_IDS[7], action, "Visible physical action is supported" if action == "OBSERVED" else "Action not reliably resolved", "KEYFRAME"),
        _layer(LAYER_IDS[8], "UNKNOWN", "Entity relationship is not reliably resolved", "KEYFRAME"),
        _layer(LAYER_IDS[9], "UNKNOWN", "No diagnostic or specific clinical observation asserted", "KEYFRAME"),
        _layer(LAYER_IDS[10], environment, "Broad environment is visible" if environment == "OBSERVED" else "Environment not reliably resolved", "KEYFRAME"),
        _layer(LAYER_IDS[11], closeup, "Close-up capture is visible" if closeup == "OBSERVED" else "Shot type not reliably resolved", "KEYFRAME_AND_TECHNICAL_METADATA"),
        _layer(LAYER_IDS[12], centered, "Primary visible content is centrally framed" if centered == "OBSERVED" else "Composition not reliably resolved", "KEYFRAME"),
        _layer(LAYER_IDS[13], speech_state, speech_text, "FASTER_WHISPER_AND_AUDIO_PROBE"),
        _layer(LAYER_IDS[14], ocr_state, ocr_text, "LOCAL_OCR"),
        _layer(LAYER_IDS[15], "OBSERVED" if direct == "OBSERVED" else "UNKNOWN", "Direct-to-camera content characteristic" if direct == "OBSERVED" else "Marketing/content usage remains indeterminate", "KEYFRAME"),
        _layer(LAYER_IDS[16], "OBSERVED", "Evidence-grounded deterministic narrative generated", "VALIDATED_ASSERTIONS"),
        _layer(LAYER_IDS[17], "OBSERVED", "Canonical search document and separate text/visual embeddings evaluated", "CANONICAL_SEARCH_BUILD"),
    ]
    if tuple(x["layer_id"] for x in layers) != LAYER_IDS:
        raise RuntimeError("LOCAL_18_LAYER_CONTRACT_MISMATCH")
    observed = [x["display_text"] for x in layers if x["state"] == "OBSERVED" and x["layer_id"] not in {LAYER_IDS[16], LAYER_IDS[17]}]
    narrative = ". ".join(observed[:6]) + "."
    package = {"provider": PROVIDER, "model": MODEL, "processor_version": PROCESSOR_VERSION,
               "semantic_spec_version": SPEC, "layers": layers,
               "narrative": narrative, "image_count": 1,
               "scene_index": scene_index, "external_ai_calls": 0}
    validate(package)
    return package


def synthesize_asset(record: Mapping[str, Any], scene_packages: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Conservative scene-to-asset merge; no new positive visual fact is introduced."""
    merged: dict[str, str] = {}
    for key in ("people", "anatomy", "action", "environment", "closeup", "centered", "direct_to_camera"):
        states = [next((l["state"] for l in p["layers"] if {
            "people": "PEOPLE_ROLES", "anatomy": "ANATOMY", "action": "ACTIONS_EVENTS",
            "environment": "ENVIRONMENT", "closeup": "CINEMATOGRAPHY",
            "centered": "COMPOSITION", "direct_to_camera": "MARKETING_CONTENT_USAGE"}[key] == l["layer_id"]), "UNKNOWN") for p in scene_packages]
        merged[key] = "OBSERVED" if "OBSERVED" in states else "FALSE" if states and all(x == "FALSE" for x in states) else "UNKNOWN"
    result = assemble(record, merged)
    result["scene_packages"] = list(scene_packages)
    return result


def validate(package: Mapping[str, Any]) -> None:
    layers = list(package.get("layers") or [])
    ids = [x.get("layer_id") for x in layers]
    if len(layers) != 18 or len(set(ids)) != 18 or tuple(ids) != LAYER_IDS:
        raise ValueError("exactly the locked 18 unique layer ids are required")
    if any(x.get("state") not in STATES or x.get("processing_status") != "COMPLETE" for x in layers):
        raise ValueError("invalid or incomplete semantic state")
    clinical = " ".join(str(x.get("display_text", "")) for x in layers if x["layer_id"] in {"TREATMENT_PROCEDURE", "CLINICAL_VISUAL_OBSERVATIONS"} and x["state"] == "OBSERVED").lower()
    grounded = " ".join(str(x.get("display_text", "")) for x in layers if x.get("evidence_source") == "TRANSCRIPT_OR_OCR").lower()
    if any(t in clinical and t not in grounded for t in NAMED_TREATMENTS):
        raise ValueError("unsupported clinical claim")
