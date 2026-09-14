"""Read-only discovery and human-review packet for AI Search V3 Batch 1."""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports" / "ai-search-v3" / "scale-up"
BLOCKED_NAMES = {
    "DSC00365.JPG", "DSC05881.JPG", "IMG_0588.MP4",
    "IMG_0620.MP4", "IMG_0621.MP4", "IMG_1253.MP4",
}
EXPECTED = {
    "assets": 881, "asset_visual_embeddings": 875,
    "asset_scenes": 8, "asset_keyframes": 8,
    "scene_embeddings": 8, "keyframe_embeddings": 8,
    "asset_search_documents": 10, "scene_search_documents": 8,
    "asset_ai_profiles": 16,
}


def env() -> dict[str, str]:
    sources = [
        ROOT / "dashboard" / ".env.local",
        ROOT / ".env.local",
        ROOT / ".worktrees" / "job8_release" / ".env.local",
    ]
    raw: dict = {}
    for source in sources:
        if source.exists():
            raw.update(dotenv_values(source))
    raw.update(os.environ)
    return {str(k).lstrip("\ufeff"): str(v) for k, v in raw.items() if v is not None}


def db(sql: str) -> object:
    values = env()
    ref = values["NEXT_PUBLIC_SUPABASE_URL"].split("//", 1)[1].split(".", 1)[0]
    response = requests.post(
        f"https://api.supabase.com/v1/projects/{ref}/database/query",
        headers={"Authorization": f"Bearer {values['SUPABASE_DASHBOARD_ACCESS_TOKEN']}"},
        json={"query": sql}, timeout=60,
    )
    if not response.ok:
        raise RuntimeError(f"Database query failed ({response.status_code}): {response.text}")
    return response.json()


SQL = r"""
with candidate_rows as (
  select a.id asset_id,a.file_name,a.mime_type,a.size_bytes,a.content_hash,
    ac.external_ai_status,ac.review_status,ac.usage_restrictions,
    sf.id source_file_id,sf.google_file_id is not null source_reference_present,
    sf.file_size_bytes source_size_bytes,sf.is_missing,sf.trashed,
    sf.sync_classification,sf.processing_error,
    d.id destination_id,d.destination_google_file_id is not null destination_reference_present,
    d.upload_status destination_status,d.verification_level,
    ve.source_method visual_source_method,ve.frame_count visual_frame_count,
    p.category existing_category,p.content_type existing_content_type,
    vj.status visual_job_status,vj.failure_code visual_failure_code,
    exists(select 1 from public.asset_search_documents sd where sd.asset_id=a.id) already_deep_indexed
  from public.assets a
  join public.asset_access_control ac on ac.asset_id=a.id
  left join lateral (
    select sf.* from public.asset_sources s join public.source_files sf on sf.id=s.source_file_id
    where s.asset_id=a.id order by (s.relationship_type='ORIGINAL') desc,s.created_at limit 1
  ) sf on true
  left join lateral (
    select d.* from public.asset_destinations d where d.asset_id=a.id
    order by (d.upload_status='VERIFIED') desc,d.created_at limit 1
  ) d on true
  left join public.asset_visual_embeddings ve on ve.asset_id=a.id
    and ve.model_provider='open_clip' and ve.model_name='ViT-B-32'
    and ve.model_version='laion2b_s34b_b79k' and ve.embedding_dimensions=512
  left join public.asset_ai_profiles p on p.asset_id=a.id
  left join lateral (
    select j.status,j.failure_code from public.asset_visual_index_jobs j
    where j.asset_id=a.id and j.model_provider='open_clip' and j.model_name='ViT-B-32'
      and j.model_version='laion2b_s34b_b79k'
    order by j.updated_at desc limit 1
  ) vj on true
  where (lower(coalesce(a.mime_type,'')) like 'image/%' or lower(coalesce(a.mime_type,'')) like 'video/%')
), eligible as (
  select * from candidate_rows c
  where c.external_ai_status='NOT_REVIEWED' and not c.already_deep_indexed
    and c.file_name <> all(array['DSC00365.JPG','DSC05881.JPG','IMG_0588.MP4','IMG_0620.MP4','IMG_0621.MP4','IMG_1253.MP4'])
    and coalesce(c.usage_restrictions,'') !~* '(DO_NOT_SEND|DENIED|BLOCKED|EXTERNAL.?AI|NOT_ALLOWED|RESTRICTED)'
    and c.content_hash is not null and c.source_file_id is not null
    and c.source_reference_present and not coalesce(c.is_missing,false) and not coalesce(c.trashed,false)
    and c.sync_classification is distinct from 'REMOVED_FROM_SOURCE'
    and c.processing_error is null and c.destination_id is not null
    and c.destination_reference_present and c.destination_status='VERIFIED'
    and c.visual_source_method is not null
    and coalesce(c.visual_job_status,'INDEXED') <> 'FAILED' and c.visual_failure_code is null
), counts as (
  select jsonb_build_object(
    'assets',(select count(*) from public.assets),
    'asset_visual_embeddings',(select count(*) from public.asset_visual_embeddings),
    'deep_indexed_assets',(select count(distinct asset_id) from public.asset_search_documents),
    'asset_scenes',(select count(*) from public.asset_scenes),
    'asset_keyframes',(select count(*) from public.asset_keyframes),
    'scene_embeddings',(select count(*) from public.scene_embeddings),
    'keyframe_embeddings',(select count(*) from public.keyframe_embeddings),
    'asset_search_documents',(select count(*) from public.asset_search_documents),
    'scene_search_documents',(select count(*) from public.scene_search_documents),
    'asset_ai_profiles',(select count(*) from public.asset_ai_profiles),
    'ai_analysis_runs',(select count(*) from public.ai_analysis_runs),
    'ocr_observations',(select count(*) from public.ocr_observations),
    'asset_transcript_chunks',(select count(*) from public.asset_transcript_chunks)
  ) value
), hashes as (
  select jsonb_object_agg(proname,md5(pg_get_functiondef(oid))) value from pg_proc
  where oid in (
    select p.oid from pg_proc p join pg_namespace n on n.oid=p.pronamespace
    where n.nspname='public' and p.proname in ('hybrid_search_assets','hybrid_search_assets_v2')
  )
)
select jsonb_build_object(
  'counts',(select value from counts),
  'hashes',(select value from hashes),
  'ranking_version',(select regexp_replace(obj_description(p.oid,'pg_proc'),'.*(job8-v3.4).*','\1') from pg_proc p join pg_namespace n on n.oid=p.pronamespace where n.nspname='public' and p.proname='hybrid_search_assets_v3' limit 1),
  'active_admins',(select coalesce(jsonb_agg(jsonb_build_object('user_id',user_id,'email',email,'management_role',management_role) order by email),'[]') from public.app_users where is_active and management_role in ('admin','super_admin')),
  'external_ai_distribution',(select jsonb_object_agg(external_ai_status,n) from (select external_ai_status,count(*) n from public.asset_access_control group by 1)x),
  'known_blocked',(select coalesce(jsonb_agg(jsonb_build_object('asset_id',asset_id,'file_name',file_name,'external_ai_status',external_ai_status,'usage_restrictions',usage_restrictions) order by file_name),'[]') from candidate_rows where file_name=any(array['DSC00365.JPG','DSC05881.JPG','IMG_0588.MP4','IMG_0620.MP4','IMG_0621.MP4','IMG_1253.MP4'])),
  'eligible_count',(select count(*) from eligible),
  'eligible',(select coalesce(jsonb_agg(to_jsonb(e) order by e.asset_id),'[]') from eligible e)
) snapshot
"""


def unwrap(result: object) -> dict:
    if isinstance(result, list) and result:
        return result[0]["snapshot"]
    if isinstance(result, dict) and "snapshot" in result:
        return result["snapshot"]
    raise RuntimeError("Unexpected database response")


def stable_key(row: dict) -> str:
    return hashlib.sha256(f"batch1:{row['asset_id']}".encode()).hexdigest()


def select_diverse(rows: list[dict], images: int, videos: int) -> list[dict]:
    selected: list[dict] = []
    for prefix, target in (("image/", images), ("video/", videos)):
        pool = [r for r in rows if r["mime_type"].lower().startswith(prefix)]
        pool.sort(key=lambda r: ((r.get("size_bytes") or 0), stable_key(r)))
        groups = [pool[i::4] for i in range(4)]
        for group in groups:
            group.sort(key=stable_key)
        while target and any(groups):
            for group in groups:
                if target and group:
                    selected.append(group.pop(0)); target -= 1
        if target:
            raise RuntimeError(f"Insufficient eligible {prefix} candidates")
    return selected


def human_size(value: int | None) -> str:
    value = int(value or 0)
    units = ["B", "KiB", "MiB", "GiB"]
    number = float(value)
    for unit in units:
        if number < 1024 or unit == units[-1]:
            return f"{number:.1f} {unit}"
        number /= 1024
    return f"{value} B"


def reason(row: dict) -> str:
    media = "still-image" if row["mime_type"].startswith("image/") else "video"
    evidence = []
    if row.get("existing_category"): evidence.append(f"existing category {row['existing_category']}")
    if row.get("existing_content_type"): evidence.append(f"content type {row['existing_content_type']}")
    suffix = f"; {', '.join(evidence)}" if evidence else ""
    return f"Eligible {media}; {human_size(row.get('size_bytes'))}; verified source/master; current 512d OpenCLIP asset vector via {row['visual_source_method']}{suffix}."


def packet_row(index: int, row: dict, group: str) -> dict:
    return {
        "ordinal": index, "group": group, "asset_id": row["asset_id"],
        "file_name": row["file_name"], "media_type": row["mime_type"],
        "size_bytes": row.get("size_bytes"), "source_file_id": row["source_file_id"],
        "destination_id": row["destination_id"], "existing_visual_embedding": True,
        "known_restriction": "NONE FOUND", "external_ai_status": row["external_ai_status"],
        "technical_selection_reason": reason(row), "decision": None,
        "decision_reason": None, "reviewer": None, "reviewed_at": None,
    }


def main() -> None:
    snapshot = unwrap(db(SQL))
    for key, value in EXPECTED.items():
        if int(snapshot["counts"][key]) != value:
            raise RuntimeError(f"Baseline count mismatch for {key}: {snapshot['counts'][key]} != {value}")
    if snapshot["ranking_version"] != "job8-v3.4":
        raise RuntimeError(f"Unexpected ranker: {snapshot['ranking_version']}")
    if snapshot["hashes"] != {
        "hybrid_search_assets": "6b179fcb951bf228d434b44baad56c38",
        "hybrid_search_assets_v2": "14f4f1347d13fa2201ac6e20e7e5020b",
    }:
        raise RuntimeError(f"V1/V2 hash mismatch: {snapshot['hashes']}")
    admins = snapshot["active_admins"]
    if not any(a["email"] == "kdimediaautomation@gmail.com" and a["management_role"] == "super_admin" for a in admins):
        raise RuntimeError("Authoritative active KDI admin was not found")
    blocked = {r["file_name"] for r in snapshot["known_blocked"]}
    if blocked != BLOCKED_NAMES:
        raise RuntimeError(f"Blocked manifest mismatch: {sorted(blocked)}")

    eligible = snapshot["eligible"]
    first = select_diverse(eligible, images=16, videos=24)
    primary_raw = select_diverse(first, images=10, videos=15)
    primary_ids = {r["asset_id"] for r in primary_raw}
    backup_raw = [r for r in first if r["asset_id"] not in primary_ids]
    rows = [packet_row(i, r, "PRIMARY" if i <= 25 else "BACKUP") for i, r in enumerate(primary_raw + backup_raw, 1)]
    generated = datetime.now(timezone.utc).isoformat()
    manifest = {
        "job": "KDI_AI_SEARCH_V3_SCALE_UP_BATCH_1", "phase": "AWAITING_HUMAN_AUTHORIZATION",
        "purpose": "KDI AI Search V3 controlled scale-up — Batch 1",
        "required_approvals": 25, "generated_at": generated,
        "authorized_reviewer_to_validate": "kdimediaautomation@gmail.com",
        "candidates_screened": int(snapshot["eligible_count"]), "primary_count": 25,
        "backup_count": 15, "known_restricted_excluded": len(snapshot["known_blocked"]),
        "database_authorization_writes": 0, "new_media_processed": 0,
        "baseline": snapshot["counts"], "external_ai_distribution": snapshot["external_ai_distribution"],
        "assets": rows,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "batch1-final-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    preflight = f"""# Batch 1 preflight

- Production health and OpenCLIP readiness: PASS (validated separately immediately before discovery).
- Search ranking: `{snapshot['ranking_version']}`.
- V1 hash: `{snapshot['hashes']['hybrid_search_assets']}` — PASS.
- V2 hash: `{snapshot['hashes']['hybrid_search_assets_v2']}` — PASS.
- Active authorized reviewer: `kdimediaautomation@gmail.com` (`super_admin`) — PASS.
- Live counts: `{json.dumps(snapshot['counts'], sort_keys=True)}`.
- External-AI distribution: `{json.dumps(snapshot['external_ai_distribution'], sort_keys=True)}`.
- Original ten-asset pilot excluded from candidate discovery and left unchanged.
- Database authorization writes: 0. External-AI/media calls: 0.
"""
    (OUT / "batch1-preflight.md").write_text(preflight, encoding="utf-8")

    lines = ["# KDI AI SEARCH V3 — BATCH 1 HUMAN AUTHORIZATION REQUIRED", "",
        "Purpose: KDI AI Search V3 controlled scale-up — Batch 1", "",
        "Required final approvals: **25**", "", "AUTHORIZED REVIEWER: `kdimediaautomation@gmail.com` (active `super_admin`; revalidation required when decisions are submitted)", "",
        f"Eligible candidates screened: **{snapshot['eligible_count']}**. The packet contains 25 primary and 15 backup candidates. Candidate selection is not approval.", ""]
    for heading, subset in (("PRIMARY CANDIDATES", rows[:25]), ("BACKUP CANDIDATES", rows[25:])):
        lines += [f"## {heading}", ""]
        for row in subset:
            lines += [f"{row['ordinal']}. `{row['file_name']}`", f"   Asset ID: `{row['asset_id']}`",
                f"   Media: `{row['media_type']}` ({human_size(row['size_bytes'])})",
                f"   Source reference: `{row['source_file_id']}`", f"   Master/destination reference: `{row['destination_id']}`",
                "   Existing visual embedding: YES", "   Known restriction: NONE FOUND",
                f"   Current external-AI status: `{row['external_ai_status']}`",
                f"   Technical selection reason: {row['technical_selection_reason']}", ""]
    lines += ["## EXCLUDED AUTHORITATIVE RESTRICTIONS", ""]
    for row in snapshot["known_blocked"]:
        lines.append(f"- `{row['file_name']}` / `{row['asset_id']}` — authoritative prior external-AI denial preserved.")
    (OUT / "batch1-candidate-review.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    decisions = ["# Batch 1 human authorization", "", "No approval has been recorded. Copy, complete, and submit the template below.", "", "```text",
        "REVIEWER:", "kdimediaautomation@gmail.com", "", "PURPOSE:", "KDI AI Search V3 controlled scale-up — Batch 1", ""]
    for row in rows:
        decisions += [f"{row['file_name']} = APPROVE / DENY / HOLD", "Reason: ...", ""]
    decisions += ["```", "", "Exactly 25 assets must be APPROVE. Every line requires a decision and reason. Approval is invalid if the reviewer is inactive, unauthorized, the purpose differs, a restricted UUID is selected, or the approved count is not exactly 25."]
    (OUT / "batch1-human-authorization.md").write_text("\n".join(decisions) + "\n", encoding="utf-8")
    print(json.dumps({k: manifest[k] for k in ("candidates_screened", "primary_count", "backup_count", "known_restricted_excluded", "database_authorization_writes", "new_media_processed")}, indent=2))


if __name__ == "__main__":
    main()
