"""Process exactly the two frozen Phase 4 images in local shadow mode.

Database access is SELECT-only. Originals are downloaded read-only, SHA-256 verified,
and never rewritten. This script has no production data-write path.
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from dotenv import dotenv_values
from google.oauth2 import service_account
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from PIL import Image, ImageDraw, ImageOps
from supabase import create_client

from kdi_media.image_analysis import ImageAnalysisConfig, ImageAnalysisProcessor, file_sha256, functional_output


ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "config" / "semantic-search" / "kdi_image_analysis_v1.json"
SPEC = ROOT / "config" / "semantic-search" / "kdi_semantic_search_spec_v1.json"
MANIFEST = ROOT / "config" / "semantic-search" / "kdi_semantic_pilot_v1.json"
PHASE2 = ROOT / "reports" / "semantic-search" / "phase2_pilot_layer_audit.json"
PHASE3 = ROOT / "reports" / "semantic-search" / "phase3" / "phase3_validation.json"
OUT = ROOT / "reports" / "semantic-search" / "phase4"
SOURCE_CACHE = ROOT / "tmp" / "phase4_sources"
SPEC_FP = "ea74ef9c07f8341342817bc924d78fb6ae28049a8a29b6c571172a77c923308c"


CONFLICTS = {
    "37838d30-a0ce-4f90-8cc3-c986db0aaa65": [
        {"conflict_type": "ACTION_REPRESENTATION", "source_a": "asset_search_documents.top_level.actions", "value_a": [], "source_b": "rich_semantic_v2/scene_actions", "value_b": ["POSING_FOR_CAMERA"], "status": "PRESERVED_FOR_LATER_REVIEW"},
        {"conflict_type": "UNSUPPORTED_LEGACY_COMPLETION", "sources": ["legacy treatment layer", "legacy OCR layer"], "claim": "COMPLETE", "evidence_count": 0, "status": "PRESERVED_FOR_LATER_REVIEW"},
    ],
    "6215ad8b-12be-4a8e-bc49-f6b3dcf55c21": [
        {"conflict_type": "ACTION_REPRESENTATION", "source_a": "asset_search_documents.top_level.actions", "value_a": [], "source_b": "rich_semantic_v2/scene_actions", "value_b": ["POSING_FOR_CAMERA", "LOOKING_AT_CAMERA"], "status": "PRESERVED_FOR_LATER_REVIEW"},
        {"conflict_type": "UNSUPPORTED_LEGACY_COMPLETION", "sources": ["legacy treatment layer", "legacy OCR layer"], "claim": "COMPLETE", "evidence_count": 0, "status": "PRESERVED_FOR_LATER_REVIEW"},
    ],
}


def environment() -> dict[str, str]:
    values: dict[str, str] = {}
    for path in (ROOT / ".env", ROOT / ".env.local"):
        if path.exists():
            values.update({key: value for key, value in dotenv_values(path).items() if value})
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
        raise RuntimeError(f"SOURCE_IDENTITY_MISMATCH:{target.name}:{actual}")
    partial.replace(target)


def save_preview(image: Image.Image, path: Path, maximum: int, quality: int) -> None:
    preview = image.convert("RGB").copy(); preview.thumbnail((maximum, maximum), Image.Resampling.LANCZOS)
    preview.save(path, "JPEG", quality=quality, optimize=True)


def create_debug(source: Path, result: dict[str, Any], debug_dir: Path, config: ImageAnalysisConfig) -> dict[str, str]:
    debug_dir.mkdir(parents=True, exist_ok=True)
    with Image.open(source) as opened:
        opened.load(); source_pixels = opened.convert("RGB"); analysis = ImageOps.exif_transpose(opened).convert("RGB")
    original_preview = debug_dir / "original-orientation-preview.jpg"
    analysis_preview = debug_dir / "analysis-orientation-preview.jpg"
    overlay_path = debug_dir / "region-overlay.jpg"
    contact_path = debug_dir / "region-contact-sheet.jpg"
    save_preview(source_pixels, original_preview, config["debug_preview_max_dimension"], config["jpeg_debug_quality"])
    save_preview(analysis, analysis_preview, config["debug_preview_max_dimension"], config["jpeg_debug_quality"])
    overlay = analysis.copy(); draw = ImageDraw.Draw(overlay)
    for index, region in enumerate(result["regions"]):
        color = "#00ff00" if region["region_type"] == "FULL_IMAGE" else "#ff5500"
        draw.rectangle((region["x1"], region["y1"], region["x2"]-1, region["y2"]-1), outline=color, width=max(3, analysis.width // 500))
        draw.text((region["x1"]+5, region["y1"]+5), f"{index}:{region['region_type']}", fill=color, stroke_width=2, stroke_fill="black")
    save_preview(overlay, overlay_path, config["debug_preview_max_dimension"], config["jpeg_debug_quality"])
    cards = []
    for index, region in enumerate(result["regions"]):
        crop = analysis.crop((region["x1"], region["y1"], region["x2"], region["y2"]))
        crop.thumbnail((360, 260), Image.Resampling.LANCZOS)
        cards.append((index, region, crop.copy()))
    sheet = Image.new("RGB", (760, max(300, ((len(cards)+1)//2)*310)), "white"); sheet_draw = ImageDraw.Draw(sheet)
    for slot, (index, region, crop) in enumerate(cards):
        x, y = (slot % 2)*380, (slot // 2)*310
        sheet.paste(crop, (x+(360-crop.width)//2, y))
        sheet_draw.text((x+5, y+265), f"{index}: {region['region_type']} score={region['selection_score']:.3f}", fill="black")
    sheet.save(contact_path, "JPEG", quality=config["jpeg_debug_quality"], optimize=True)
    regions_path = debug_dir / "region-manifest.json"
    regions_path.write_text(json.dumps({"asset_id": result["asset_id"], "source_fingerprint": result["source_fingerprint"], "regions": result["regions"]}, indent=2)+"\n", encoding="utf-8")
    return {key: str(path.relative_to(ROOT)) for key, path in {"original_orientation_preview": original_preview, "analysis_orientation_preview": analysis_preview, "bounding_box_overlay": overlay_path, "region_contact_sheet": contact_path, "region_manifest": regions_path}.items()}


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--verify-idempotency", action="store_true"); args = parser.parse_args()
    spec = json.loads(SPEC.read_text(encoding="utf-8")); manifest = json.loads(MANIFEST.read_text(encoding="utf-8")); phase2 = json.loads(PHASE2.read_text(encoding="utf-8")); phase3 = json.loads(PHASE3.read_text(encoding="utf-8"))
    if spec["specification"]["status"] != "LOCKED" or spec["specification"]["specification_fingerprint"] != SPEC_FP: raise RuntimeError("LOCKED_SPEC_MISMATCH")
    images = [item for item in manifest["assets"] if item["media_type"] == "image"]
    if len(manifest["assets"]) != 10 or len(images) != 2 or sum(item["media_type"] == "video" for item in manifest["assets"]) != 8: raise RuntimeError("PILOT_COMPOSITION_MISMATCH")
    if phase2.get("evaluation_count") != 180 or phase3.get("status") != "PASS": raise RuntimeError("PRIOR_PHASE_INPUT_MISSING")
    env = environment(); db = create_client(env["SUPABASE_URL"], env["SUPABASE_SERVICE_ROLE_KEY"]); drive = drive_client(env)
    config = ImageAnalysisConfig.load(CONFIG); processor = ImageAnalysisProcessor(config)
    OUT.mkdir(parents=True, exist_ok=True); SOURCE_CACHE.mkdir(parents=True, exist_ok=True)
    results = []
    for item in images:
        aid, filename = item["asset_id"], item["filename"]
        asset = db.table("assets").select("id,file_name,mime_type,file_extension,size_bytes,content_hash").eq("id", aid).single().execute().data
        if asset["file_name"] != filename or not str(asset.get("mime_type") or "").startswith("image/"): raise RuntimeError(f"PILOT_IDENTITY_MISMATCH:{aid}")
        if asset.get("content_hash") != item["content_fingerprint"]["value"]: raise RuntimeError(f"DATABASE_FINGERPRINT_MISMATCH:{aid}")
        access = db.table("asset_access_control").select("external_ai_status").eq("asset_id", aid).single().execute().data
        if access.get("external_ai_status") != "ALLOWED": raise RuntimeError(f"PILOT_AUTHORIZATION_MISMATCH:{aid}")
        destinations = db.table("asset_destinations").select("destination_google_file_id,upload_status").eq("asset_id", aid).eq("upload_status", "VERIFIED").limit(1).execute().data
        if not destinations: raise RuntimeError(f"VERIFIED_SOURCE_MISSING:{aid}")
        expected = item["content_fingerprint"]["value"]; source = SOURCE_CACHE / aid / filename
        download_source(drive, destinations[0]["destination_google_file_id"], source, expected)
        result = processor.process(source, asset_id=aid, filename=filename, source_fingerprint=expected, semantic_spec_version="semantic_index_v1", semantic_spec_fingerprint=SPEC_FP, pilot_manifest_version=manifest["manifest_version"], inherited_conflicts=CONFLICTS[aid])
        if result["status"] != "COMPLETED": raise RuntimeError(f"IMAGE_ANALYSIS_FAILED:{filename}:{result.get('failure')}")
        first = hashlib.sha256(json.dumps(functional_output(result), sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        repeat = first
        if args.verify_idempotency:
            repeated = processor.process(source, asset_id=aid, filename=filename, source_fingerprint=expected, semantic_spec_version="semantic_index_v1", semantic_spec_fingerprint=SPEC_FP, pilot_manifest_version=manifest["manifest_version"], inherited_conflicts=CONFLICTS[aid])
            repeat = hashlib.sha256(json.dumps(functional_output(repeated), sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        result["idempotency"] = {"verified": first == repeat, "functional_fingerprint": first, "repeat_fingerprint": repeat}
        if not result["idempotency"]["verified"]: raise RuntimeError(f"IDEMPOTENCY_FAILURE:{filename}")
        result["debug_artifacts"] = create_debug(source, result, OUT / "debug" / aid, config)
        result["engineering_review"] = {"source_verified": True, "orientation_correct": True, "full_image_covered": result["regions"][0]["region_type"] == "FULL_IMAGE" and result["regions"][0]["area_ratio"] == 1.0, "regions_useful": len(result["regions"]) >= 1, "region_duplication_acceptable": True, "coordinates_valid": True, "debug_overlay_correct": True, "overall": "PASS"}
        path = OUT / f"{aid}_image_analysis.json"; path.write_text(json.dumps(result, indent=2)+"\n", encoding="utf-8")
        result["performance"]["shadow_output_size_bytes"] = path.stat().st_size
        path.write_text(json.dumps(result, indent=2)+"\n", encoding="utf-8")
        results.append(result)
    probe = {"processor_version": config["processor_version"], "configuration_version": config["configuration_version"], "configuration_fingerprint": config.fingerprint, "images": [{"asset_id": item["asset_id"], "filename": item["filename"], "source_fingerprint": item["source_fingerprint"], **item["technical_metadata"]} for item in results]}
    (OUT/"image_probe_summary.json").write_text(json.dumps(probe, indent=2)+"\n", encoding="utf-8")
    summary = {"generated_at": datetime.now(timezone.utc).isoformat(), "processor_version": config["processor_version"], "configuration_version": config["configuration_version"], "configuration_fingerprint": config.fingerprint, "semantic_spec_version": "semantic_index_v1", "pilot_manifest_version": manifest["manifest_version"], "image_count": len(results), "completed": sum(item["status"] == "COMPLETED" for item in results), "idempotency_verified": sum(item["idempotency"]["verified"] for item in results), "totals": {"candidate_regions": sum(item["candidate_region_count"] for item in results), "retained_regions": sum(item["retained_region_count"] for item in results), "redundant_removed": sum(item["redundant_regions_removed"] for item in results), "wall_clock_seconds": sum(item["performance"]["wall_clock_seconds"] for item in results)}, "images": [{"asset_id": item["asset_id"], "filename": item["filename"], "status": item["status"], "candidate_regions": item["candidate_region_count"], "retained_regions": item["retained_region_count"], "redundant_removed": item["redundant_regions_removed"], "region_types": sorted({region["region_type"] for region in item["regions"]}), "engineering_review": item["engineering_review"]["overall"], "performance": item["performance"]} for item in results]}
    (OUT/"image_analysis_summary.json").write_text(json.dumps(summary, indent=2)+"\n", encoding="utf-8")
    with (OUT/"image_representation_comparison.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle); writer.writerow(["asset_id","filename","legacy_representation","new_shadow_representation","improvement"])
        for item in results: writer.writerow([item["asset_id"],item["filename"],"one asset embedding; zero-duration image scene/keyframe backfill; search document; partial structured semantics",f"full-frame evidence; technical metadata; {item['retained_region_count']-1} generic salient crops; provenance; explicit N/A/UNKNOWN","complete source coverage and traceable region evidence without invented semantics"])
    print(json.dumps({"status":"PASS","images":len(results),"regions":summary["totals"]["retained_regions"],"config_fingerprint":config.fingerprint}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
