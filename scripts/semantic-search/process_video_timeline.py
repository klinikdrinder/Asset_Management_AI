"""Run kdi_video_timeline_v1 on the eight frozen pilots in shadow mode.

Database usage is SELECT-only. Originals are downloaded read-only to ignored tmp storage,
verified by SHA-256, and never modified. Outputs are local JSON/CSV/SVG/JPEG artifacts.
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
from typing import Any

from dotenv import dotenv_values
from google.oauth2 import service_account
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from PIL import Image, ImageDraw
from supabase import create_client

from kdi_media.video_frames import resolve_ffmpeg_paths
from kdi_media.video_timeline import TimelineConfig, VideoTimelineProcessor, file_sha256, functional_output


ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "config" / "semantic-search" / "kdi_video_timeline_v1.json"
SPEC = ROOT / "config" / "semantic-search" / "kdi_semantic_search_spec_v1.json"
MANIFEST = ROOT / "config" / "semantic-search" / "kdi_semantic_pilot_v1.json"
PHASE2 = ROOT / "reports" / "semantic-search" / "phase2_pilot_layer_audit.json"
OUT = ROOT / "reports" / "semantic-search" / "phase3"
SOURCE_CACHE = ROOT / "tmp" / "phase3_sources"


def environment() -> dict[str, str]:
    values: dict[str, str] = {}
    for path in (ROOT / ".env", ROOT / ".env.local"):
        if path.exists(): values.update({k: v for k, v in dotenv_values(path).items() if v})
    values.update(os.environ)
    return values


def drive_client(env: dict[str, str]):
    cred_path = env.get("GOOGLE_DRIVE_SERVICE_ACCOUNT_CREDENTIALS_PATH") or env.get("GOOGLE_APPLICATION_CREDENTIALS")
    if (not cred_path or not Path(cred_path).is_file()) and (ROOT / ".secrets" / "kdi-media-reader.json").is_file():
        cred_path = str(ROOT / ".secrets" / "kdi-media-reader.json")
    token_path = env.get("GOOGLE_DRIVE_TOKEN_FILE") or env.get("GOOGLE_TOKEN_PATH")
    if cred_path and Path(cred_path).is_file():
        credentials = service_account.Credentials.from_service_account_file(cred_path, scopes=["https://www.googleapis.com/auth/drive.readonly"])
    elif token_path and Path(token_path).is_file():
        credentials = Credentials.from_authorized_user_file(token_path, ["https://www.googleapis.com/auth/drive"])
    else:
        raise RuntimeError("DRIVE_CREDENTIALS_UNAVAILABLE")
    return build("drive", "v3", credentials=credentials, cache_discovery=False)


def download_source(drive, file_id: str, target: Path, expected_hash: str) -> None:
    if target.is_file() and file_sha256(target) == expected_hash:
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_suffix(target.suffix + ".partial")
    request = drive.files().get_media(fileId=file_id, supportsAllDrives=True)
    with partial.open("wb") as stream:
        transfer = MediaIoBaseDownload(stream, request, chunksize=8 * 1024 * 1024)
        done = False
        while not done:
            _, done = transfer.next_chunk(num_retries=3)
    actual = file_sha256(partial)
    if actual != expected_hash:
        partial.unlink(missing_ok=True)
        raise RuntimeError(f"SOURCE_FINGERPRINT_MISMATCH:{target.name}:{actual}")
    partial.replace(target)


def extract_debug(ffmpeg: str, source: Path, result: dict[str, Any], debug_dir: Path) -> dict[str, str]:
    debug_dir.mkdir(parents=True, exist_ok=True)
    candidates = result.get("keyframe_candidates") or []
    if len(candidates) > 12:
        indices = sorted({round(i * (len(candidates) - 1) / 11) for i in range(12)})
        candidates = [candidates[i] for i in indices]
    thumbs = []
    for index, keyframe in enumerate(candidates):
        path = debug_dir / f"frame-{index:02d}.jpg"
        subprocess.run([ffmpeg, "-v", "error", "-ss", f"{keyframe['timestamp']:.6f}", "-i", str(source), "-frames:v", "1", "-vf", "scale=320:180:force_original_aspect_ratio=decrease,pad=320:180:(ow-iw)/2:(oh-ih)/2", "-q:v", "5", "-y", str(path)], check=True, capture_output=True, timeout=60)
        thumbs.append((path, keyframe))
    if thumbs:
        sheet = Image.new("RGB", (960, ((len(thumbs)+2)//3)*220), "white")
        draw = ImageDraw.Draw(sheet)
        for i, (path, keyframe) in enumerate(thumbs):
            with Image.open(path) as image:
                sheet.paste(image.convert("RGB"), ((i%3)*320, (i//3)*220))
            draw.text(((i%3)*320+4, (i//3)*220+183), f"{keyframe['timestamp']:.2f}s {keyframe['selection_reason']}", fill="black")
        contact = debug_dir / "contact-sheet.jpg"
        sheet.save(contact, quality=82)
        for path, _ in thumbs: path.unlink(missing_ok=True)
    else:
        contact = debug_dir / "contact-sheet-unavailable.txt"; contact.write_text("No keyframes", encoding="utf-8")
    signals = (result.get("frame_analysis") or {}).get("signals") or []
    width, height = 1200, 320
    def points(key: str, color: str) -> str:
        if not signals: return ""
        step = max(1, len(signals)//1200)
        sampled = signals[::step]
        return "<polyline fill='none' stroke='%s' stroke-width='1' points='%s'/>" % (color, " ".join(f"{i/(len(sampled)-1 or 1)*width:.1f},{height-20-x[key]*(height-40):.1f}" for i,x in enumerate(sampled)))
    svg = f"<svg xmlns='http://www.w3.org/2000/svg' width='{width}' height='{height}'><rect width='100%' height='100%' fill='white'/>{points('visual_change_score','#d33')}{points('motion_score','#36c')}{points('composition_change_score','#2a5')}<text x='10' y='18'>red=change blue=motion green=composition</text></svg>"
    plot = debug_dir / "timeline-signals.svg"; plot.write_text(svg, encoding="utf-8")
    return {"contact_sheet": str(contact.relative_to(ROOT)), "timeline_plot": str(plot.relative_to(ROOT))}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify-idempotency", action="store_true")
    args = parser.parse_args()
    spec = json.loads(SPEC.read_text(encoding="utf-8")); manifest = json.loads(MANIFEST.read_text(encoding="utf-8")); phase2 = json.loads(PHASE2.read_text(encoding="utf-8"))
    if spec["specification"]["status"] != "LOCKED" or spec["specification"]["specification_fingerprint"] != "ea74ef9c07f8341342817bc924d78fb6ae28049a8a29b6c571172a77c923308c": raise RuntimeError("LOCKED_SPEC_MISMATCH")
    videos = [x for x in manifest["assets"] if x["media_type"] == "video"]
    if len(manifest["assets"]) != 10 or len(videos) != 8 or sum(x["media_type"] == "image" for x in manifest["assets"]) != 2: raise RuntimeError("PILOT_COMPOSITION_MISMATCH")
    if phase2.get("evaluation_count") != 180: raise RuntimeError("PHASE2_AUDIT_MISSING")
    env = environment(); db = create_client(env["SUPABASE_URL"], env["SUPABASE_SERVICE_ROLE_KEY"]); drive = drive_client(env)
    ffmpeg, ffprobe = resolve_ffmpeg_paths(project_root=ROOT); config = TimelineConfig.load(CONFIG); processor = VideoTimelineProcessor(config, ffmpeg_path=ffmpeg, ffprobe_path=ffprobe)
    OUT.mkdir(parents=True, exist_ok=True); SOURCE_CACHE.mkdir(parents=True, exist_ok=True)
    results = []
    for item in videos:
        aid, filename = item["asset_id"], item["filename"]
        asset = db.table("assets").select("id,file_name,mime_type,checksum_sha256,content_hash").eq("id", aid).single().execute().data
        if asset["file_name"] != filename or not str(asset.get("mime_type") or "").startswith("video/"): raise RuntimeError(f"PILOT_IDENTITY_MISMATCH:{aid}")
        access = db.table("asset_access_control").select("external_ai_status").eq("asset_id", aid).single().execute().data
        if access.get("external_ai_status") != "ALLOWED": raise RuntimeError(f"PILOT_AUTHORIZATION_MISMATCH:{aid}")
        destinations = db.table("asset_destinations").select("destination_google_file_id,upload_status").eq("asset_id", aid).eq("upload_status", "VERIFIED").limit(1).execute().data
        if not destinations: raise RuntimeError(f"VERIFIED_SOURCE_MISSING:{aid}")
        expected_hash = item["content_fingerprint"]["value"]
        source = SOURCE_CACHE / aid / filename
        download_source(drive, destinations[0]["destination_google_file_id"], source, expected_hash)
        result = processor.process(source, asset_id=aid, filename=filename, source_fingerprint=expected_hash, semantic_spec_version="semantic_index_v1", semantic_spec_fingerprint=spec["specification"]["specification_fingerprint"], pilot_manifest_version=manifest["manifest_version"])
        if result["status"] not in {"COMPLETED", "PARTIAL"}: raise RuntimeError(f"TIMELINE_FAILED:{filename}:{result.get('failure')}")
        first_hash = hashlib.sha256(json.dumps(functional_output(result), sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        idempotency = {"verified": False, "functional_fingerprint": first_hash}
        if args.verify_idempotency:
            repeated = processor.process(source, asset_id=aid, filename=filename, source_fingerprint=expected_hash, semantic_spec_version="semantic_index_v1", semantic_spec_fingerprint=spec["specification"]["specification_fingerprint"], pilot_manifest_version=manifest["manifest_version"])
            second_hash = hashlib.sha256(json.dumps(functional_output(repeated), sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            idempotency = {"verified": first_hash == second_hash, "functional_fingerprint": first_hash, "repeat_fingerprint": second_hash}
            if not idempotency["verified"]: raise RuntimeError(f"IDEMPOTENCY_FAILURE:{filename}")
        result["idempotency"] = idempotency
        result["debug_artifacts"] = extract_debug(ffmpeg, source, result, OUT / "debug" / aid)
        review_warnings = set(result["warnings"])
        review = "REVIEW_NEEDED" if {"POSSIBLE_UNDER_SEGMENTATION", "OVER_SEGMENTATION_SCENE_RATE", "EVENT_COUNT_EXPLOSION", "KEYFRAME_COUNT_EXPLOSION"} & review_warnings else "PASS"
        result["timeline_quality_review"] = {"start_covered": result["scene_candidates"][0]["start_frame"] == 0, "end_covered": result["scene_candidates"][-1]["end_frame"] == result["frame_analysis"]["frames_processed"] - 1, "major_transitions_represented": len(result["boundaries"]) > 0 or result["quality_metrics"]["change_spike_count"] == 0, "short_change_coverage": len(result["event_candidates"]) > 0 or result["quality_metrics"]["change_spike_count"] == 0, "boundary_explosion": "OVER_SEGMENTATION_SCENE_RATE" in review_warnings, "undersegmentation_warning": "POSSIBLE_UNDER_SEGMENTATION" in review_warnings, "overall": review}
        result["frame_analysis"]["signals_summary"] = {key: {"min": min(x[key] for x in result["frame_analysis"]["signals"]), "max": max(x[key] for x in result["frame_analysis"]["signals"]), "mean": sum(x[key] for x in result["frame_analysis"]["signals"])/len(result["frame_analysis"]["signals"])} for key in ("visual_change_score","motion_score","histogram_change_score","composition_change_score","brightness","edge_texture_score")}
        (OUT / f"{aid}_timeline.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        results.append(result)
    probe_summary = {"processor_version": config["processor_version"], "configuration_version": config["configuration_version"], "configuration_fingerprint": config.fingerprint, "videos": [{"asset_id": r["asset_id"], "filename": r["filename"], "source_fingerprint": r["source_fingerprint"], **r["technical_metadata"]} for r in results]}
    (OUT / "video_probe_summary.json").write_text(json.dumps(probe_summary, indent=2) + "\n", encoding="utf-8")
    summary = {"generated_at": datetime.now(timezone.utc).isoformat(), "processor_version": config["processor_version"], "configuration_version": config["configuration_version"], "configuration_fingerprint": config.fingerprint, "semantic_spec_version": "semantic_index_v1", "pilot_manifest_version": manifest["manifest_version"], "video_count": len(results), "completed": sum(r["status"] == "COMPLETED" for r in results), "idempotency_verified": sum(r["idempotency"]["verified"] for r in results), "totals": {"frames_processed": sum(r["frame_analysis"]["frames_processed"] for r in results), "scenes": sum(len(r["scene_candidates"]) for r in results), "events": sum(len(r["event_candidates"]) for r in results), "keyframes": sum(len(r["keyframe_candidates"]) for r in results), "redundant_removed": sum(r["redundant_keyframes_removed"] for r in results), "wall_clock_seconds": sum(r["performance"]["wall_clock_seconds"] for r in results)}, "videos": [{"asset_id": r["asset_id"], "filename": r["filename"], "status": r["status"], "duration_seconds": r["technical_metadata"]["duration_seconds"], "expected_frames": r["technical_metadata"]["frame_count"], "frames_processed": r["frame_analysis"]["frames_processed"], "coverage_percent": r["frame_analysis"]["timeline_coverage_percent"], "scene_candidates": len(r["scene_candidates"]), "hard_boundaries": sum(x["boundary_type"] == "HARD_CUT" for x in r["boundaries"]), "soft_boundaries": sum(x["boundary_type"] == "SOFT_TRANSITION" for x in r["boundaries"]), "event_candidates": len(r["event_candidates"]), "keyframes": len(r["keyframe_candidates"]), "redundant_removed": r["redundant_keyframes_removed"], "warnings": r["warnings"], "timeline_review": r["timeline_quality_review"]["overall"], "performance": r["performance"]} for r in results]}
    (OUT / "video_timeline_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    with (OUT / "video_timeline_comparison.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle); writer.writerow(["asset_id","filename","old_production_scenes","new_shadow_scenes","old_production_keyframes","new_shadow_keyframes","new_event_candidates"])
        for r in results: writer.writerow([r["asset_id"],r["filename"],1,len(r["scene_candidates"]),1,len(r["keyframe_candidates"]),len(r["event_candidates"])])
    print(json.dumps({"status":"PASS","videos":len(results),"frames":summary["totals"]["frames_processed"],"scenes":summary["totals"]["scenes"],"events":summary["totals"]["events"],"keyframes":summary["totals"]["keyframes"],"config_fingerprint":config.fingerprint}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
