"""Generate a READ-ONLY ACL classification review worksheet for unclassified assets.

Selects assets whose ``asset_access_control.is_clinical IS NULL`` and emits a
deterministic CSV worksheet plus a SHA-256 integrity manifest. Suggestions are
ADVISORY only and derived from already-stored metadata — no media is read, no
external AI is called, and NOTHING is written to the database.

Usage (read-only):
  python scripts/create_acl_classification_worksheet.py --all-unclassified \
      --output audit/acl_backfill/acl_851_review_worksheet.csv

  # subset by frozen ordinal (from the full local-preparation manifest)
  python scripts/create_acl_classification_worksheet.py --ordinal-start 1 --ordinal-end 50 --output ...
  # explicit ids
  python scripts/create_acl_classification_worksheet.py --asset-id <uuid> --asset-id <uuid> --output ...
  python scripts/create_acl_classification_worksheet.py --asset-id-file ids.txt --output ...
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from dotenv import dotenv_values

import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from kdi_media.acl_classification import (  # noqa: E402
    WORKSHEET_FIELDS,
    WORKSHEET_VERSION,
    AssetEvidence,
    canonical_hash,
    suggest_classification,
    worksheet_manifest,
)

DEFAULT_MANIFEST = ROOT / "reports/semantic-search/rollout/full/local-preparation-checkpoint.json"


def load_env() -> dict[str, str]:
    e: dict[str, str] = {}
    for f in (ROOT / ".env", ROOT / ".env.local", ROOT / "dashboard/.env.local"):
        if f.exists():
            e.update({k: v for k, v in dotenv_values(f).items() if v})
    e.update({k: v for k, v in os.environ.items() if v})
    return e


def chunked(seq, n=100):
    for i in range(0, len(seq), n):
        yield seq[i : i + n]


def load_manifest(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8")).get("assets", {})
    values = raw.values() if isinstance(raw, dict) else raw
    return {str(x["asset_id"]): x for x in values if x.get("asset_id")}


def build_rows(db, manifest: dict[str, dict], *, asset_ids=None, ordinal_start=None,
               ordinal_end=None, limit=0) -> list[dict]:
    # --- cohort: is_clinical IS NULL (read-only) ---
    acl_rows = (
        db.table("asset_access_control")
        .select("asset_id,is_clinical,sensitivity_level,internal_usage_status,requires_clinical_permission,download_allowed")
        .is_("is_clinical", "null")
        .execute()
        .data
        or []
    )
    acl = {str(r["asset_id"]): r for r in acl_rows}
    cohort_ids = set(acl)

    if asset_ids:
        cohort_ids &= set(asset_ids)
    if ordinal_start is not None or ordinal_end is not None:
        lo = ordinal_start if ordinal_start is not None else -10**9
        hi = ordinal_end if ordinal_end is not None else 10**9
        cohort_ids = {a for a in cohort_ids if manifest.get(a, {}).get("ordinal") is not None
                      and lo <= int(manifest[a]["ordinal"]) <= hi}

    ordered = sorted(
        cohort_ids,
        key=lambda a: (manifest.get(a, {}).get("ordinal") if manifest.get(a, {}).get("ordinal") is not None else 10**9, a),
    )
    if limit and limit > 0:
        ordered = ordered[:limit]

    # --- batched read-only enrichment ---
    assets: dict[str, dict] = {}
    profiles: dict[str, dict] = {}
    source_avail: dict[str, bool] = {}
    source_name: dict[str, str] = {}
    ready_docs: set[str] = set()
    for batch in chunked(ordered, 100):
        for r in (db.table("assets").select("id,original_file_name,file_name,mime_type,upload_status").in_("id", batch).execute().data or []):
            assets[str(r["id"])] = r
        for r in (db.table("asset_ai_profiles").select("asset_id,short_description,content_type").in_("asset_id", batch).execute().data or []):
            profiles[str(r["asset_id"])] = r
        for r in (db.table("asset_search_documents").select("asset_id,build_status").in_("asset_id", batch).eq("build_status", "READY").execute().data or []):
            ready_docs.add(str(r["asset_id"]))
        for r in (db.table("asset_sources").select("asset_id,source_files(is_missing,trashed,sync_classification,source_folders(active,source_name))").in_("asset_id", batch).execute().data or []):
            aid = str(r["asset_id"])
            ok = False
            sf = r.get("source_files")
            for f in (sf if isinstance(sf, list) else [sf] if sf else []):
                folders = f.get("source_folders")
                for fold in (folders if isinstance(folders, list) else [folders] if folders else []):
                    if fold.get("active") and not f.get("is_missing", True) and not f.get("trashed", True) \
                       and f.get("sync_classification") != "REMOVED_FROM_SOURCE":
                        ok = True
                        source_name.setdefault(aid, str(fold.get("source_name") or ""))
            source_avail[aid] = ok

    rows: list[dict] = []
    for aid in ordered:
        a = assets.get(aid, {})
        m = manifest.get(aid, {})
        c = acl.get(aid, {})
        prof = profiles.get(aid, {})
        ev = AssetEvidence(
            asset_id=aid,
            filename=str(a.get("file_name") or m.get("filename") or ""),
            source_folder=str(m.get("source_folder") or ""),
            source_name=source_name.get(aid, ""),
            description_summary=str(prof.get("short_description") or ""),
            content_type=str(prof.get("content_type") or ""),
            ocr_text=" ".join(str(x) for x in (m.get("ocr_texts_by_scene") or {}).values()) if isinstance(m.get("ocr_texts_by_scene"), dict) else "",
            transcript_text="",  # transcripts not evaluated for the cohort; left blank
            has_semantic_evidence=(aid in ready_docs) or bool(prof),
            has_people_evidence=False,
        )
        suggestion, reason, confidence = suggest_classification(ev)
        rows.append({
            "asset_id": aid,
            "ordinal": m.get("ordinal", ""),
            "filename": ev.filename,
            "original_filename": str(a.get("original_file_name") or ""),
            "media_type": str(m.get("media_type") or a.get("mime_type") or ""),
            "source_name": ev.source_name,
            "source_folder": ev.source_folder,
            "source_reference": str(m.get("source_path") or ""),  # relative path only; no URL/token
            "current_internal_usage_status": c.get("internal_usage_status", ""),
            "current_sensitivity_level": c.get("sensitivity_level", ""),
            "current_is_clinical": c.get("is_clinical", ""),
            "current_requires_clinical_permission": c.get("requires_clinical_permission", ""),
            "current_download_allowed": c.get("download_allowed", ""),
            "source_available": source_avail.get(aid, False),
            "existing_description_summary": ev.description_summary,
            "existing_content_type": ev.content_type,
            "existing_treatment": "",
            "existing_subject": "",
            "existing_clinical_visual_summary": "",
            "existing_semantic_evidence_available": ev.has_semantic_evidence,
            "existing_people_evidence_available": ev.has_people_evidence,
            "suggested_classification": suggestion,
            "suggestion_reason": reason,
            "suggestion_confidence": confidence,
            "review_decision": "",   # BLANK — human must fill
            "reviewer": "",
            "reviewed_at": "",
            "review_notes": "",
        })
    return rows


def main() -> None:
    p = argparse.ArgumentParser(description="Read-only ACL classification worksheet generator")
    p.add_argument("--all-unclassified", action="store_true")
    p.add_argument("--ordinal-start", type=int)
    p.add_argument("--ordinal-end", type=int)
    p.add_argument("--asset-id", action="append", default=[])
    p.add_argument("--asset-id-file", type=Path)
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()

    asset_ids = list(args.asset_id)
    if args.asset_id_file and args.asset_id_file.exists():
        asset_ids += [x.strip() for x in args.asset_id_file.read_text(encoding="utf-8").splitlines() if x.strip()]
    if not (args.all_unclassified or asset_ids or args.ordinal_start is not None or args.ordinal_end is not None):
        raise SystemExit("select a cohort: --all-unclassified | --ordinal-start/--ordinal-end | --asset-id | --asset-id-file")

    e = load_env()
    url = e.get("SUPABASE_URL") or e.get("NEXT_PUBLIC_SUPABASE_URL")
    key = e.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise SystemExit("database configuration unavailable")
    from supabase import create_client
    db = create_client(url, key)  # read-only usage below (only .select())

    manifest = load_manifest(args.manifest)
    rows = build_rows(db, manifest, asset_ids=asset_ids or None,
                      ordinal_start=args.ordinal_start, ordinal_end=args.ordinal_end, limit=args.limit)

    # Serialize CSV deterministically to a string first (for hashing).
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=WORKSHEET_FIELDS, quoting=csv.QUOTE_ALL, extrasaction="ignore", lineterminator="\n")
    w.writeheader()
    for r in rows:
        w.writerow(r)
    csv_text = buf.getvalue()
    digest = canonical_hash(rows)  # immutable-projection hash (survives review edits)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("﻿" + csv_text, encoding="utf-8")  # utf-8-sig BOM for Excel

    project_id = url.replace("https://", "").split(".")[0]
    manifest_out = worksheet_manifest(
        project_id=project_id,
        generated_at=datetime.now(timezone.utc).isoformat(),
        worksheet_sha256=digest,
        cohort=rows,
    )
    manifest_path = args.output.with_name(args.output.stem.replace("worksheet", "manifest") + ".json") \
        if "worksheet" in args.output.stem else args.output.with_suffix(".manifest.json")
    manifest_path.write_text(json.dumps(manifest_out, indent=2) + "\n", encoding="utf-8")

    print(json.dumps({
        "status": "GENERATED_READ_ONLY",
        "worksheet_version": WORKSHEET_VERSION,
        "cohort_count": len(rows),
        "suggestion_tally": manifest_out["suggestion_tally"],
        "source_unavailable": manifest_out["source_unavailable"],
        "worksheet": str(args.output),
        "manifest": str(manifest_path),
        "sha256": digest,
        "note": "SUGGESTIONS ADVISORY — NOT APPROVED, NOT APPLIED. No database writes performed.",
    }, indent=2))


if __name__ == "__main__":
    main()
