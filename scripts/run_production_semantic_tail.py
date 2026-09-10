"""Completion stages of the existing production semantic rollout worker.

`run_production_semantic_rollout.py` prepares local evidence for the frozen #31-#130 manifest and
checkpoints each asset at WAITING_EXTERNAL_AI_APPROVAL. This module finishes that same pipeline.

    transcript  local faster-whisper over audio-bearing videos, written into the checkpoint
    semantic    Claude over real scene keyframes -> canonical persistence -> embeddings -> publish

Two stages because CTranslate2 (faster-whisper) and PyTorch (OpenCLIP, E5) cannot share a process.
Both stages are resumable and idempotent: every write is keyed by a deterministic uuid5 over the
analysis run, so a repeat converges on the same rows.

Scope is fixed by the frozen manifest. Assets #1-#30 are immutable and #131+ are never touched.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
OUT = ROOT / "reports/semantic-search/rollout/100"
CHECKPOINT = OUT / "production-rollout-local-checkpoint.json"
SEMANTIC_CHECKPOINT = OUT / "production-rollout-semantic-checkpoint.json"
COHORT_MANIFEST = OUT / "production-semantic-cohort-34-130.json"
FF = str(ROOT / ".tools/ffmpeg/bin/ffmpeg.exe")
FP = str(ROOT / ".tools/ffmpeg/bin/ffprobe.exe")
RUN_NAMESPACE = uuid.UUID("0f2c6d84-9b37-4c1e-8a55-71d0e6b4f3a2")


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_environment() -> None:
    load_dotenv(ROOT / ".env")
    load_dotenv(ROOT / ".env.local", override=False)


def read_checkpoint(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"assets": []}


def write_checkpoint(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")


def load_cohort_manifest(start: int, end: int) -> dict[int, dict[str, Any]]:
    if start != 34 or end != 130:
        raise RuntimeError("PRODUCTION_SCOPE_MUST_BE_ORDINALS_34_130")
    payload = json.loads(COHORT_MANIFEST.read_text(encoding="utf-8"))
    assets = payload.get("assets", [])
    ordinals = [int(x["ordinal"]) for x in assets]
    if len(assets) != 97 or ordinals != list(range(start, end + 1)):
        raise RuntimeError("FROZEN_COHORT_SCOPE_INVALID")
    if len({x["asset_id"] for x in assets}) != 97:
        raise RuntimeError("FROZEN_COHORT_DUPLICATE_ASSET_IDS")
    return {int(x["ordinal"]): x for x in assets}


def local_records(start: int, end: int, cohort: Mapping[int, Mapping[str, Any]]) -> list[dict[str, Any]]:
    data = read_checkpoint(CHECKPOINT)
    records = [x for x in data.get("assets", [])
               if x.get("checkpoint") == "WAITING_EXTERNAL_AI_APPROVAL"
               and int(x["ordinal"]) in cohort]
    for record in records:
        ordinal = int(record["ordinal"])
        if not (start <= ordinal <= end) or ordinal not in cohort:
            raise RuntimeError(f"OUT_OF_SCOPE_ASSET:{record['ordinal']}")
        if record["asset_id"] != cohort[ordinal]["asset_id"]:
            raise RuntimeError(f"COHORT_ASSET_ID_MISMATCH:{ordinal}")
    return sorted(records, key=lambda x: x["ordinal"])


# ------------------------------------------------------------------ transcript
def transcript_stage(limit: int | None, start: int, end: int) -> int:
    """Local speech evaluation. No audio ever leaves the machine."""
    from faster_whisper import WhisperModel

    cohort = load_cohort_manifest(start, end)
    records = local_records(start, end, cohort)
    pending = [x for x in records if x.get("transcript_state") in {None, "PENDING_SEMANTIC_PIPELINE"}]
    if limit:
        pending = pending[:limit]
    if not pending:
        print(json.dumps({"stage": "transcript", "pending": 0}))
        return 0
    snapshots = sorted((Path.home() / ".cache/huggingface/hub/models--Systran--faster-whisper-small/snapshots").glob("*"))
    if not snapshots:
        raise RuntimeError("LOCAL_WHISPER_MODEL_MISSING")
    model = WhisperModel(str(snapshots[-1]), device="cpu", compute_type="int8", local_files_only=True)
    processed = 0
    for record in pending:
        work = OUT / "local-work" / record["asset_id"]
        media = work / record["filename"]
        if not record.get("audio_stream"):
            record["transcript_state"] = "NOT_APPLICABLE"
            record["transcript_chunks"] = []
        elif not media.is_file():
            record["transcript_state"] = "UNKNOWN_MEDIA_NOT_RETAINED"
            record["transcript_chunks"] = []
        else:
            wav = work / "audio.wav"
            subprocess.run([FF, "-v", "error", "-i", str(media), "-vn", "-ac", "1", "-ar", "16000",
                            "-c:a", "pcm_s16le", "-y", str(wav)], capture_output=True, timeout=180)
            segments, info = model.transcribe(str(wav), beam_size=5, word_timestamps=True,
                                              vad_filter=True, temperature=0,
                                              condition_on_previous_text=False)
            chunks = []
            for segment in segments:
                probabilities = [float(w.probability) for w in (segment.words or [])
                                 if isinstance(w.probability, (int, float))]
                confidence = (round(sum(probabilities) / len(probabilities), 3) if probabilities else
                              (round(max(0.0, min(1.0, math.exp(float(segment.avg_logprob)))), 3)
                               if isinstance(segment.avg_logprob, (int, float)) else None))
                text = " ".join(str(segment.text or "").split())
                if not text:
                    continue
                chunks.append({"start": round(float(segment.start), 3), "end": round(float(segment.end), 3),
                               "text": text, "confidence": confidence,
                               "language": info.language, "language_probability": round(float(info.language_probability), 3)})
            # The Phase 11 meaningfulness gate: a chime or a single decoded token is not speech.
            meaningful = [c for c in chunks
                          if (c["confidence"] or 0) >= 0.6 and len(c["text"].split()) >= 2
                          and (c["end"] - c["start"]) >= 0.6
                          and (c["language_probability"] or 0) >= 0.7]
            record["transcript_chunks"] = meaningful
            record["transcript_rejected"] = len(chunks) - len(meaningful)
            record["transcript_state"] = ("MEANINGFUL_SPEECH" if meaningful else
                                          "NO_MEANINGFUL_SPEECH" if chunks else "NO_SPEECH")
            wav.unlink(missing_ok=True)
        processed += 1
        write_checkpoint(CHECKPOINT, data)
        print(json.dumps({"ordinal": record["ordinal"], "transcript_state": record["transcript_state"],
                          "chunks": len(record.get("transcript_chunks", []))}), flush=True)
    return processed


# ------------------------------------------------------------------ semantic
def build_evidence(record: dict[str, Any]):
    """Reconstructs the local evidence object from the checkpoint, no re-processing."""
    from kdi_media.production_indexer import SceneEvidence, VideoEvidence

    by_scene: dict[int, list[str]] = {}
    for frame in record.get("keyframes", []):
        by_scene.setdefault(int(frame["scene_index"]), []).append(str(frame["path"]))
    transcripts: dict[int, list[str]] = {}
    for chunk in record.get("transcript_chunks", []):
        for scene in record.get("scenes", []):
            if scene["start_seconds"] - 1e-6 <= chunk["start"] and chunk["end"] <= scene["end_seconds"] + 1e-6:
                transcripts.setdefault(int(scene["scene_index"]), []).append(chunk["text"])
                break
    scenes = [SceneEvidence(scene_index=int(s["scene_index"]),
                            start_seconds=float(s["start_seconds"]),
                            end_seconds=float(s["end_seconds"]),
                            keyframe_paths=by_scene.get(int(s["scene_index"]), []),
                            ocr_texts=list(record.get("ocr_texts", {}).get(str(s["scene_index"]), [])),
                            transcript_texts=transcripts.get(int(s["scene_index"]), []))
              for s in record.get("scenes", [])]
    return VideoEvidence(asset_id=record["asset_id"], filename=record["filename"],
                         technical=record.get("technical_probe", {}), scenes=scenes,
                         audio_stream=bool(record.get("audio_stream")),
                         audio_state="AUDIO_PRESENT" if record.get("audio_stream") else "NO_AUDIO",
                         transcript_state=str(record.get("transcript_state", "UNKNOWN")),
                         ocr_evaluated=bool(record.get("ocr_evaluated")),
                         ocr_observations=int(record.get("ocr_observations", 0)))


def semantic_stage(limit: int | None, dry_run: bool, start: int, end: int) -> dict[str, Any]:
    from supabase import create_client
    from kdi_media.claude_provider import ClaudeSemanticProvider
    from kdi_media.production_indexer import ProductionSemanticIndexer
    from kdi_media.supabase_production_adapter import CanonicalSemanticPersistenceAdapter, ManifestScope

    cohort = load_cohort_manifest(start, end)
    manifest_ids = frozenset(x["asset_id"] for x in cohort.values())

    client = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])
    certified = client.table("asset_semantic_layers").select("asset_id").eq("active", True).execute().data or []
    counts: dict[str, int] = {}
    for row in certified:
        counts[row["asset_id"]] = counts.get(row["asset_id"], 0) + 1
    locked = frozenset(k for k, v in counts.items() if v == 18) - manifest_ids
    scope = ManifestScope(asset_ids=manifest_ids, locked_asset_ids=locked)

    from sentence_transformers import SentenceTransformer
    sys.path.insert(0, str(ROOT / "dashboard"))
    from visual_indexing.openclip_encoder import OpenClipEncoder
    from PIL import Image

    e5_snapshots = sorted((Path.home() / ".cache/huggingface/hub/models--intfloat--multilingual-e5-small/snapshots").glob("*"))
    e5 = SentenceTransformer(str(e5_snapshots[-1]), local_files_only=True)
    clip = OpenClipEncoder()

    def embed_text(text: str) -> list[float]:
        return [float(x) for x in e5.encode(text, normalize_embeddings=True)]

    def embed_image(path: str) -> list[float]:
        with Image.open(path) as image:
            return [float(x) for x in clip.embed_image(image)]

    adapter = CanonicalSemanticPersistenceAdapter(client, scope, text_embedder=embed_text,
                                                  visual_embedder=embed_image)
    provider = ClaudeSemanticProvider()
    indexer = ProductionSemanticIndexer(adapter, provider)

    state = read_checkpoint(SEMANTIC_CHECKPOINT)
    live_ready = client.table("kdi_search_ready_assets_v1").select("asset_id").in_(
        "asset_id", list(manifest_ids)
    ).eq("search_ready", True).execute().data or []
    done = {x["asset_id"] for x in live_ready}
    records = [x for x in local_records(start, end, cohort) if x["asset_id"] not in done]
    if limit:
        records = records[:limit]

    results = list(state.get("assets", []))
    for record in records:
        asset_id = record["asset_id"]
        evidence = build_evidence(record)
        adapter.evidence_source = lambda _aid, _e=evidence: _e
        run_id = str(uuid.uuid5(RUN_NAMESPACE, f"{asset_id}:{record['checksum']}:kdi_production_indexer_v1"))
        started = time.perf_counter()
        if dry_run:
            results = [x for x in results if x.get("asset_id") != asset_id]
            results.append({"asset_id": asset_id, "ordinal": record["ordinal"], "status": "DRY_RUN",
                            "canonical_scenes": len(evidence.scenes),
                            "canonical_keyframes": evidence.keyframe_count,
                            "keyframes_to_transmit": len(evidence.asset_frames()) + evidence.keyframe_count})
            print(json.dumps(results[-1]), flush=True)
            continue
        adapter.begin_run({"id": run_id, "asset_id": asset_id, "run_type": "PRODUCTION_SEMANTIC_INDEXING",
                           "status": "RUNNING", "semantic_spec_version": "semantic_index_v1",
                           "ontology_version": "KDI_SEMANTIC_V2",
                           "processor_version": "kdi_production_indexer_v1",
                           "configuration_fingerprint": run_id, "source_fingerprint": record["checksum"],
                           "provider": "claude", "model": os.getenv("KDI_CLAUDE_MODEL", ""),
                           "metadata": {"ordinal": record["ordinal"], "scenes": len(evidence.scenes),
                                        "keyframes": evidence.keyframe_count}})
        outcome = indexer.index_asset_fully(asset_id)
        outcome.update({"ordinal": record["ordinal"], "filename": record["filename"],
                        "analysis_run_id": run_id, "elapsed_seconds": round(time.perf_counter() - started, 2),
                        "staged": adapter.last_build.get(asset_id, {}),
                        "claude_requests": len([u for u in provider.usage if u["asset_id"] == asset_id])})
        results = [x for x in results if x.get("asset_id") != asset_id]
        results.append(outcome)
        write_checkpoint(SEMANTIC_CHECKPOINT, {"status": "RUNNING", "updated_at": now(), "assets": results})
        print(json.dumps({k: outcome.get(k) for k in ("ordinal", "filename", "status", "code",
                                                      "canonical_scenes", "canonical_keyframes",
                                                      "claude_requests", "elapsed_seconds")}), flush=True)

    ready = sum(1 for x in results if x.get("status") == "SEARCH_READY")
    payload = {"status": "PASS" if ready == 100 else "INCOMPLETE", "search_ready": ready,
               "processed": len(results), "completed_at": now(),
               "external_ai_calls": len(provider.usage), "assets": sorted(results, key=lambda x: x.get("ordinal", 0))}
    write_checkpoint(SEMANTIC_CHECKPOINT, payload)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", choices=["transcript", "semantic"], required=True)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--ordinal-start", type=int, default=34)
    parser.add_argument("--ordinal-end", type=int, default=130)
    parser.add_argument("--dry-run", action="store_true",
                        help="semantic stage only: report what would be transmitted, call nothing")
    args = parser.parse_args()
    load_environment()
    if args.stage == "transcript":
        processed = transcript_stage(args.limit, args.ordinal_start, args.ordinal_end)
        print(json.dumps({"stage": "transcript", "processed": processed}))
    else:
        print(json.dumps({k: v for k, v in semantic_stage(
            args.limit, args.dry_run, args.ordinal_start, args.ordinal_end
        ).items() if k != "assets"}))


if __name__ == "__main__":
    main()
