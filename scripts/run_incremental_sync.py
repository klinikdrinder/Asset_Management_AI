"""Step 14 command guard and environment preflight.

Live execution stays fail-closed until the Step 14 migration is deployed and
the production adapter is explicitly verified.  It never silently falls back
to the legacy full migration command.
"""
from __future__ import annotations
import argparse, json, os, sys
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from kdi_media.incremental_sync import write_json_report

REQUIRED=("SUPABASE_URL","SUPABASE_SERVICE_ROLE_KEY","GOOGLE_DRIVE_CREDENTIALS_FILE","GOOGLE_DRIVE_TOKEN_FILE","GOOGLE_DRIVE_DESTINATION_TOKEN_FILE")

def main(argv=None):
    parser=argparse.ArgumentParser(description="KDI Step 14 incremental synchronization")
    parser.add_argument("sync",nargs="?",default="sync")
    parser.add_argument("--incremental",action="store_true",required=True)
    parser.add_argument("--dry-run",action="store_true")
    parser.add_argument("--source-id")
    parser.add_argument("--run-id")
    parser.add_argument("--trigger",choices=("manual","scheduled"),default="manual")
    args=parser.parse_args(argv)
    missing=[name for name in REQUIRED if not os.getenv(name,"").strip()]
    stamp=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    report={"run_type":"incremental_sync","trigger_type":args.trigger,"dry_run":args.dry_run,"started_at":datetime.now(timezone.utc).isoformat(),"status":"BLOCKED_CONFIGURATION" if missing else "BLOCKED_NOT_VERIFIED","missing_environment":missing,"message":"Production Step 14 adapter has not passed controlled tests A-J; no source or destination changes were made."}
    path=ROOT/"reports"/"step-14"/f"incremental-sync-{stamp}.json"
    write_json_report(path,report)
    print(json.dumps({"status":report["status"],"dry_run":args.dry_run,"report":str(path),"missing_environment":missing}))
    return 2

if __name__=="__main__": raise SystemExit(main())
