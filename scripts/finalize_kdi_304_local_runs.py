"""Finalize only the frozen, validated 304 LOCAL_PREPARATION runs."""
from __future__ import annotations

import hashlib, json, os
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv
from supabase import create_client

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "reports/semantic-search/rollout/full/kdi-304-preflight.json"
CHECKPOINT = ROOT / "reports/semantic-search/rollout/full/local-preparation-checkpoint.json"
EXPECTED = "a2eb6c8247f18c6af427281aa490d205cf9c90ba2aa563324a662aa124b1c567"

def main():
    load_dotenv(ROOT / ".env"); load_dotenv(ROOT / ".env.local", override=False)
    frozen = json.loads(AUDIT.read_text(encoding="utf-8"))["target_asset_ids"]
    actual = hashlib.sha256(("\n".join(sorted(frozen)) + "\n").encode()).hexdigest()
    if len(frozen) != 304 or actual != EXPECTED: raise SystemExit("FROZEN_MANIFEST_INVALID")
    cp = json.loads(CHECKPOINT.read_text(encoding="utf-8"))["assets"]
    bad = []
    for aid in frozen:
        row = cp.get(aid, {})
        missing = [x["path"] for x in row.get("keyframes", []) if not Path(x["path"]).is_file()]
        if row.get("local_evidence_complete") is not True or row.get("checkpoint") != "LOCAL_EVIDENCE_COMPLETE" or missing:
            bad.append({"asset_id": aid, "missing": missing, "checkpoint": row.get("checkpoint")})
    if bad: raise SystemExit("LOCAL_EVIDENCE_INVALID:" + json.dumps(bad))
    db = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])
    runs = (db.table("semantic_analysis_runs").select("id,asset_id,status,metadata")
            .eq("run_type", "LOCAL_PREPARATION").eq("metadata->>local_evidence_complete", "true").execute().data or [])
    if sorted({x["asset_id"] for x in runs}) != sorted(frozen) or len(runs) != 304:
        raise SystemExit("LIVE_LOCAL_RUN_SCOPE_INVALID")
    completed = datetime.now(timezone.utc).isoformat()
    for run in runs:
        db.table("semantic_analysis_runs").update({"status": "COMPLETED", "completed_at": completed}).eq("id", run["id"]).eq("run_type", "LOCAL_PREPARATION").execute()
    verify = (db.table("semantic_analysis_runs").select("id,asset_id,status,completed_at")
              .eq("run_type", "LOCAL_PREPARATION").eq("metadata->>local_evidence_complete", "true").execute().data or [])
    invalid = [x for x in verify if x.get("status") != "COMPLETED" or not x.get("completed_at")]
    if len(verify) != 304 or invalid: raise SystemExit("LOCAL_RUN_FINALIZATION_VERIFY_FAILED:" + json.dumps(invalid))
    print(json.dumps({"status":"PASS","target":304,"runs_finalized":304,"completed_at":completed,"acl_writes":0,"semantic_writes":0}))

if __name__ == "__main__": main()
