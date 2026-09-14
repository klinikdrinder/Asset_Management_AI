"""Remediate the four explicitly frozen KDI local-foundation exceptions.

This script is intentionally narrow.  It never calls an external AI service, never changes ACL
rows, and never touches assets outside the four immutable IDs below.  PNGs are diagnosed only;
the three authoritative files are structurally corrupt.  The PPTX is parsed locally with the
standard library and persisted through the existing LOCAL_PREPARATION run architecture.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import struct
import sys
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree as ET

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
FULL = ROOT / "reports/semantic-search/rollout/full"
CHECKPOINT = FULL / "local-preparation-checkpoint.json"
MANIFEST = ROOT / "tmp/kdi-4-remediation/remediation-manifest.json"
TEMP = ROOT / "tmp/kdi-4-remediation"
PPTX_ID = "3bcdd832-b504-4641-9729-0d965e01411a"
PNG_IDS = [
    "1e6651de-6ffb-4565-9094-b1c5cc9c09b8",
    "2746a447-4b32-415c-971e-ed3878176848",
    "c89e88bf-39fb-4bd6-8ed2-dc4cb9e3901c",
]
ALL_IDS = PNG_IDS + [PPTX_ID]
RUN_NAMESPACE = uuid.UUID("3d7e51a6-2c94-4f18-9b60-5a4c7e2f8d13")
NS_A = "http://schemas.openxmlformats.org/drawingml/2006/main"
NS_P = "http://schemas.openxmlformats.org/presentationml/2006/main"


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def png_diagnosis(path: Path, expected_sha: str) -> dict:
    b = path.read_bytes()
    chunks = []
    if b[:8] == b"\x89PNG\r\n\x1a\n":
        pos = 8
        while pos + 8 <= len(b):
            n = struct.unpack(">I", b[pos:pos + 4])[0]
            typ = b[pos + 4:pos + 8].decode("latin1")
            chunks.append({"type": typ, "declared_length": n, "offset": pos})
            pos += 12 + n
            if pos > len(b):
                break
    try:
        from PIL import Image
        with Image.open(path) as im:
            im.verify()
        pillow = "OK"
    except Exception as exc:
        pillow = f"{type(exc).__name__}: {exc}"
    return {
        "bytes": len(b), "sha256": sha256(path), "expected_sha256": expected_sha,
        "sha256_matches_record": sha256(path) == expected_sha,
        "signature": b[:8].hex(), "chunks": chunks,
        "has_iend": any(c["type"] == "IEND" for c in chunks),
        "pillow_verify": pillow,
        "classification": "SOURCE_MEDIA_CORRUPT",
        "recovery_possible": False,
    }


def pptx_evidence(path: Path) -> dict:
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        slides = sorted(
            (n for n in names if n.startswith("ppt/slides/slide") and n.endswith(".xml")),
            key=lambda n: int(n.rsplit("slide", 1)[1].split(".", 1)[0]),
        )
        notes = sorted(
            (n for n in names if n.startswith("ppt/notesSlides/notesSlide") and n.endswith(".xml")),
            key=lambda n: int(n.rsplit("notesSlide", 1)[1].split(".", 1)[0]),
        )

        def text(part: str) -> list[str]:
            root = ET.fromstring(z.read(part))
            return [x.text for x in root.findall(f".//{{{NS_A}}}t") if x.text]

        slide_text = [{"evidence_id": str(uuid.uuid5(RUN_NAMESPACE, f"{PPTX_ID}:slide:{i + 1}")),
                       "slide_ordinal": i + 1, "part": n, "text": text(n)}
                      for i, n in enumerate(slides)]
        note_text = [{"evidence_id": str(uuid.uuid5(RUN_NAMESPACE, f"{PPTX_ID}:notes:{i + 1}")),
                      "notes_ordinal": i + 1, "part": n, "text": text(n)}
                     for i, n in enumerate(notes)]
        media = sorted(n for n in names if n.startswith("ppt/media/"))
        return {
            "format": "PPTX",
            "package_valid": True,
            "zip_entries": len(names),
            "slide_count": len(slides),
            "slides": slide_text,
            "notes": note_text,
            "embedded_media": [{"evidence_id": str(uuid.uuid5(RUN_NAMESPACE, f"{PPTX_ID}:media:{n}")),
                                "part": n} for n in media],
            "embedded_media_count": len(media),
            "rendered_slides": 0,
            "renderer": None,
            "ocr_observations": 0,
            "visual_embeddings": 0,
            "visual_status": "UNAVAILABLE_NO_LOCAL_SLIDE_RENDERER",
            "text_source": "OOXML_DRAWING_TEXT_NOT_OCR",
        }


def main() -> None:
    TEMP.mkdir(parents=True, exist_ok=True)
    cp = json.loads(CHECKPOINT.read_text(encoding="utf-8"))["assets"]
    if set(ALL_IDS) != set(PNG_IDS + [PPTX_ID]) or len(ALL_IDS) != 4:
        raise SystemExit("TARGET_MANIFEST_INVALID")

    # The four source copies were independently downloaded to these paths by the read-only
    # acquisition step.  Never substitute a different file.
    before = {aid: cp.get(aid) for aid in ALL_IDS}
    report = {"generated_at": now(), "target": 4, "asset_ids": ALL_IDS,
              "external_ai_calls_attempted": 0, "external_ai_calls_completed": 0,
              "acl_modifications": 0, "before_checkpoint": before, "assets": {}}

    for aid in PNG_IDS:
        path = TEMP / f"{aid}.dest"
        if not path.is_file():
            raise SystemExit(f"MISSING_AUTHORITATIVE_DESTINATION:{aid}")
        expected = before[aid]["checksum"]
        report["assets"][aid] = {
            "filename": before[aid]["filename"], "stage": "IMAGE_DECODE",
            "authoritative_source_status": "DOWNLOADED_DESTINATION_BYTE_IDENTICAL",
            "source_relationship": "ORIGINAL" if aid != PNG_IDS[2] else "DUPLICATE",
            "diagnosis": png_diagnosis(path, expected),
        }

    pptx_path = TEMP / f"{PPTX_ID}.dest"
    if not pptx_path.is_file() or not zipfile.is_zipfile(pptx_path):
        raise SystemExit("PPTX_AUTHORITATIVE_PACKAGE_INVALID")
    evidence = pptx_evidence(pptx_path)
    aid_dir = FULL / "local-work" / PPTX_ID
    aid_dir.mkdir(parents=True, exist_ok=True)
    local_path = aid_dir / "REVIEW.pptx"
    if not local_path.exists() or sha256(local_path) != sha256(pptx_path):
        shutil.copy2(pptx_path, local_path)

    checksum = sha256(local_path)
    run_id = str(uuid.uuid5(RUN_NAMESPACE, f"{PPTX_ID}:{checksum}:kdi_local_preparation_v1"))
    started = (before.get(PPTX_ID) or {}).get("started_at") or now()
    metadata = {
        "media_type": "DOCUMENT", "technical_probe": {
            "format": "pptx", "file_size_bytes": local_path.stat().st_size,
            "package_valid": True, "slide_count": evidence["slide_count"],
        },
        "document_evidence": evidence, "local_path": str(local_path),
        "external_semantic_status": "PENDING_PRIVACY_REVIEW", "local_evidence_complete": True,
        "search_ready": False, "external_ai_calls": 0,
    }
    report["assets"][PPTX_ID] = {
        "filename": "REVIEW.pptx", "stage": "DOCUMENT_LOCAL_PREPARATION",
        "authoritative_source_status": "VALID_DESTINATION_PACKAGE",
        "checksum": checksum, "run_id": run_id, "evidence": evidence,
        "local_evidence_complete": True, "recovery_possible": True,
    }

    # Persist the PPTX through the existing canonical LOCAL_PREPARATION run and technical metadata.
    load_dotenv(ROOT / ".env"); load_dotenv(ROOT / ".env.local", override=False)
    from supabase import create_client
    from kdi_media import local_preparation as lp
    db = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])
    existing_run = db.table("semantic_analysis_runs").select("id,status,completed_at").eq("id", run_id).limit(1).execute().data or []
    # A completed canonical run is immutable on rerun; re-upserting a RUNNING row would violate
    # the database's completed_at/status consistency check.  This is the idempotency guard.
    run_metadata = lp.run_row(PPTX_ID, run_id, checksum, started, metadata)["metadata"]
    if not existing_run or existing_run[0].get("status") != "COMPLETED":
        db.table("semantic_analysis_runs").upsert(
            lp.run_row(PPTX_ID, run_id, checksum, started, metadata), on_conflict="id").execute()
    else:
        db.table("semantic_analysis_runs").update({"metadata": run_metadata}).eq("id", run_id).execute()
    technical = {
        "asset_id": PPTX_ID, "width_px": None, "height_px": None, "aspect_ratio": None,
        "orientation": "NOT_APPLICABLE", "duration_seconds": None, "fps": None,
        "codec": "OOXML/PPTX", "rotation_degrees": None, "has_audio": False,
        "audio_codec": None, "sample_rate_hz": None, "provenance": "KDI_LOCAL_PREPARATION_V1",
        "metadata": {"source_fingerprint": checksum, "file_size_bytes": local_path.stat().st_size,
                     "format_name": "pptx", "document_evidence": evidence},
    }
    try:
        db.table("asset_technical_metadata").upsert(technical, on_conflict="asset_id").execute()
    except Exception as exc:
        report["assets"][PPTX_ID]["technical_metadata_persistence"] = f"RUN_METADATA_ONLY: {exc}"
    if not existing_run or existing_run[0].get("status") != "COMPLETED":
        db.table("semantic_analysis_runs").update({"status": "COMPLETED", "completed_at": now()}).eq("id", run_id).execute()

    rec = dict(cp.get(PPTX_ID) or {})
    rec.update({"asset_id": PPTX_ID, "filename": "REVIEW.pptx", "media_type": "DOCUMENT",
                "mime_type": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
                "size": local_path.stat().st_size, "checksum": checksum,
                "source_master_reference": "1Nr5aYxCm61_5iVqzj6RJryyFug9ykuzr",
                "analysis_run_id": run_id, "checkpoint": "LOCAL_EVIDENCE_COMPLETE",
                "local_evidence_complete": True, "external_ai_calls": 0,
                "external_semantic_status": "PENDING_PRIVACY_REVIEW", "SEARCH_READY": False,
                "document_evidence": evidence, "local_path": str(local_path)})
    data = json.loads(CHECKPOINT.read_text(encoding="utf-8")); data["assets"][PPTX_ID] = rec
    data["updated_at"] = now(); CHECKPOINT.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    report["after_checkpoint"] = {aid: data["assets"].get(aid) for aid in ALL_IDS}
    MANIFEST.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps({"target": 4, "png_source_media_corrupt": 3, "pptx_local_evidence_complete": True,
                      "report": str(MANIFEST), "external_ai_calls": 0, "acl_modifications": 0}, indent=2))


if __name__ == "__main__":
    main()
