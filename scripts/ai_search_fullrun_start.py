"""Orchestrate the AI Search v3 full run start (consent cleared 2026-09-12).

  1. acquire the run-start lock (refuses if another run is active + fresh)
  2. create the semantic_analysis_runs record (with the consent note)
  3. SMOKE one real extraction end-to-end (fail fast before the fleet)
  4. enqueue ONLY decodable assets (asset_media_probe.status='DECODABLE')
  5. leave the run row RUNNING; two workers then drain the queue

Prints the run_id, enqueued/held-back counts. Does NOT launch workers (that is
done under process management), and does NOT touch quarantined assets.
"""
from __future__ import annotations

import hashlib, sys, uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from ai_search_extract import Extractor, MODEL  # noqa
from ai_search_queue_worker import enqueue, acquire_lock, LOCK_NAME  # noqa
from kdi_media.extraction_contract_v2 import CONTRACT_VERSION  # noqa

CONSENT = ("Klinik Dr Inder authorized external AI processing of clinic media for "
           "INTERNAL SEMANTIC INDEXING ONLY - no publication, no external sharing "
           "(cleared 2026-09-12). See reports/ai-search-v3/job1_run_authorization.md.")


def main():
    x = Extractor()
    D = x.db
    R = str(uuid.uuid4())
    if not acquire_lock(D, "orchestrator", R):
        print("REFUSED: another full run holds the lock and is fresh. Aborting.")
        return 1
    decodable = [r["asset_id"] for r in
                 (D.table("asset_media_probe").select("asset_id").eq("status", "DECODABLE").execute().data or [])]
    held = (D.table("asset_media_probe").select("asset_id", count="exact").eq("status", "QUARANTINE").execute().count or 0)
    if not decodable:
        print("no decodable assets; aborting"); return 1
    anchor = decodable[0]
    now = datetime.now(timezone.utc).isoformat()
    fp = hashlib.sha256((CONTRACT_VERSION + R).encode()).hexdigest()
    D.table("semantic_analysis_runs").upsert({
        "id": R, "asset_id": anchor, "run_type": "AI_SEARCH_V3_FULL", "status": "RUNNING",
        "semantic_spec_version": "semantic_index_v1", "ontology_version": "KDI_SEMANTIC_V2",
        "processor_version": "kdi-ai-search-v3-fullrun", "configuration_fingerprint": fp,
        "source_fingerprint": "fullrun:" + fp, "provider": "anthropic", "model": MODEL,
        "model_version": MODEL, "started_at": now,
        "metadata": {"job": "KDI_AI_SEARCH_V3_FULL", "contract_version": CONTRACT_VERSION,
                     "model": MODEL, "consent": CONSENT, "decodable_enqueued": len(decodable),
                     "held_back_quarantine": held, "external_ai_scope": "internal_indexing_only"},
    }, on_conflict="id").execute()

    # 3. smoke one real extraction before the fleet
    smoke = decodable[0]
    res = x.process(smoke, run_id=R, dry_run=False)
    if res.get("status") != "COMPLETE":
        print(f"SMOKE FAILED on {smoke}: {res}. Not enqueuing. Investigate before running.")
        D.table("semantic_analysis_runs").update({"status": "FAILED", "error_message": f"smoke:{res}"}).eq("id", R).execute()
        return 1
    # 4. enqueue all decodable; mark the smoked asset DONE so no worker repeats it
    n = enqueue(D, R, decodable)
    D.table("ai_search_job_queue").update(
        {"state": "DONE", "updated_at": now}).eq("run_id", R).eq("asset_id", smoke).execute()
    print(f"RUN_ID={R}")
    print(f"smoke_ok={smoke} concepts={res.get('concepts')}")
    print(f"enqueued={n} (1 pre-completed by smoke) held_back_quarantine={held}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
