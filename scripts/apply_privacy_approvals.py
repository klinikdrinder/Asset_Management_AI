"""Validate/apply an explicitly completed privacy approval worksheet.

This command is intentionally never run by triage. Blank decisions are errors;
no default approval exists. Applying an APPROVE decision changes only the
external-AI gate and review metadata; consent and marketing approval remain
separate fields.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "reports/semantic-search/rollout/100/privacy-approval-required.json"
ALLOWED = {"APPROVE", "DENY", "HOLD"}


def validate(path: Path, manifest_path: Path = MANIFEST, ordinal_start: int = 31,
             ordinal_end: int = 130) -> list[dict[str, str]]:
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    raw = payload["assets"]
    values = list(raw.values()) if isinstance(raw, dict) else list(raw)
    selected = [x for x in values if x.get("ordinal") is not None and
                ordinal_start <= int(x["ordinal"]) <= ordinal_end]
    frozen = {str(x["asset_id"]): x for x in selected}
    expected = ordinal_end - ordinal_start + 1
    with path.open(newline="", encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))
    if (len(rows) != expected or len(frozen) != expected or
            {str(x.get("asset_id")) for x in rows} != set(frozen) or
            {int(x["ordinal"]) for x in rows} != set(range(ordinal_start, ordinal_end + 1))):
        raise ValueError(f"worksheet must contain exactly the frozen #{ordinal_start}-#{ordinal_end} asset IDs")
    for row in rows:
        decision = str(row.get("human_decision") or "").strip().upper()
        if decision not in ALLOWED:
            raise ValueError(f"blank or invalid human_decision for ordinal {row.get('ordinal')}")
        if not str(row.get("reviewer") or "").strip():
            raise ValueError(f"reviewer is required for ordinal {row.get('ordinal')}")
        if not str(row.get("reviewed_at") or "").strip():
            raise ValueError(f"reviewed_at is required for ordinal {row.get('ordinal')}")
        if str(row.get("filename")) != str(frozen[str(row["asset_id"])]["filename"]):
            raise ValueError(f"filename/asset mismatch for ordinal {row.get('ordinal')}")
    return rows


def apply(path: Path, manifest_path: Path = MANIFEST, ordinal_start: int = 31,
          ordinal_end: int = 130) -> None:
    load_dotenv(ROOT / ".env"); load_dotenv(ROOT / ".env.local", override=False)
    from supabase import create_client
    url = os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL"); key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key: raise RuntimeError("database configuration unavailable")
    db = create_client(url, key)
    for row in validate(path, manifest_path, ordinal_start, ordinal_end):
        decision = row["human_decision"].strip().upper()
        values = {"review_status": "REVIEWED", "reviewed_at": row["reviewed_at"], "metadata": {"privacy_review": {"decision": decision, "reviewer": row["reviewer"], "recorded_at": datetime.now(timezone.utc).isoformat(), "source": "AUTHORIZED_WORKSHEET"}}}
        if decision == "APPROVE": values.update({"classification_status": "VERIFIED", "internal_usage_status": "ALLOWED", "external_ai_status": "ALLOWED"})
        elif decision == "DENY": values.update({"external_ai_status": "NOT_ALLOWED"})
        else: values.update({"external_ai_status": "NOT_REVIEWED"})
        result = db.table("asset_access_control").update(values).eq("asset_id", row["asset_id"]).execute()
        if result.data is None: raise RuntimeError(f"approval update failed for {row['asset_id']}")


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--worksheet", type=Path, required=True); parser.add_argument("--apply", action="store_true")
    parser.add_argument("--manifest", type=Path, default=MANIFEST)
    parser.add_argument("--ordinal-start", type=int, default=31); parser.add_argument("--ordinal-end", type=int, default=130)
    args = parser.parse_args(); rows = validate(args.worksheet, args.manifest, args.ordinal_start, args.ordinal_end)
    if args.apply: apply(args.worksheet, args.manifest, args.ordinal_start, args.ordinal_end); print(json.dumps({"status": "APPLIED", "rows": len(rows)}))
    else: print(json.dumps({"status": "VALID", "rows": len(rows), "executed": False}))


if __name__ == "__main__": main()
