"""Validate a reviewed ACL classification worksheet — READ-ONLY, writes nothing to the database.

Checks a reviewed worksheet (+ its manifest) against the manifest snapshot and live DB state,
reports issues by severity, writes a markdown report, and exits non-zero on any ERROR so it can
gate an apply.

Usage (read-only):
  python scripts/validate_acl_worksheet.py \
      --worksheet audit/acl_backfill/acl_851_review_worksheet.csv \
      --manifest  audit/acl_backfill/acl_851_review_manifest.json

Exit codes: 0 = no ERRORs (WARNINGs allowed); 2 = one or more ERRORs (do not apply).
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from kdi_media.acl_classification import (  # noqa: E402
    APPLYING_DECISIONS,
    CLINICAL_HINTS,
    REVIEW_DECISIONS,
    WORKSHEET_VERSION,
    canonical_hash,
    decision_to_acl,
    immutable_row_hash,
    predict_visible_after_apply,
)

SUPER_ADMIN = "3938c364-0250-40a1-8db6-9ef704ca0122"  # can_view_clinical=true (projection only)
REPORT_DEFAULT = ROOT / "audit/acl_backfill/worksheet_validation_report.md"
RUN_WARN_THRESHOLD = 50   # a run of identical decisions this long smells like bulk confirmation


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


def parse_ts(value: str):
    try:
        dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def fetch_db(db, ids: list[str]):
    acl: dict[str, dict] = {}
    upload: dict[str, str] = {}
    source_avail: dict[str, bool] = {}
    for batch in chunked(ids, 100):
        for r in (db.table("asset_access_control").select(
                "asset_id,is_clinical,internal_usage_status,sensitivity_level,requires_clinical_permission,download_allowed,classification_status,metadata"
            ).in_("asset_id", batch).execute().data or []):
            acl[str(r["asset_id"])] = r
        for r in (db.table("assets").select("id,upload_status").in_("id", batch).execute().data or []):
            upload[str(r["id"])] = str(r.get("upload_status") or "PENDING")
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
            source_avail[aid] = ok
    return acl, upload, source_avail


def main() -> None:
    p = argparse.ArgumentParser(description="Read-only ACL worksheet validator")
    p.add_argument("--worksheet", type=Path, required=True)
    p.add_argument("--manifest", type=Path, required=True)
    p.add_argument("--report", type=Path, default=REPORT_DEFAULT)
    args = p.parse_args()

    rows = read_worksheet(args.worksheet)
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    snap: dict[str, str] = manifest.get("immutable_row_hashes") or {}

    errors: list[dict] = []
    warnings: list[dict] = []
    E = lambda code, detail, asset_id="": errors.append({"code": code, "asset_id": asset_id, "detail": detail})
    W = lambda code, detail, asset_id="": warnings.append({"code": code, "asset_id": asset_id, "detail": detail})

    aid_of = lambda r: str(r.get("asset_id") or "").strip()
    ids = [aid_of(r) for r in rows]

    # ---- ERROR 1: manifest integrity (global) ----
    if manifest.get("worksheet_version") != WORKSHEET_VERSION:
        E("E1_VERSION", f"worksheet_version {manifest.get('worksheet_version')} != {WORKSHEET_VERSION}")
    computed = canonical_hash(rows)
    if manifest.get("worksheet_sha256") != computed:
        E("E1_HASH", f"worksheet sha256 mismatch (manifest {manifest.get('worksheet_sha256')} vs computed {computed}) — immutable columns/rows changed")
    if manifest.get("cohort_count") is not None and manifest["cohort_count"] != len(rows):
        E("E1_COUNT", f"row count changed: manifest {manifest['cohort_count']} vs file {len(rows)}")

    # ---- ERROR 4: duplicate / not-in-original / removed ----
    for a, n in Counter([i for i in ids if i]).items():
        if n > 1:
            E("E4_DUPLICATE", f"asset_id appears {n} times", a)
    file_ids = {i for i in ids if i}
    if snap:
        for a in sorted(file_ids - set(snap)):
            E("E4_NOT_IN_ORIGINAL", "asset_id is not in the original cohort snapshot", a)
        for a in sorted(set(snap) - file_ids):
            E("E4_ROW_REMOVED", "cohort asset_id is missing from the file (row deleted)", a)
    else:
        W("W_NO_SNAPSHOT", "manifest has no immutable_row_hashes; per-row drift (check 6) falls back to the global hash only")

    # ---- ERROR 6: per-row non-review drift ----
    if snap:
        for r in rows:
            a = aid_of(r)
            if a in snap and immutable_row_hash(r) != snap[a]:
                E("E6_ROW_DRIFT", "a non-review column differs from the manifest snapshot", a)

    # ---- ERROR 2 & 3: decisions structural ----
    now = datetime.now(timezone.utc)
    decided: list[tuple[dict, str]] = []
    for r in rows:
        raw = r.get("review_decision") or ""
        dec = raw.strip().upper()
        if not dec:
            continue
        a = aid_of(r)
        if dec not in REVIEW_DECISIONS:
            E("E2_INVALID_DECISION", f"invalid review_decision {raw!r} (allowed: {', '.join(REVIEW_DECISIONS)})", a)
            continue
        decided.append((r, dec))
        if not (r.get("reviewer") or "").strip():
            E("E3_NO_REVIEWER", f"decision {dec} but reviewer is blank", a)
        at = (r.get("reviewed_at") or "").strip()
        if not at:
            E("E3_NO_REVIEWED_AT", f"decision {dec} but reviewed_at is blank", a)
        else:
            ts = parse_ts(at)
            if ts is None:
                E("E3_REVIEWED_AT_UNPARSEABLE", f"reviewed_at {at!r} is not a valid ISO timestamp", a)
            elif ts > now:
                E("E3_REVIEWED_AT_FUTURE", f"reviewed_at {at} is in the future", a)

    # ---- live DB (read-only) ----
    e = load_env()
    url = e.get("SUPABASE_URL") or e.get("NEXT_PUBLIC_SUPABASE_URL")
    key = e.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise SystemExit("database configuration unavailable")
    from supabase import create_client
    db = create_client(url, key)
    acl, upload, source_avail = fetch_db(db, [i for i in file_ids])

    # ---- ERROR 5: is_clinical no longer NULL (stale) ----
    for r in rows:
        a = aid_of(r)
        cur = acl.get(a)
        if cur is not None and cur.get("is_clinical") is not None:
            E("E5_STALE", f"is_clinical is now {cur.get('is_clinical')} (was NULL at generation) — row is stale", a)

    # excluded set (for warning 12): NOT_ALLOWED or a library_exclusion provenance block
    excluded_ids = {a for a, cur in acl.items()
                    if str(cur.get("internal_usage_status")) == "NOT_ALLOWED"
                    or (isinstance(cur.get("metadata"), dict) and cur["metadata"].get("library_exclusion"))}

    # ---- WARNINGS 7, 8, 10, 12 (per decided row) ----
    for r, dec in decided:
        a = aid_of(r)
        sug = (r.get("suggested_classification") or "").strip().upper()
        conf = (r.get("suggestion_confidence") or "").strip().upper()
        evidence = f"reason={r.get('suggestion_reason','')!r}; clinical_visual={r.get('existing_clinical_visual_summary','')!r}"
        if dec in APPLYING_DECISIONS and sug in ("CLINICAL", "NON_CLINICAL") and dec != sug:
            if sug == "CLINICAL" and dec == "NON_CLINICAL":
                W("W7_CLINICAL_TO_NONCLINICAL", f"advisory CLINICAL but decided NON_CLINICAL — {evidence}", a)
            else:
                W("W7_CONTRADICTS_ADVISORY", f"advisory {sug} but decided {dec} — {evidence}", a)
        if conf in ("MEDIUM", "HIGH") and sug in ("CLINICAL", "NON_CLINICAL") and dec in APPLYING_DECISIONS and dec != sug:
            W("W8_HIGH_CONF_DISAGREE", f"advisory {sug} ({conf}) but decided {dec} — {evidence}", a)
        if dec == "NON_CLINICAL":
            blob = " ".join([str(r.get(k) or "") for k in
                             ("existing_description_summary", "existing_clinical_visual_summary", "existing_treatment", "suggestion_reason")]).lower()
            hits = sorted({h for h in CLINICAL_HINTS if h in blob})
            if hits:
                W("W10_NONCLINICAL_CLINICAL_EVIDENCE", f"NON_CLINICAL but stored evidence has clinical keywords: {', '.join(hits)}", a)
        if a in excluded_ids:
            W("W12_EXCLUDED_WITH_DECISION", f"asset is already separately excluded (library_exclusion / NOT_ALLOWED) but carries decision {dec}", a)

    # ---- WARNING 11: source unavailable ----
    unavailable = sorted(a for a in file_ids if not source_avail.get(a, False))
    decided_ids = {aid_of(r) for r, _ in decided}
    for a in unavailable:
        if a in decided_ids:
            W("W11_SOURCE_UNAVAILABLE", "source record missing/removed/trashed — stays hidden regardless of classification", a)

    # ---- WARNING 9: bulk-confirmation smell ----
    order = [(aid_of(r), (r.get("review_decision") or "").strip().upper()) for r in rows]
    longest_run, longest_dec, run, run_dec = 0, "", 0, None
    for _, dec in order:
        if dec and dec == run_dec:
            run += 1
        else:
            run, run_dec = (1, dec) if dec else (0, None)
        if run > longest_run:
            longest_run, longest_dec = run, run_dec
    stamps = sorted([t for t in (parse_ts((r.get("reviewed_at") or "").strip()) for r, _ in decided) if t])
    span_seconds = int((stamps[-1] - stamps[0]).total_seconds()) if len(stamps) >= 2 else 0
    reviewed_range = f"{stamps[0].isoformat()} .. {stamps[-1].isoformat()}" if stamps else "none"
    if decided:
        if longest_run >= RUN_WARN_THRESHOLD:
            W("W9_LONG_RUN", f"longest unbroken run of identical decisions = {longest_run} ({longest_dec}) in file order")
        if len(decided) >= 50 and span_seconds < len(decided) * 2:
            W("W9_FAST_SPAN", f"{len(decided)} decisions within {span_seconds}s (~{span_seconds/max(1,len(decided)):.1f}s each) — possible rubber-stamp")

    # ---- SUMMARY ----
    dec_counts = Counter(dec for _, dec in decided)
    blank = sum(1 for r in rows if not (r.get("review_decision") or "").strip())
    # agreement by advisory confidence
    conf_stats: dict[str, dict[str, int]] = {}
    for r, dec in decided:
        sug = (r.get("suggested_classification") or "").strip().upper()
        conf = (r.get("suggestion_confidence") or "NONE").strip().upper() or "NONE"
        s = conf_stats.setdefault(conf, {"decided": 0, "agree": 0})
        s["decided"] += 1
        if dec == sug:
            s["agree"] += 1
    # projected visibility after apply
    vis_super = vis_normal = 0
    for r, dec in decided:
        if dec not in APPLYING_DECISIONS:
            continue
        a = aid_of(r)
        cur = acl.get(a)
        if cur is None or cur.get("is_clinical") is not None:  # missing or stale -> not projectable
            continue
        eff = {**dict(cur), **decision_to_acl(dec, cur)}
        sa = source_avail.get(a, False)
        up = upload.get(a, "PENDING")
        if predict_visible_after_apply(eff, sa, viewer_can_view_clinical=True, upload_status=up)[0]:
            vis_super += 1
        if predict_visible_after_apply(eff, sa, viewer_can_view_clinical=False, upload_status=up)[0]:
            vis_normal += 1

    summary = {
        "worksheet": str(args.worksheet),
        "worksheet_sha256": computed,
        "rows": len(rows),
        "errors": len(errors),
        "warnings": len(warnings),
        "decision_counts": dict(dec_counts),
        "undecided": blank,
        "agreement_by_confidence": {c: f"{v['agree']}/{v['decided']}" for c, v in sorted(conf_stats.items())},
        "projected_visible_super_admin": vis_super,
        "projected_visible_normal_user": vis_normal,
        "source_unavailable_total": len(unavailable),
        "longest_identical_run": f"{longest_run} ({longest_dec})" if longest_run else "0",
        "reviewed_at_range": reviewed_range,
        "reviewed_at_span_seconds": span_seconds,
    }

    # ---- markdown report ----
    def block(title, items):
        if not items:
            return [f"## {title} — none", ""]
        out = [f"## {title} ({len(items)})", "", "| code | asset_id | detail |", "|---|---|---|"]
        out += [f"| {x['code']} | {x['asset_id'] or '—'} | {x['detail'].replace('|', '\\|')} |" for x in items]
        return out + [""]

    md = ["# ACL worksheet validation report", "",
          f"**{'FAIL — do not apply' if errors else 'OK — no blocking errors'}** · {len(errors)} error(s), {len(warnings)} warning(s)", "",
          "## Summary", "", "| metric | value |", "|---|---|"]
    md += [f"| {k} | {json.dumps(v) if isinstance(v, (dict, list)) else v} |" for k, v in summary.items()]
    md += [""] + block("ERRORS (block the apply)", errors) + block("WARNINGS (review, non-blocking)", warnings)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text("\n".join(md) + "\n", encoding="utf-8")

    print(json.dumps({"status": "FAIL" if errors else "OK", **summary, "report": str(args.report)}, indent=2))
    if errors:
        sys.exit(2)


if __name__ == "__main__":
    main()
