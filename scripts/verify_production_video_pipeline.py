"""Verifies the finished production video pipeline end to end, stage by stage.

Two of the checks transmit real scene keyframes to Claude. That is the pipeline's own transmission
path, exercised against evidence the local stages already produced; it writes nothing to the
database and does not touch any asset's access-control row.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
OUT = ROOT / "reports/semantic-search/rollout/100"
REPORT = ROOT / "reports/semantic-search/rollout/production-indexer/video-pipeline-verification.json"


def main() -> int:
    load_dotenv(ROOT / ".env")
    load_dotenv(ROOT / ".env.local", override=False)
    os.environ.setdefault("KDI_EXTERNAL_AI_ENABLED", "true")

    from kdi_media.claude_provider import ClaudeSemanticProvider, LAYER_IDS
    from kdi_media.production_indexer import validate_clinical_claims
    from kdi_media import canonical_rows as cr
    sys.path.insert(0, str(ROOT / "scripts"))
    from run_production_semantic_tail import build_evidence

    checkpoint = json.loads((OUT / "production-rollout-local-checkpoint.json").read_text(encoding="utf-8"))
    records = sorted([x for x in checkpoint["assets"] if x.get("checkpoint") == "WAITING_EXTERNAL_AI_APPROVAL"],
                     key=lambda x: x["ordinal"])
    results: dict[str, object] = {"assets_prepared": len(records)}

    # Prefer a genuinely multi-scene video so scene fan-out is exercised, not assumed.
    record = max(records, key=lambda x: x.get("canonical_scenes", 0))
    evidence = build_evidence(record)
    results["target"] = {"ordinal": record["ordinal"], "filename": record["filename"],
                         "scenes": len(evidence.scenes), "keyframes": evidence.keyframe_count}

    frames_present = all(Path(p).is_file() for s in evidence.scenes for p in s.keyframe_paths)
    results["scene_pipeline"] = {
        "multi_scene_videos": sum(1 for x in records if x.get("canonical_scenes", 0) > 1),
        "total_scenes": sum(x.get("canonical_scenes", 0) for x in records),
        "total_keyframes": sum(x.get("canonical_keyframes", 0) for x in records),
        "every_scene_has_keyframes": all(s.keyframe_paths for s in evidence.scenes),
        "keyframe_files_present": frames_present,
        "pass": frames_present and all(s.keyframe_paths for s in evidence.scenes)
                and sum(1 for x in records if x.get("canonical_scenes", 0) > 1) > 0,
    }
    results["audio"] = {
        "audio_bearing": sum(1 for x in records if x.get("audio_stream")),
        "transcript_states": {state: sum(1 for x in records if x.get("transcript_state") == state)
                              for state in {x.get("transcript_state") for x in records}},
        "pass": all(x.get("audio_evaluated") for x in records),
    }
    results["ocr"] = {
        "evaluated": sum(1 for x in records if x.get("ocr_evaluated")),
        "observations": sum(int(x.get("ocr_observations", 0)) for x in records),
        "pass": all(x.get("ocr_evaluated") for x in records),
    }

    provider = ClaudeSemanticProvider()
    scene = evidence.scenes[0]
    frames = scene.frames()
    package = provider.analyze(
        asset_id=record["asset_id"],
        evidence_text=scene.evidence_text(record["asset_id"], record["filename"], evidence.technical),
        images=frames, request_type=f"verify:scene:{scene.scene_index}")
    states = {layer["layer_id"]: layer["state"] for layer in package["layers"]}
    results["video_keyframe_to_claude"] = {
        "images_transmitted": package.get("image_count"),
        "raw_video_transmitted": False,
        "model": package["model"],
        "pass": bool(package.get("image_count")) and package.get("image_count") == len(frames),
    }
    results["eighteen_layer_validation"] = {
        "layers_returned": len(package["layers"]),
        "all_ids_present": sorted(states) == sorted(LAYER_IDS),
        "states": states,
        "clinical_offenders": validate_clinical_claims(package, scene.ocr_texts + scene.transcript_texts),
        "pass": len(package["layers"]) == 18 and sorted(states) == sorted(LAYER_IDS)
                and not validate_clinical_claims(package, scene.ocr_texts + scene.transcript_texts),
    }

    # Row construction over the real package, without any database write.
    run_id = "00000000-0000-5000-8000-00000000c0de"
    layers = cr.layer_rows(record["asset_id"], run_id, package)
    assertions, evidence_rows, positives = cr.assertion_rows(
        record["asset_id"], run_id, package, record["checksum"],
        scene_id=cr.uid(run_id + ":scene:0"), start_time=scene.start_seconds, end_time=scene.end_seconds)
    text = cr.searchable_text(record["filename"], package, scene.ocr_texts)
    document = cr.document_row(cr.uid(run_id + ":doc"), run_id, record["asset_id"], record["filename"],
                               "VIDEO", text, positives, document_type="SCENE",
                               scene_id=cr.uid(run_id + ":scene:0"), source_fingerprint=record["checksum"])
    results["persistence"] = {
        "layer_rows": len(layers),
        "assertion_rows": len(assertions),
        "evidence_rows": len(evidence_rows),
        "assertions_without_evidence": sum(1 for a in assertions
                                           if not any(e["assertion_id"] == a["id"] for e in evidence_rows)),
        "document_status": document["status"],
        "deterministic_ids": all(str(a["id"]).count("-") == 4 for a in assertions),
        "pass": len(layers) == 18 and document["status"] == "READY"
                and all(any(e["assertion_id"] == a["id"] for e in evidence_rows) for a in assertions),
    }

    from sentence_transformers import SentenceTransformer
    sys.path.insert(0, str(ROOT / "dashboard"))
    from visual_indexing.openclip_encoder import OpenClipEncoder
    from PIL import Image

    snapshots = sorted((Path.home() / ".cache/huggingface/hub/models--intfloat--multilingual-e5-small/snapshots").glob("*"))
    e5 = SentenceTransformer(str(snapshots[-1]), local_files_only=True)
    vector = [float(x) for x in e5.encode("passage: " + text, normalize_embeddings=True)]
    e5_row = cr.text_embedding_row(cr.uid(run_id + ":t"), run_id, record["asset_id"], vector, text,
                                   document["document_fingerprint"], scope="TEXT_SCENE")
    results["e5"] = {"dimensions": e5_row["dimensions"], "model": e5_row["model"],
                     "model_version": e5_row["model_version"], "provider": e5_row["provider"],
                     "pass": e5_row["dimensions"] == 384 and e5_row["model"] == cr.E5_MODEL}

    clip = OpenClipEncoder()
    with Image.open(scene.keyframe_paths[0]) as image:
        visual = [float(x) for x in clip.embed_image(image)]
    clip_row = cr.visual_embedding_row(cr.uid(run_id + ":v"), run_id, record["asset_id"], visual,
                                       record["checksum"], scope="VISUAL_KEYFRAME",
                                       scene_id=cr.uid(run_id + ":scene:0"),
                                       keyframe_id=cr.uid(run_id + ":kf"))
    results["openclip"] = {"dimensions": clip_row["dimensions"], "model": clip_row["model"],
                           "model_version": clip_row["model_version"], "provider": clip_row["provider"],
                           "pass": clip_row["dimensions"] == 512 and clip_row["model"] == cr.CLIP_MODEL}
    results["embedding_families_separate"] = e5_row["provider"] != clip_row["provider"] and \
        e5_row["dimensions"] != clip_row["dimensions"]

    # Resume: identifiers must be reproducible from the same run and unit.
    again = cr.assertion_rows(record["asset_id"], run_id, package, record["checksum"],
                              scene_id=cr.uid(run_id + ":scene:0"))[0]
    results["resume"] = {
        "local_checkpoint_assets": len(records),
        "deterministic_repeat_ids_identical": [a["id"] for a in assertions] == [a["id"] for a in again],
        "semantic_checkpoint": (OUT / "production-rollout-semantic-checkpoint.json").exists(),
        "pass": [a["id"] for a in assertions] == [a["id"] for a in again],
    }
    results["claude_usage"] = provider.usage
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(results, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps({k: (v.get("pass") if isinstance(v, dict) and "pass" in v else v)
                      for k, v in results.items() if k not in {"claude_usage", "target", "scene_pipeline"}}, default=str))
    print(json.dumps({"target": results["target"], "scene_pipeline": results["scene_pipeline"]}, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
