"""AI Search v3 - Job 1 scoped test extraction over the 20-asset cohort.

Scope is explicit and narrow:
  * external AI runs ONLY for the asset_ids in job1_test20_candidate_cohort.json
  * KDI_EXTERNAL_AI_ENABLED is set in THIS process only (never written to .env)
  * every asset is gated on can_asset_use_external_ai() before any call
  * all rows share one analysis_run_id -> reversal is a single delete on it

Pipeline per asset: auth gate -> Drive download -> keyframes (videos, bundled
ffmpeg) -> v2 contract -> Claude vision -> validate -> resolve/finalize -> write
to asset_search_concepts_v2 (+ provenance columns). Idempotent per (run, asset).

Usage:
  python scripts/run_ai_search_v3_job1_test20.py            # all not-yet-written
  python scripts/run_ai_search_v3_job1_test20.py --only <asset_id>   # smoke
"""
from __future__ import annotations

import base64, io, json, os, subprocess, sys, uuid, hashlib, argparse
from datetime import datetime, timezone
from pathlib import Path

import httpx
from dotenv import dotenv_values
from PIL import Image
from supabase import create_client
import imageio_ffmpeg
from google.oauth2 import service_account
from googleapiclient.discovery import build as gbuild
from googleapiclient.http import MediaIoBaseDownload

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from kdi_media.ontology_resolver import OntologyResolver, PERSON_ROLES, RELATIONSHIP_TYPES  # noqa
from kdi_media.extraction_contract_v2 import (  # noqa
    build_prompt, finalize_concept, LAYER_IDS, STATES, CONTRACT_VERSION,
    LOW_CONFIDENCE_THRESHOLD, NAMED_PROCEDURE_CONFIDENCE_FLOOR,
)

MODEL = "claude-opus-4-8"
NS = uuid.UUID("6b1a9f27-4c3d-4a58-9e70-2d5c8f1b3a64")
OUT = ROOT / "reports" / "ai-search-v3"
WORK = ROOT / "tmp" / "job1"; WORK.mkdir(parents=True, exist_ok=True)
FF = imageio_ffmpeg.get_ffmpeg_exe()
VOCAB_TABLE = {"ANATOMY": ("anatomy_terms", "name"), "TREATMENT_PROCEDURE": ("treatments", "name"),
               "ACTIONS_EVENTS": ("actions", "name"),
               "CLINICAL_VISUAL_OBSERVATIONS": ("clinical_observation_definitions", "label"),
               "ENVIRONMENT": ("locations", "name")}


def env():
    e = {}
    for f in (ROOT / ".env", ROOT / ".env.local", ROOT / "dashboard/.env.local"):
        if f.exists():
            e.update({k: v for k, v in dotenv_values(f).items() if v})
    e.update(os.environ)
    return e


def q(v):
    return "null" if v is None else "'" + str(v).replace("'", "''") + "'"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only")
    args = ap.parse_args()

    e = env()
    # scope external AI to THIS process only
    os.environ["KDI_EXTERNAL_AI_ENABLED"] = "true"
    os.environ["KDI_SEMANTIC_PROVIDER"] = "claude"
    url = e.get("SUPABASE_URL") or e["NEXT_PUBLIC_SUPABASE_URL"]
    ref = url.split("//")[1].split(".")[0]
    akey = e["ANTHROPIC_API_KEY"]
    db = create_client(url, e["SUPABASE_SERVICE_ROLE_KEY"])  # service_role: bypasses RLS, can write both tables

    # Drive
    creds = service_account.Credentials.from_service_account_file(
        e["GOOGLE_DRIVE_SERVICE_ACCOUNT_CREDENTIALS_PATH"],
        scopes=["https://www.googleapis.com/auth/drive.readonly"])
    drive = gbuild("drive", "v3", credentials=creds, cache_discovery=False)

    def drive_file_id(asset_id):
        rows = db.table("asset_sources").select("source_file_id,is_first_discovered_source").eq("asset_id", asset_id).execute().data or []
        rows.sort(key=lambda r: 0 if r.get("is_first_discovered_source") else 1)
        for r in rows:
            sf = db.table("source_files").select("google_file_id,is_folder").eq("id", r["source_file_id"]).single().execute().data
            if sf and sf.get("google_file_id") and not sf.get("is_folder"):
                return sf["google_file_id"]
        return None

    def download(file_id, dest):
        req = drive.files().get_media(fileId=file_id, supportsAllDrives=True)
        with open(dest, "wb") as fh:
            dl = MediaIoBaseDownload(fh, req, chunksize=8 * 1024 * 1024)
            done = False
            while not done:
                _, done = dl.next_chunk()

    def video_duration(path):
        p = subprocess.run([FF, "-i", str(path)], capture_output=True, text=True)
        for line in p.stderr.splitlines():
            if "Duration:" in line:
                hms = line.split("Duration:")[1].split(",")[0].strip()
                h, m, s = hms.split(":")
                return int(h) * 3600 + int(m) * 60 + float(s)
        return 0.0

    def jpeg_b64(path, max_side=1536):
        im = Image.open(path).convert("RGB")
        w, h = im.size
        sc = min(1.0, max_side / max(w, h))
        if sc < 1:
            im = im.resize((int(w * sc), int(h * sc)))
        buf = io.BytesIO(); im.save(buf, "JPEG", quality=85)
        return base64.b64encode(buf.getvalue()).decode("ascii")

    def frames_for(asset_id, path, is_video):
        if not is_video:
            return [jpeg_b64(path)]
        dur = video_duration(path) or 5.0
        out = []
        for i, fr in enumerate((0.05, 0.2, 0.4, 0.6, 0.8, 0.95)):
            t = max(0.0, dur * fr)
            fp = WORK / f"{asset_id}_f{i}.jpg"
            subprocess.run([FF, "-nostdin", "-ss", f"{t:.3f}", "-i", str(path), "-frames:v", "1",
                            "-q:v", "3", str(fp), "-y"], capture_output=True)
            if fp.exists():
                out.append(jpeg_b64(fp))
        return out

    # ontology vocab + resolver
    def fetch(table, cols):
        return db.table(table).select(cols).eq("is_active", True).execute().data or []
    resolver = OntologyResolver.from_rows(
        treatments=fetch("treatments", "id,code,name"),
        anatomy_terms=fetch("anatomy_terms", "id,code,name"),
        actions=fetch("actions", "id,code,name"),
        clinical_observation_definitions=fetch("clinical_observation_definitions", "id,code,label"),
        locations=fetch("locations", "id,code,name"),
        treatment_aliases=(db.table("treatment_aliases").select("treatment_id,alias,normalized_alias").eq("is_active", True).execute().data or []),
    )
    vocab = {}
    for layer, (table, namecol) in VOCAB_TABLE.items():
        vocab[layer] = [(r["code"], r.get(namecol)) for r in fetch(table, f"code,{namecol}")]
    vocab["PEOPLE_ROLES"] = [(c, c) for c in PERSON_ROLES]
    vocab["RELATIONSHIPS"] = [(c, c) for c in RELATIONSHIP_TYPES]

    def analyze(frames_b64, evidence_text):
        prompt = build_prompt(evidence_text, vocab)
        content = [{"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": b}} for b in frames_b64]
        content.append({"type": "text", "text": prompt})
        body = {"model": MODEL, "max_tokens": 12000, "thinking": {"type": "adaptive"},
                "messages": [{"role": "user", "content": content}]}
        r = httpx.post("https://api.anthropic.com/v1/messages",
                       headers={"x-api-key": akey, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                       json=body, timeout=600)
        r.raise_for_status()
        b = r.json()
        text = "".join(x.get("text", "") for x in b.get("content", []) if x.get("type") == "text")
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            s, en = text.find("{"), text.rfind("}")
            parsed = json.loads(text[s:en + 1])
        return parsed, b.get("usage", {}), b.get("stop_reason")

    def validate(v):
        by = {}
        for L in v.get("layers", []):
            lid = L.get("layer_id")
            if lid in LAYER_IDS and lid not in by and L.get("state") in STATES:
                by[lid] = L
        missing = set(LAYER_IDS) - set(by)
        if missing:
            raise RuntimeError(f"missing/invalid layers: {sorted(missing)}")
        return by

    # cohort + run id
    cohort = json.loads((OUT / "job1_test20_candidate_cohort.json").read_text())
    ids = cohort["video"] + cohort["image"]
    detail = {d["asset_id"]: d for d in cohort["detail"]}
    if args.only:
        ids = [args.only]
    run_id_file = OUT / "job1_test20_run_id.txt"
    RUN_ID = run_id_file.read_text().strip() if run_id_file.exists() else str(uuid.uuid4())
    run_id_file.write_text(RUN_ID)
    now = datetime.now(timezone.utc).isoformat()

    auth_note = (ROOT / "reports/ai-search-v3/job1_run_authorization.md").read_text(encoding="utf-8")[:4000]
    meta = {"job": "KDI_AI_SEARCH_V3_JOB_1_TEST20", "contract_version": CONTRACT_VERSION,
            "model": MODEL, "low_confidence_threshold": LOW_CONFIDENCE_THRESHOLD,
            "named_procedure_floor": NAMED_PROCEDURE_CONFIDENCE_FLOOR,
            "cohort_asset_ids": cohort["video"] + cohort["image"],
            "consent_decision": "consent_status=UNKNOWN on all assets; 20-asset test authorized; "
                                "full-library run requires a consent workflow first (see job1_run_authorization.md)",
            "external_ai_scope": "process-env only; per-asset can_asset_use_external_ai gate"}
    anchor = cohort["video"][0]
    fp = hashlib.sha256((CONTRACT_VERSION + RUN_ID).encode()).hexdigest()
    db.table("semantic_analysis_runs").upsert({
        "id": RUN_ID, "asset_id": anchor, "run_type": "AI_SEARCH_V3_JOB1_TEST", "status": "RUNNING",
        "semantic_spec_version": "semantic_index_v1", "ontology_version": "KDI_SEMANTIC_V2",
        "processor_version": "kdi-ai-search-v3-job1-test20", "configuration_fingerprint": fp,
        "source_fingerprint": "cohort:" + fp, "provider": "anthropic", "model": MODEL,
        "model_version": MODEL, "started_at": now, "metadata": meta,
    }, on_conflict="id").execute()

    results = []
    for aid in ids:
        d = detail.get(aid, {})
        is_video = str(d.get("mime", "")).startswith("video")
        rec = {"asset_id": aid, "filename": d.get("filename"), "media": "video" if is_video else "image",
               "source_folder": d.get("folder"), "source_path": d.get("path"), "status": None, "concepts": []}
        try:
            # resume: skip if this run already wrote rows for the asset
            existing = db.table("asset_search_concepts_v2").select("id").eq("analysis_run_id", RUN_ID).eq("asset_id", aid).limit(1).execute().data
            if existing:
                rec["status"] = "ALREADY_WRITTEN"; results.append(rec); print(rec["status"], aid); continue
            if db.rpc("can_asset_use_external_ai", {"p_asset_id": aid}).execute().data is not True:
                rec["status"] = "AUTH_DENIED"; results.append(rec); print(rec["status"], aid); continue
            fid = drive_file_id(aid)
            if not fid:
                rec["status"] = "NO_DRIVE_ID"; results.append(rec); continue
            ext = ".mp4" if is_video else ".jpg"
            src = WORK / f"{aid}{ext}"
            if not src.exists():
                download(fid, src)
            frames = frames_for(aid, src, is_video)
            rec["frames"] = len(frames)
            evidence_text = json.dumps({"filename": d.get("filename"), "media": rec["media"],
                                        "source_folder": d.get("folder"), "frames_supplied": len(frames)})
            parsed, usage, stop = analyze(frames, evidence_text)
            rec["usage"] = usage; rec["stop_reason"] = stop
            by = validate(parsed)
            rec["narrative"] = parsed.get("narrative", "")
            rows = []
            for lid in LAYER_IDS:
                L = by[lid]
                if L["state"] != "OBSERVED":
                    continue
                for i, c in enumerate(L.get("concepts", []) or []):
                    fin = finalize_concept(lid, c, resolver)
                    critical = lid not in ("SEARCH_EMBEDDINGS", "ASSET_IDENTITY_PROVENANCE")
                    rid = str(uuid.uuid5(NS, f"{RUN_ID}:{aid}:{lid}:{i}"))
                    rows.append((rid, fin))
                    rec["concepts"].append({"layer": lid, **{k: fin[k] for k in
                        ("concept_type", "canonical_code", "raw_concept", "model_confidence",
                         "resolution_method", "review_state", "degraded", "evidence")}})
            if rows:
                payload = [dict(
                    id=rid, asset_id=aid, scene_id=None, event_id=None, concept_type=f["concept_type"],
                    canonical_code=f["canonical_code"], display_text=f["display_text"], source="AI_MODEL",
                    semantic_state="OBSERVED", confidence=f["model_confidence"], search_critical=True,
                    human_review_status="PENDING", analysis_run_id=RUN_ID, assertion_id=None, evidence_ids=[],
                    review_state=f["review_state"], raw_concept=f["raw_concept"],
                    model_confidence=f["model_confidence"], resolution_method=f["resolution_method"],
                ) for rid, f in rows]
                db.table("asset_search_concepts_v2").insert(payload).execute()
            rec["status"] = "COMPLETE"; rec["rows_written"] = len(rows)
            print(f"COMPLETE {aid} {rec['media']} concepts={len(rows)}")
        except Exception as ex:  # noqa
            rec["status"] = "ERROR"; rec["error"] = f"{type(ex).__name__}: {ex}"[:500]
            print("ERROR", aid, rec["error"])
        results.append(rec)

    if not args.only:
        db.table("semantic_analysis_runs").update(
            {"status": "COMPLETED", "completed_at": datetime.now(timezone.utc).isoformat()}
        ).eq("id", RUN_ID).execute()
    out = {"run_id": RUN_ID, "model": MODEL, "contract_version": CONTRACT_VERSION,
           "generated_at": now, "results": results}
    (OUT / f"job1_test20_run_result.json").write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(f"\nRUN_ID={RUN_ID}  assets={len(results)}  "
          f"complete={sum(1 for r in results if r['status']=='COMPLETE')}")


if __name__ == "__main__":
    raise SystemExit(main())
