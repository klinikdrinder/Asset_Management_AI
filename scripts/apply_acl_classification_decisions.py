"""Validate / apply a reviewed ACL classification worksheet.

DRY RUN IS THE DEFAULT. Without ``--apply`` this performs zero database writes:
it validates the worksheet, verifies the integrity hash, checks live state for
staleness/idempotency, and predicts RLS visibility.

With ``--apply`` it writes ONLY these columns on rows whose review_decision is
CLINICAL or NON_CLINICAL: is_clinical, sensitivity_level,
requires_clinical_permission, classification_status, and an appended
metadata.acl_classification_backfill provenance block. It never touches
external_ai_status, marketing_usage_status, consent_status, download_allowed,
internal_usage_status, or any semantic/search/embedding state. By default it
only writes rows where is_clinical IS NULL (no blind overwrite); reclassifying
already-set rows requires --allow-reclassification.

Usage:
  python scripts/apply_acl_classification_decisions.py --worksheet <csv>                # dry-run (default)
  python scripts/apply_acl_classification_decisions.py --worksheet <csv> --manifest <json>
  python scripts/apply_acl_classification_decisions.py --worksheet <csv> --apply         # writes (do NOT run yet)
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from kdi_media.acl_classification import (  # noqa: E402
    WORKSHEET_VERSION,
    apply_plans,
    canonical_hash,
    duplicate_asset_ids,
    plan_row,
)


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


def read_worksheet(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def fetch_live_state(db, asset_ids: list[str]):
    """Read-only: current ACL rows + source availability for the worksheet ids."""
    acl: dict[str, dict] = {}
    source_available: dict[str, bool] = {}
    for batch in chunked(asset_ids, 100):
        for r in (db.table("asset_access_control").select(
                "asset_id,is_clinical,sensitivity_level,internal_usage_status,requires_clinical_permission,download_allowed,classification_status,metadata"
            ).in_("asset_id", batch).execute().data or []):
            acl[str(r["asset_id"])] = r
        for r in (db.table("asset_sources").select(
                "asset_id,source_files(is_missing,trashed,sync_classification,source_folders(active))"
            ).in_("asset_id", batch).execute().data or []):
            aid = str(r["asset_id"]); ok = False
            sf = r.get("source_files")
            for f in (sf if isinstance(sf, list) else [sf] if sf else []):
                folders = f.get("source_folders")
                for fold in (folders if isinstance(folders, list) else [folders] if folders else []):
                    if fold.get("active") and not f.get("is_missing", True) and not f.get("trashed", True) \
                       and f.get("sync_classification") != "REMOVED_FROM_SOURCE":
                        ok = True
            source_available[aid] = ok
    return acl, source_available


def acl_distribution(db) -> dict[str, int]:
    """Live is_clinical distribution across all asset_access_control rows — the RLS visibility gate
    requires is_clinical IS NOT NULL, so 'null' is exactly the still-hidden cohort."""
    rows = db.table("asset_access_control").select("is_clinical").execute().data or []
    dist = {"null": 0, "true": 0, "false": 0}
    for r in rows:
        v = r.get("is_clinical")
        dist["null" if v is None else "true" if v else "false"] += 1
    return dist


def main() -> None:
    p = argparse.ArgumentParser(description="Validate/apply a reviewed ACL classification worksheet")
    p.add_argument("--worksheet", type=Path, required=True)
    p.add_argument("--manifest", type=Path)
    p.add_argument("--apply", action="store_true", help="perform writes (default: dry-run only)")
    p.add_argument("--allow-reclassification", action="store_true", help="permit overwriting rows whose is_clinical is already set")
    p.add_argument("--confirm-count", type=int, default=None, help="required with --apply: must equal the planned write count (guards against surprise mass writes)")
    p.add_argument("--batch-size", type=int, default=50)
    p.add_argument("--audit-out", type=Path, default=ROOT / "audit/acl_backfill")
    args = p.parse_args()

    rows = read_worksheet(args.worksheet)
    ids = [str(r.get("asset_id") or "").strip() for r in rows]

    # --- worksheet-level integrity ---
    fatal: list[str] = []
    dupes = duplicate_asset_ids(rows)
    if dupes:
        fatal.append(f"duplicate asset_id in worksheet: {dupes[:5]}{'…' if len(dupes) > 5 else ''}")
    computed_hash = canonical_hash(rows)
    manifest = json.loads(args.manifest.read_text(encoding="utf-8")) if args.manifest and args.manifest.exists() else None
    if manifest is not None:
        if manifest.get("worksheet_version") != WORKSHEET_VERSION:
            fatal.append(f"worksheet_version mismatch: {manifest.get('worksheet_version')} != {WORKSHEET_VERSION}")
        if manifest.get("worksheet_sha256") != computed_hash:
            fatal.append("integrity hash mismatch: worksheet immutable columns were altered or do not match the manifest")
    if fatal:
        print(json.dumps({"status": "REJECTED", "errors": fatal}, indent=2))
        raise SystemExit(2)

    # --- live state (read-only) ---
    e = load_env()
    url = e.get("SUPABASE_URL") or e.get("NEXT_PUBLIC_SUPABASE_URL")
    key = e.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise SystemExit("database configuration unavailable")
    from supabase import create_client
    db = create_client(url, key)
    acl, source_available = fetch_live_state(db, [i for i in ids if i])
    distribution_before = acl_distribution(db)

    # --- plan every row (pure) ---
    plans = []
    for r in rows:
        aid = str(r.get("asset_id") or "").strip()
        plans.append(plan_row(r, acl.get(aid), source_available.get(aid, False),
                              allow_reclassification=args.allow_reclassification))

    summary: dict[str, int] = {}
    for pl in plans:
        summary[pl.action] = summary.get(pl.action, 0) + 1
    to_apply = [pl for pl in plans if pl.action == "APPLY"]
    errors = [pl for pl in plans if pl.action == "ERROR"]
    predicted_visible = sum(1 for pl in to_apply if pl.predicted_visible)

    report = {
        "status": "DRY_RUN" if not args.apply else "APPLY",
        "worksheet": str(args.worksheet),
        "worksheet_sha256": computed_hash,
        "rows": len(rows),
        "action_summary": summary,
        "planned_writes": len(to_apply),
        "predicted_visible_after_apply": predicted_visible,
        "errors": [{"asset_id": pl.asset_id, "errors": pl.errors} for pl in errors],
        "acl_distribution_before": distribution_before,
        "writes_performed": 0,
    }

    # Validate-all-first: any hard row ERROR blocks a real apply entirely.
    if args.apply and errors:
        report["status"] = "ABORTED_BEFORE_WRITE"
        report["reason"] = "one or more rows failed validation; no writes performed"
        print(json.dumps(report, indent=2))
        raise SystemExit(2)

    # Reviewed-row count confirmation: --apply must be accompanied by --confirm-count equal to the
    # exact number of planned writes, so a mass write can never happen without an explicit number.
    if args.apply and (args.confirm_count is None or args.confirm_count != len(to_apply)):
        report["status"] = "ABORTED_BEFORE_WRITE"
        report["reason"] = f"--confirm-count must equal the {len(to_apply)} planned write(s); received {args.confirm_count}"
        print(json.dumps(report, indent=2))
        raise SystemExit(2)

    if not args.apply:
        report["note"] = "DRY RUN — 0 database writes. Re-run with --apply --confirm-count <N> to write approved decisions."
        print(json.dumps(report, indent=2))
        return

    # --- real apply (gated by --apply; NOT run in the design task) ---
    rows_by_id = {str(r.get("asset_id") or "").strip(): r for r in rows}
    apply_ts = datetime.now(timezone.utc).isoformat()
    audit = {"applied": 0, "records": []}
    try:
        audit = apply_plans(db, plans, rows_by_id, acl, apply=True, apply_ts=apply_ts, worksheet_sha256=computed_hash)
    finally:
        args.audit_out.mkdir(parents=True, exist_ok=True)
        audit_path = args.audit_out / f"apply_audit_{apply_ts.replace(':', '').replace('-', '').replace('.', '')}.json"
        audit_path.write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
        report["writes_performed"] = audit.get("applied", 0)
        report["audit_log"] = str(audit_path)
    # Post-run RLS visibility recount: is_clinical distribution after writes (null = still hidden).
    report["acl_distribution_after"] = acl_distribution(db)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
