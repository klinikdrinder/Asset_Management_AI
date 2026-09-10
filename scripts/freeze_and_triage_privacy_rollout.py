"""Freeze #31-#130 and perform local-only privacy triage.

No semantic, ACL, consent, or external-AI fields are written. The only output
is a durable manifest and a human review queue under reports/.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from supabase import create_client

ROOT = Path(__file__).resolve().parents[1]
LOCKED = ROOT / "reports/semantic-search/30-asset-rollout/phase01/kdi_30_asset_rollout_v1.json"
OUT = ROOT / "reports/semantic-search/rollout/100"
FFPROBE = ROOT / ".tools/ffmpeg/bin/ffprobe.exe"
SUPPORTED = {"jpg", "jpeg", "png", "webp", "mp4", "mov", "pdf"}
CLINICAL_HINTS = ("clinic", "patient", "doctor", "consult", "scalp", "hair", "before", "after", "procedure")


def rows(query):
    return query.execute().data or []


def media_type(asset):
    mime = str(asset.get("mime_type") or "")
    if mime.startswith("video/"):
        return "VIDEO"
    if mime.startswith("image/"):
        return "IMAGE"
    if "pdf" in mime:
        return "DOCUMENT"
    return "OTHER"


def freeze(db):
    locked = json.loads(LOCKED.read_text(encoding="utf-8"))
    locked_assets = locked["pilot_assets"] + locked["new_assets"]
    locked_ids = {str(x["asset_id"]) for x in locked_assets}
    locked_hashes = {str(x["content_hash"]) for x in locked_assets}
    assets = rows(db.table("assets").select("id,file_name,file_extension,mime_type,size_bytes,content_hash,checksum_sha256,upload_status,migration_status"))
    sources = rows(db.table("asset_sources").select("asset_id,source_file_id,source_files(id,file_name,file_extension,size_bytes,relative_path,processing_status,decision,hash_status,content_sha256,google_file_id,source_folders(source_name))"))
    by_asset = {str(x["asset_id"]): (x.get("source_files") or {}) for x in sources}
    candidates = []
    for asset in assets:
        aid = str(asset["id"])
        source = by_asset.get(aid, {})
        ext = str(asset.get("file_extension") or Path(str(asset.get("file_name") or "")).suffix).lower().lstrip(".")
        content_hash = str(asset.get("content_hash") or asset.get("checksum_sha256") or source.get("content_sha256") or "")
        status = str(asset.get("upload_status") or asset.get("migration_status") or "").upper()
        processing = str(source.get("processing_status") or "").upper()
        decision = str(source.get("decision") or "").upper()
        reasons = []
        if aid in locked_ids or content_hash in locked_hashes: reasons.append("CERTIFIED_OR_DUPLICATE")
        if ext not in SUPPORTED: reasons.append("UNSUPPORTED_FORMAT")
        if not content_hash: reasons.append("MISSING_HASH")
        if not source.get("id") or not source.get("google_file_id"): reasons.append("UNRESOLVABLE_SOURCE")
        if any(x in status or x in processing for x in ("FAILED", "CORRUPT", "BLOCKED", "FORBIDDEN")): reasons.append("BLOCKED_STATUS")
        if decision in {"SKIP", "REJECT"}: reasons.append("SOURCE_EXCLUDED")
        if reasons: continue
        kind = media_type(asset)
        candidates.append({"asset_id": aid, "filename": str(asset.get("file_name") or ""), "media_type": kind,
                           "mime_type": asset.get("mime_type"), "size": asset.get("size_bytes") or source.get("size_bytes"),
                           "checksum": content_hash, "source_id": source.get("id"),
                           "source_master_reference": source.get("google_file_id"),
                           "source_folder": (source.get("source_folders") or {}).get("source_name"),
                           "source_path": source.get("relative_path"), "source_status": processing or status or "UNKNOWN"})
    candidates.sort(key=lambda x: (0 if x["media_type"] == "VIDEO" else 1 if x["media_type"] == "IMAGE" else 2,
                                   str(x.get("source_folder") or "").casefold(), int(x.get("size") or 0),
                                   x["filename"].casefold(), x["asset_id"]))
    target = candidates[:100]
    if len(target) != 100: raise RuntimeError(f"expected 100 eligible rollout candidates, found {len(target)}")
    for ordinal, item in enumerate(target, 31): item["ordinal"] = ordinal
    if len({x["asset_id"] for x in target}) != 100: raise RuntimeError("duplicate manifest asset IDs")
    if any(x["ordinal"] < 31 or x["ordinal"] > 130 for x in target): raise RuntimeError("manifest scope violation")
    return target


def local_probe(path: Path, kind: str) -> dict:
    if kind == "VIDEO":
        raw = json.loads(subprocess.run([str(FFPROBE), "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)], capture_output=True, text=True, check=True, timeout=180).stdout)
        streams = raw.get("streams", [])
        video = next((x for x in streams if x.get("codec_type") == "video"), {})
        return {"duration_seconds": float((raw.get("format") or {}).get("duration") or 0), "width": video.get("width"), "height": video.get("height"), "audio_stream": any(x.get("codec_type") == "audio" for x in streams), "decoded_locally": True}
    if kind == "IMAGE":
        from PIL import Image
        with Image.open(path) as image: return {"width": image.width, "height": image.height, "format": image.format, "decoded_locally": True}
    return {"decoded_locally": True, "bytes": path.stat().st_size}


class LocalPrivacyModel:
    """Local-only visual classifier. No network-capable provider is imported."""
    def __init__(self):
        from transformers import AutoModelForImageTextToText, AutoProcessor
        import torch
        self.torch = torch
        # The locally cached 256M checkpoint is the approved equivalent for
        # privacy triage and keeps this CPU-only review bounded.
        model_path = ROOT / ".kdi-models/SmolVLM2-256M-Video-Instruct"
        self.processor = AutoProcessor.from_pretrained(str(model_path), local_files_only=True)
        self.model = AutoModelForImageTextToText.from_pretrained(str(model_path), local_files_only=True, torch_dtype=torch.float32)
        self.model.eval()

    def classify(self, image) -> str:
        from PIL import Image
        if not isinstance(image, Image.Image):
            image = Image.fromarray(image)
        prompt = ("Classify privacy content in this frame for internal review. Return concise observable facts only. "
                  "State whether a patient/person receiving examination or treatment is visible, whether a clinical procedure "
                  "is visibly occurring, and whether personal or medical text is readable. Never identify anyone or infer a diagnosis.")
        messages = [{"role": "user", "content": [{"type": "image"}, {"type": "text", "text": prompt}]}]
        rendered = self.processor.apply_chat_template(messages, add_generation_prompt=True)
        inputs = self.processor(text=rendered, images=[image.convert("RGB")], return_tensors="pt")
        with self.torch.no_grad():
            generated = self.model.generate(**inputs, max_new_tokens=45, do_sample=False)
        completion = generated[:, inputs["input_ids"].shape[1]:]
        return self.processor.batch_decode(completion, skip_special_tokens=True)[0].strip()[:500]


def sample_video_frames(path: Path, duration: float, directory: Path) -> list[Path]:
    import subprocess
    times = sorted(set(max(0.0, min(duration - 0.05, duration * f)) for f in (0.1, 0.5, 0.9)))
    result = []
    for index, timestamp in enumerate(times):
        target = directory / f"frame-{index}.jpg"
        subprocess.run([str(ROOT / ".tools/ffmpeg/bin/ffmpeg.exe"), "-ss", f"{timestamp:.3f}", "-i", str(path), "-frames:v", "1", "-q:v", "4", "-y", str(target)], capture_output=True, check=True, timeout=180)
        if target.is_file() and target.stat().st_size: result.append(target)
    return result


def main():
    load_dotenv(ROOT / ".env"); load_dotenv(ROOT / ".env.local", override=False)
    url = os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL"); key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key: raise SystemExit("DATABASE_CONFIGURATION_UNAVAILABLE")
    db = create_client(url, key); manifest = freeze(db)
    ids = [x["asset_id"] for x in manifest]
    acl_rows = rows(db.table("asset_access_control").select("asset_id,classification_status,internal_usage_status,consent_status,marketing_usage_status,external_ai_status").in_("asset_id", ids))
    acl = {str(x["asset_id"]): x for x in acl_rows}
    layer_rows = rows(db.table("asset_semantic_layers").select("asset_id,processing_status").in_("asset_id", ids).eq("active", True))
    layer_counts = {}
    for row in layer_rows: layer_counts.setdefault(str(row["asset_id"]), []).append(row.get("processing_status"))
    docs = {str(x["asset_id"]) for x in rows(db.table("asset_search_documents").select("asset_id").in_("asset_id", ids).eq("build_status", "READY"))}
    destinations = {str(x["asset_id"]): x for x in rows(db.table("asset_destinations").select("asset_id,destination_google_file_id,upload_status").in_("asset_id", ids).eq("upload_status", "VERIFIED"))}
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseDownload
    cred_path = os.getenv("GOOGLE_DRIVE_SERVICE_ACCOUNT_CREDENTIALS_PATH") or str(ROOT / ".secrets/kdi-media-reader.json")
    drive = build("drive", "v3", credentials=service_account.Credentials.from_service_account_file(cred_path, scopes=["https://www.googleapis.com/auth/drive.readonly"]), cache_discovery=False)
    visual_model = LocalPrivacyModel()
    triage = []
    for item in manifest:
        print(json.dumps({"stage": "local_privacy_triage", "ordinal": item["ordinal"], "filename": item["filename"]}), flush=True)
        aid = item["asset_id"]; acl_item = acl.get(aid, {})
        evidence = ["source metadata and local technical probe"]
        status = "INVALID_UNAVAILABLE"
        probe = {}
        patient = procedure = sensitive = False
        temp = Path(tempfile.mkdtemp(prefix="kdi-privacy-")); path = temp / item["filename"]
        try:
            with path.open("wb") as fh:
                dl = MediaIoBaseDownload(fh, drive.files().get_media(fileId=destinations[aid]["destination_google_file_id"], supportsAllDrives=True), chunksize=8 * 1024 * 1024)
                done = False
                while not done: _, done = dl.next_chunk(num_retries=3)
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if digest != item["checksum"]: raise RuntimeError("MASTER_HASH_MISMATCH")
            probe = local_probe(path, item["media_type"])
            stem = item["filename"].lower()
            frame_facts = []
            if item["media_type"] == "VIDEO":
                frames = sample_video_frames(path, float(probe.get("duration_seconds") or 0), temp)
                from PIL import Image
                for frame in frames:
                    with Image.open(frame) as image: frame_facts.append(visual_model.classify(image))
                probe["sampled_frames"] = len(frame_facts)
            joined = " ".join(frame_facts).lower()
            patient = any(x in joined for x in ("patient", "receiving treatment", "examination", "examining", "consultation"))
            procedure = any(x in joined for x in ("procedure", "treatment occurring", "surgery", "medical procedure"))
            sensitive = any(x in joined for x in ("personal text", "medical text", "phone number", "name", "record"))
            if patient: evidence.append("local visual model reported patient/examination context across sampled frames")
            if procedure: evidence.append("local visual model reported an active clinical procedure signal")
            if sensitive: evidence.append("local visual model reported potentially sensitive visible text")
            if patient and procedure: status = "CLINICAL"
            elif patient or procedure or sensitive: status = "POTENTIALLY_CLINICAL"
            elif frame_facts: status = "NON_CLINICAL"
            else: status = "UNCERTAIN"
            item["_local_model_facts"] = frame_facts
        except Exception as exc:
            evidence.append(str(exc)); status = "INVALID_UNAVAILABLE"
        finally: shutil.rmtree(temp, ignore_errors=True)
        triage.append({k: v for k, v in {**item, "current_semantic_status": "COMPLETE" if len(layer_counts.get(aid, [])) == 18 and all(x == "COMPLETE" for x in layer_counts.get(aid, [])) else "PENDING", "SEARCH_READY": aid in docs, "local_classification": status, "classification_confidence": "MEDIUM" if status != "UNCERTAIN" else "LOW", "classification_evidence": evidence, "technical_probe": probe,
                       "classification_status": acl_item.get("classification_status"), "internal_usage_status": acl_item.get("internal_usage_status"), "consent_status": acl_item.get("consent_status"), "marketing_usage_status": acl_item.get("marketing_usage_status"), "external_ai_status": acl_item.get("external_ai_status"),
                       "patient_context_signal": patient, "procedure_context_signal": procedure, "sensitive_text_signal": sensitive,
                       "recommended_next_action": "AUTHORIZED_HUMAN_PRIVACY_REVIEW_BEFORE_EXTERNAL_AI"}.items() if not k.startswith("_")})
    OUT.mkdir(parents=True, exist_ok=True)
    artifact = {"generated_at": datetime.now(timezone.utc).isoformat(), "manifest_id": "kdi_semantic_rollout_100_v1", "range": "#31-#130", "rows": len(triage), "duplicates": 0, "assets": triage, "external_ai_calls": 0}
    (OUT / "privacy-approval-required.json").write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")
    md = ["# KDI privacy review queue", "", "External-AI approval was not changed by this triage.", "", "| Ordinal | Filename | Local classification | External AI | Consent | Recommended action |", "|---:|---|---|---|---|---|"]
    md += [f"| {x['ordinal']} | {x['filename']} | {x['local_classification']} | {x.get('external_ai_status')} | {x.get('consent_status')} | {x['recommended_next_action']} |" for x in triage]
    (OUT / "privacy-approval-required.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    from collections import Counter
    print(json.dumps({"status": "PASS", "manifest_rows": len(triage), "local_inspected": sum(bool(x["technical_probe"]) for x in triage), "classifications": Counter(x["local_classification"] for x in triage), "external_ai_calls": 0}))


if __name__ == "__main__": main()
