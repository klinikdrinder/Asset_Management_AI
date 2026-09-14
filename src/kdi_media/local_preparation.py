"""Canonical rows for the locally-completable half of the pipeline.

Everything here is produced without transmitting anything: technical probe, canonical scenes,
representative keyframes, local transcription, local OCR, and OpenCLIP 512D visual vectors. No
semantic layer, assertion, narrative, search document or E5 text vector is produced, because those
depend on the external 18-layer evaluation that stays deferred until human privacy review.

Physical units are keyed by `canonical_rows.unit_uid`, so when the semantic stage is resumed after
that review it upserts these very rows instead of creating a second copy of the same scene.
"""
from __future__ import annotations

from typing import Any, Callable, Mapping, Sequence

from . import canonical_rows as cr

PROCESSOR = "kdi_local_preparation_v1"
RUN_TYPE = "LOCAL_PREPARATION"
EXTERNAL_STATUS = "PENDING_PRIVACY_REVIEW"


def run_row(asset_id: str, run_id: str, source_fingerprint: str, started_at: str,
            metadata: Mapping[str, Any]) -> dict[str, Any]:
    """The analysis run local preparation writes under.

    Status is RUNNING, not FAILED and not COMPLETED: the local half is finished but the run as a
    whole is genuinely still open, waiting on the external evaluation.
    """
    return {
        "id": run_id, "asset_id": asset_id, "run_type": RUN_TYPE, "status": "RUNNING",
        "semantic_spec_version": cr.SPEC, "ontology_version": cr.ONTOLOGY,
        "processor_version": PROCESSOR, "configuration_version": PROCESSOR,
        "configuration_fingerprint": cr.fingerprint(PROCESSOR, cr.SPEC, source_fingerprint),
        "source_fingerprint": source_fingerprint, "embedding_version": "kdi_visual_embedding_v1",
        "provider": "local", "model": cr.CLIP_MODEL, "model_version": cr.CLIP_VERSION,
        "started_at": started_at,
        "metadata": {**dict(metadata), "external_semantic_status": EXTERNAL_STATUS,
                     "local_evidence_complete": True, "search_ready": False,
                     "external_ai_calls": 0},
    }


def scene_rows(asset_id: str, run_id: str, source_fingerprint: str,
               scenes: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Canonical scene boundaries with no description.

    The description is deliberately left empty: it is semantic output, and inventing one here would
    fabricate the very thing the privacy gate defers. `canonical_active` stays false so no asset can
    become SEARCH_READY on locally derived evidence alone.
    """
    return [{
        "id": cr.unit_uid(asset_id, source_fingerprint, "scene", scene["scene_index"]),
        "asset_id": asset_id, "scene_index": int(scene["scene_index"]),
        "start_seconds": round(float(scene["start_seconds"]), 3),
        "end_seconds": round(float(scene["end_seconds"]), 3),
        "scene_type": "CANONICAL_SEMANTIC_SCENE",
        "detection_method": "LOCAL_SHOT_CHANGE_AND_QUALITY_V1", "confidence": 0.8,
        "review_status": "NOT_REVIEWED", "source": "LOCAL_PREPARATION",
        "processor_version": PROCESSOR, "configuration_version": PROCESSOR,
        "semantic_label": "CANONICAL_SEMANTIC_SCENE", "semantic_state": "UNKNOWN",
        "semantic_version": cr.SPEC, "canonical_active": False,
        "semantic_analysis_run_id": run_id,
        "metadata": {"stage": "LOCAL_EVIDENCE_COMPLETE", "external_semantic_status": EXTERNAL_STATUS},
    } for scene in scenes]


def keyframe_rows(asset_id: str, run_id: str, source_fingerprint: str,
                  keyframes: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for frame in keyframes:
        scene_index = int(frame["scene_index"])
        basename = str(frame["path"]).replace(chr(92), "/").rsplit("/", 1)[-1]
        rows.append({
            "id": cr.unit_uid(asset_id, source_fingerprint, "kf", scene_index, int(frame["frame_index"])),
            "asset_id": asset_id,
            "scene_id": cr.unit_uid(asset_id, source_fingerprint, "scene", scene_index),
            "timestamp_seconds": round(float(frame["timestamp"]), 3),
            "frame_index": int(frame["frame_index"]),
            "selection_reason": "REPRESENTATIVE_SCENE_KEYFRAME", "is_representative": True,
            "review_status": "NOT_REVIEWED", "source_fingerprint": source_fingerprint,
            "processor_version": PROCESSOR, "semantic_analysis_run_id": run_id,
            "semantic_version": cr.SPEC,
            "metadata": {"local_path_basename": basename},
        })
    return rows


def ocr_rows(asset_id: str, run_id: str, source_fingerprint: str,
             observations: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Local OCR. `text_type` stays OTHER because classifying the text is a semantic judgement."""
    rows = []
    for index, item in enumerate(observations):
        text = cr.normalize(str(item.get("text") or ""))
        if not text:
            continue
        scene_index = item.get("scene_index")
        scene_id = keyframe_id = None
        if scene_index is not None:
            scene_id = cr.unit_uid(asset_id, source_fingerprint, "scene", int(scene_index))
            keyframe_id = cr.unit_uid(asset_id, source_fingerprint, "kf", int(scene_index),
                                      int(item.get("frame_index", 0)))
        confidence = item.get("confidence")
        rows.append({
            "id": cr.unit_uid(asset_id, source_fingerprint, "ocr", index),
            "asset_id": asset_id, "scene_id": scene_id, "keyframe_id": keyframe_id,
            "timestamp_seconds": item.get("timestamp"), "raw_text": text[:2000],
            "normalized_text": text.lower()[:2000], "text_type": "OTHER", "language": "en",
            "confidence": round(float(confidence), 4) if isinstance(confidence, (int, float)) else None,
            "provenance": "OCR", "provider": "easyocr", "model": "craft_english_g2",
            "version": PROCESSOR, "search_status": "PENDING_SEMANTIC_REVIEW",
            "source_text_fingerprint": cr.fingerprint(text, cr.TEXT_NORMALIZATION, source_fingerprint),
            "semantic_analysis_run_id": run_id, "human_review_status": "PENDING",
            "metadata": {"stage": "LOCAL_EVIDENCE_COMPLETE", "bounding_box": item.get("box")},
        })
    return rows


def transcript_rows(asset_id: str, run_id: str, source_fingerprint: str,
                    chunks: Sequence[Mapping[str, Any]],
                    scenes: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Local transcript chunks, linked to a scene only when fully contained by it."""
    rows = []
    for index, chunk in enumerate(chunks):
        scene_id = None
        for scene in scenes:
            if (float(scene["start_seconds"]) - 1e-6 <= float(chunk["start"])
                    and float(chunk["end"]) <= float(scene["end_seconds"]) + 1e-6):
                scene_id = cr.unit_uid(asset_id, source_fingerprint, "scene", int(scene["scene_index"]))
                break
        text = cr.normalize(str(chunk.get("text") or ""))
        rows.append({
            "asset_id": asset_id, "scene_id": scene_id,
            "start_seconds": round(float(chunk["start"]), 3),
            "end_seconds": round(float(chunk["end"]), 3),
            "transcript_text": text[:4000], "raw_text": text[:4000],
            "normalized_text": text.lower()[:4000],
            "language": chunk.get("language"), "transcription_status": "COMPLETE",
            "confidence": chunk.get("confidence"), "search_status": "PENDING_SEMANTIC_REVIEW",
            "source_text_fingerprint": cr.fingerprint(text, cr.TEXT_NORMALIZATION, source_fingerprint),
            "provider": "faster_whisper", "model": "Systran/faster-whisper-small", "version": PROCESSOR,
            "semantic_analysis_run_id": run_id, "human_review_status": "PENDING",
            "source_chunk_id": cr.unit_uid(asset_id, source_fingerprint, "transcript", index),
            "provenance": {"stage": "LOCAL_EVIDENCE_COMPLETE", "engine": "faster_whisper",
                           "language_probability": chunk.get("language_probability")},
        })
    return rows


def visual_embedding_rows(asset_id: str, run_id: str, source_fingerprint: str, *,
                          keyframe_vectors: Sequence[tuple[int, int, list[float]]],
                          scene_pool: Callable[[list[list[float]]], list[float]],
                          asset_vector: Sequence[float] | None = None,
                          asset_metadata: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
    """VISUAL_KEYFRAME per frame, VISUAL_SCENE pooled per scene, VISUAL_ASSET pooled per asset."""
    rows: list[dict[str, Any]] = []
    by_scene: dict[int, list[list[float]]] = {}
    for scene_index, frame_index, vector in keyframe_vectors:
        by_scene.setdefault(scene_index, []).append(list(vector))
        keyframe_id = cr.unit_uid(asset_id, source_fingerprint, "kf", scene_index, frame_index)
        rows.append(cr.visual_embedding_row(
            cr.unit_uid(asset_id, source_fingerprint, "vkf", keyframe_id), run_id, asset_id, vector,
            source_fingerprint, scope="VISUAL_KEYFRAME",
            scene_id=cr.unit_uid(asset_id, source_fingerprint, "scene", scene_index),
            keyframe_id=keyframe_id, metadata={"frame_index": frame_index}))
    scene_vectors: list[list[float]] = []
    for scene_index in sorted(by_scene):
        pooled = scene_pool(by_scene[scene_index])
        scene_vectors.append(pooled)
        rows.append(cr.visual_embedding_row(
            cr.unit_uid(asset_id, source_fingerprint, "vscene", scene_index), run_id, asset_id, pooled,
            source_fingerprint, scope="VISUAL_SCENE",
            scene_id=cr.unit_uid(asset_id, source_fingerprint, "scene", scene_index),
            metadata={"aggregation": "l2_mean_pool_l2_v1", "member_frames": len(by_scene[scene_index])}))
    vector = list(asset_vector) if asset_vector is not None else (
        scene_pool(scene_vectors) if scene_vectors else [])
    if vector:
        rows.append(cr.visual_embedding_row(
            cr.unit_uid(asset_id, source_fingerprint, "vasset"), run_id, asset_id, vector,
            source_fingerprint, scope="VISUAL_ASSET",
            metadata=dict(asset_metadata or {"aggregation": "l2_mean_pool_l2_v1",
                                             "member_scenes": len(scene_vectors)})))
    return rows
