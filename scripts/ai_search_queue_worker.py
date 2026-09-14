"""DB-backed work queue for the AI Search v3 full run.

Survives a disconnected shell and cannot corrupt on double-start:
  * one job row per asset (QUEUED/CLAIMED/DONE/FAILED)
  * atomic claim via ai_search_claim_jobs() = FOR UPDATE SKIP LOCKED, so two
    workers never take the same asset; expired CLAIMED rows return to work
  * a single-instance lock row (ai_search_acquire_lock) so a second ORCHESTRATOR
    refuses to start; heartbeat renews it, a dead holder goes stale and frees it
  * progress is visible by SELECT (queue states + lock heartbeat), not a log

Modes:
  enqueue  --run <uuid> --assets a,b,c    populate the queue
  work     --run <uuid> --worker <name>   claim+process loop (bounded, leased)
  status   --run <uuid>                   print queue state counts
  selftest                                prove the machinery, no API calls

The real per-asset processor is intentionally pluggable (process_asset). In
--dry-run / selftest it just marks DONE so the concurrency machinery can be
tested without model calls or the consent gate. The full run wires process_asset
to the (generalized) extraction pipeline.
"""
from __future__ import annotations

import argparse, os, socket, time, uuid
from pathlib import Path
from dotenv import dotenv_values
from supabase import create_client

ROOT = Path(__file__).resolve().parents[1]
LOCK_NAME = "ai_search_full_run"
LEASE_SECONDS = 900
STALE_LOCK_SECONDS = 120


def db():
    e = {}
    for f in (ROOT / ".env", ROOT / ".env.local", ROOT / "dashboard/.env.local"):
        if f.exists():
            e.update({k: v for k, v in dotenv_values(f).items() if v})
    e.update(os.environ)
    return create_client(e.get("SUPABASE_URL") or e["NEXT_PUBLIC_SUPABASE_URL"], e["SUPABASE_SERVICE_ROLE_KEY"])


def enqueue(D, run_id, asset_ids):
    rows = [{"run_id": run_id, "asset_id": a, "state": "QUEUED"} for a in asset_ids]
    D.table("ai_search_job_queue").upsert(rows, on_conflict="run_id,asset_id").execute()
    return len(rows)


def acquire_lock(D, holder, run_id):
    return D.rpc("ai_search_acquire_lock", {"p_name": LOCK_NAME, "p_holder": holder,
                 "p_run": run_id, "p_stale": STALE_LOCK_SECONDS}).execute().data is True


def heartbeat(D, holder, processed=None, total=None):
    patch = {"heartbeat_at": "now()"}
    # PostgREST can't call now(); send an ISO timestamp instead
    from datetime import datetime, timezone
    patch = {"heartbeat_at": datetime.now(timezone.utc).isoformat()}
    if processed is not None:
        patch["processed"] = processed
    if total is not None:
        patch["total"] = total
    D.table("ai_search_run_lock").update(patch).eq("lock_name", LOCK_NAME).eq("holder", holder).execute()


def claim(D, run_id, worker, limit=2, lease=LEASE_SECONDS):
    return [r["ai_search_claim_jobs"] if isinstance(r, dict) else r
            for r in (D.rpc("ai_search_claim_jobs", {"p_run": run_id, "p_worker": worker,
                      "p_lease": lease, "p_limit": limit}).execute().data or [])]


def complete(D, run_id, asset_id, ok, err=None):
    from datetime import datetime, timezone
    D.table("ai_search_job_queue").update({
        "state": "DONE" if ok else "FAILED", "last_error": err,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }).eq("run_id", run_id).eq("asset_id", asset_id).execute()


def status(D, run_id):
    rows = D.table("ai_search_job_queue").select("state").eq("run_id", run_id).execute().data or []
    from collections import Counter
    return dict(Counter(r["state"] for r in rows))


def process_asset(asset_id, run_id=None, dry_run=True, extractor=None):
    """Dry-run marks DONE (machinery test). Real path delegates to the
    generalized extractor (drive -> 3-tier decode/frames -> v2 contract ->
    resolver + finalize + donor precondition -> write). Real path is
    consent-gated and only runs when dry_run is False with an extractor."""
    if dry_run:
        return True, None
    r = extractor.process(asset_id, run_id=run_id, dry_run=False)
    ok = r.get("status") == "COMPLETE"
    return ok, None if ok else r.get("status")


def work(D, run_id, worker, dry_run=True):
    """One worker. Multiple workers run concurrently and safely: each claims a
    single job atomically via FOR UPDATE SKIP LOCKED, so they never overlap.
    No per-worker startup lock (that would block the 2nd worker) - the
    corruption guard is the atomic claim; the run-start guard lives in the
    orchestrator (acquire_lock at enqueue). Progress is visible in the DB via
    queue state counts; each worker also heartbeats the lock row for liveness."""
    from datetime import datetime, timezone
    extractor = None
    if not dry_run:
        import sys as _sys
        _sys.path.insert(0, str(Path(__file__).resolve().parent))
        from ai_search_extract import Extractor  # lazy
        extractor = Extractor()
    processed = 0
    while True:
        batch = claim(D, run_id, worker, limit=1)  # one at a time -> smooth 2-worker balancing
        if not batch:
            break
        for aid in batch:
            try:
                ok, err = process_asset(aid, run_id=run_id, dry_run=dry_run, extractor=extractor)
            except Exception as ex:  # noqa
                ok, err = False, f"{type(ex).__name__}:{ex}"[:300]
            complete(D, run_id, aid, ok, err)
            processed += 1
        D.table("ai_search_run_lock").upsert(
            {"lock_name": LOCK_NAME, "holder": worker, "run_id": run_id,
             "heartbeat_at": datetime.now(timezone.utc).isoformat()}, on_conflict="lock_name").execute()
    print(f"[{worker}] drained; processed {processed}")


def selftest(D):
    run = str(uuid.uuid4())
    assets = [r["id"] for r in (D.table("assets").select("id").limit(4).execute().data or [])]
    ok = True
    try:
        enqueue(D, run, assets)
        assert status(D, run).get("QUEUED") == 4, "enqueue"
        # 1. single-instance lock: first holder wins, second refuses
        assert acquire_lock(D, "w1", run) is True, "w1 lock"
        assert acquire_lock(D, "w2", run) is False, "w2 must be refused"
        # 2. atomic disjoint claims (SKIP LOCKED): two claims never overlap
        c1 = set(claim(D, run, "w1", limit=2))
        c2 = set(claim(D, run, "w2", limit=2))
        assert len(c1) == 2 and len(c2) == 2 and not (c1 & c2), f"disjoint claims {c1} {c2}"
        # 3. expired claim returns to the pool and can be reclaimed
        from datetime import datetime, timezone, timedelta
        one = next(iter(c1))
        D.table("ai_search_job_queue").update(
            {"claim_expires_at": (datetime.now(timezone.utc) - timedelta(seconds=5)).isoformat()}
        ).eq("run_id", run).eq("asset_id", one).execute()
        rec = set(claim(D, run, "w3", limit=4))
        assert one in rec, "expired claim not reclaimed"
        # 4. complete everything -> all DONE
        for a in assets:
            complete(D, run, a, True)
        st = status(D, run)
        assert st.get("DONE") == 4 and "QUEUED" not in st, f"final {st}"
        print("SELFTEST PASS:", {"enqueue": 4, "lock_refuses_second": True,
              "claims_disjoint": True, "expired_reclaimed": True, "all_done": st})
    except AssertionError as ex:
        ok = False
        print("SELFTEST FAIL:", ex, "state=", status(D, run))
    finally:
        D.table("ai_search_job_queue").delete().eq("run_id", run).execute()
        D.table("ai_search_run_lock").delete().eq("lock_name", LOCK_NAME).execute()
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["enqueue", "work", "status", "selftest"])
    ap.add_argument("--run"); ap.add_argument("--worker", default=f"{socket.gethostname()}:{os.getpid()}")
    ap.add_argument("--assets"); ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    D = db()
    if a.mode == "selftest":
        raise SystemExit(0 if selftest(D) else 1)
    if a.mode == "enqueue":
        print("enqueued", enqueue(D, a.run, a.assets.split(",")))
    elif a.mode == "status":
        print(status(D, a.run))
    elif a.mode == "work":
        work(D, a.run, a.worker, dry_run=a.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
