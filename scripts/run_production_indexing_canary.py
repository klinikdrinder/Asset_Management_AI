"""Read-only production-worker canary.

The canary intentionally uses the frozen Phase-01 selection rule and performs
the same eligibility gate as the production worker. It never writes Supabase;
an unapproved asset must be blocked before media acquisition or Claude calls.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from supabase import create_client

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/semantic-search/rollout/production-indexer"
TARGET = "ee67353a-16f0-46e8-b0b6-518806952824"


class ReadOnlyAdapters:
    def __init__(self, row: dict, acl: dict) -> None:
        from kdi_media.production_indexer import AssetEligibility
        self.row = row
        self._eligibility = AssetEligibility(
            asset_id=TARGET,
            media_type=str(row.get("mime_type") or ""),
            classification_status=str(acl.get("classification_status") or "UNKNOWN"),
            internal_usage_status=str(acl.get("internal_usage_status") or "UNKNOWN"),
            external_ai_status=str(acl.get("external_ai_status") or "UNKNOWN"),
        )
        self.failure: dict | None = None

    def eligibility(self, asset_id: str):
        assert asset_id == TARGET
        return self._eligibility

    def acquire(self, asset_id: str):
        raise AssertionError("privacy gate must run before acquisition")

    def stage(self, asset_id: str, package: dict) -> None:
        raise AssertionError("read-only canary cannot stage data")

    def completeness(self, asset_id: str) -> bool:
        return False

    def publish(self, asset_id: str) -> None:
        raise AssertionError("read-only canary cannot publish")

    def fail(self, asset_id: str, code: str, detail: str) -> None:
        self.failure = {"asset_id": asset_id, "code": code, "detail": detail}


def main() -> None:
    load_dotenv(ROOT / ".env")
    load_dotenv(ROOT / ".env.local", override=False)
    os.environ.setdefault("PYTHONPATH", str(ROOT / "src"))
    from kdi_media.production_indexer import ProductionSemanticIndexer

    url = os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise SystemExit("DATABASE_CONFIGURATION_UNAVAILABLE")
    db = create_client(url, key)
    row = (db.table("assets").select("id,file_name,mime_type,file_extension,content_hash,size_bytes")
           .eq("id", TARGET).single().execute().data)
    acl = (db.table("asset_access_control").select("*").eq("asset_id", TARGET)
           .single().execute().data)
    adapters = ReadOnlyAdapters(row, acl)
    result = ProductionSemanticIndexer(adapters).index_asset_fully(TARGET)
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "BLOCKED" if result["status"] == "BLOCKED" else result["status"],
        "target": {"ordinal": 31, **row},
        "eligibility": adapters._eligibility.__dict__,
        "result": result,
        "failure": adapters.failure,
        "database_writes": 0,
        "claude_requests": 0,
        "media_acquired": False,
        "semantic_truth_changed": 0,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "canary-31-production-worker.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
