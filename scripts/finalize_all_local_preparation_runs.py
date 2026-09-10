"""Finalize validated LOCAL_PREPARATION rows from the canonical local checkpoint."""
from __future__ import annotations
import json, os
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv
from supabase import create_client

ROOT = Path(__file__).resolve().parents[1]
CHECKPOINT = ROOT / "reports/semantic-search/rollout/full/local-preparation-checkpoint.json"

def chunks(values, size=40):
    for i in range(0, len(values), size): yield values[i:i+size]

def main():
    load_dotenv(ROOT / ".env"); load_dotenv(ROOT / ".env.local", override=False)
    records = json.loads(CHECKPOINT.read_text(encoding="utf-8"))["assets"]
    ids = sorted(aid for aid, r in records.items()
                 if r.get("checkpoint") == "LOCAL_EVIDENCE_COMPLETE"
                 and r.get("local_evidence_complete") is True
                 and not any(not Path(f["path"]).is_file() for f in r.get("keyframes", [])))
    if len(ids) != 847: raise SystemExit(f"VALIDATED_LOCAL_COUNT_INVALID:{len(ids)}")
    db = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])
    runs=[]
    for batch in chunks(ids):
        runs += (db.table("semantic_analysis_runs").select("id,asset_id,status,metadata")
                 .in_("asset_id", batch).eq("run_type", "LOCAL_PREPARATION")
                 .eq("metadata->>local_evidence_complete", "true").execute().data or [])
    if len(runs) != 847 or {x["asset_id"] for x in runs} != set(ids):
        raise SystemExit(f"LIVE_RUN_SCOPE_INVALID:{len(runs)}")
    timestamp=datetime.now(timezone.utc).isoformat()
    changed=0
    for run in runs:
        if run["status"] != "COMPLETED":
            db.table("semantic_analysis_runs").update({"status":"COMPLETED","completed_at":timestamp}).eq("id",run["id"]).execute()
            changed += 1
    print(json.dumps({"validated_local":847,"newly_finalized":changed,"completed_at":timestamp,"acl_writes":0}))

if __name__ == "__main__": main()
