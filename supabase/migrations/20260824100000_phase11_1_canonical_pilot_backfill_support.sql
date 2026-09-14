begin;

alter table public.asset_scenes add column if not exists semantic_version text not null default 'LEGACY';
alter table public.asset_scenes add column if not exists canonical_active boolean not null default false;
alter table public.asset_scenes drop constraint if exists asset_scenes_asset_scene_index_key;
alter table public.asset_scenes add constraint asset_scenes_asset_scene_version_key unique(asset_id,scene_index,semantic_version);
create unique index if not exists asset_scenes_canonical_active_idx on public.asset_scenes(asset_id,scene_index) where canonical_active;
create index if not exists asset_scenes_semantic_version_idx on public.asset_scenes(asset_id,semantic_version,canonical_active);

alter table public.asset_events add column if not exists source_event_id uuid;
alter table public.asset_events add column if not exists semantic_version text not null default 'semantic_index_v1';
create unique index if not exists asset_events_source_event_idx on public.asset_events(asset_id,source_event_id) where source_event_id is not null;

alter table public.asset_keyframes add column if not exists source_keyframe_id uuid;
alter table public.asset_keyframes add column if not exists semantic_version text not null default 'LEGACY';
create unique index if not exists asset_keyframes_source_keyframe_idx on public.asset_keyframes(asset_id,source_keyframe_id) where source_keyframe_id is not null;

alter table public.asset_transcript_chunks add column if not exists source_chunk_id uuid;
alter table public.asset_transcript_chunks add column if not exists human_review_status text not null default 'PENDING';
create unique index if not exists transcript_chunks_source_chunk_idx on public.asset_transcript_chunks(asset_id,source_chunk_id) where source_chunk_id is not null;

alter table public.ocr_observations add column if not exists source_observation_id uuid;
alter table public.ocr_observations add column if not exists human_review_status text not null default 'PENDING';
create unique index if not exists ocr_observations_source_observation_idx on public.ocr_observations(asset_id,source_observation_id) where source_observation_id is not null;

alter table public.semantic_assertion_evidence add column if not exists idempotency_key text;
create unique index if not exists semantic_evidence_idempotency_idx on public.semantic_assertion_evidence(idempotency_key) where idempotency_key is not null;

alter table public.semantic_narratives add column if not exists source_narrative_key text;
create unique index if not exists semantic_narratives_source_key_idx on public.semantic_narratives(source_narrative_key) where source_narrative_key is not null;
alter table public.narrative_claims add column if not exists source_claim_id uuid;
create unique index if not exists narrative_claims_source_id_idx on public.narrative_claims(source_claim_id) where source_claim_id is not null;

alter table public.asset_search_concepts_v2 add column if not exists assertion_id uuid references public.semantic_assertions(id) on delete cascade;
alter table public.asset_search_concepts_v2 add column if not exists evidence_ids uuid[] not null default '{}';
alter table public.asset_search_concepts_v2 add column if not exists review_state text not null default 'AI_UNREVIEWED';
create unique index if not exists search_concepts_v2_assertion_scope_idx on public.asset_search_concepts_v2(assertion_id,coalesce(scene_id,'00000000-0000-0000-0000-000000000000'::uuid),coalesce(event_id,'00000000-0000-0000-0000-000000000000'::uuid)) where assertion_id is not null;

drop view public.effective_semantic_assertions;
create view public.effective_semantic_assertions with(security_invoker=true) as
select distinct on (a.asset_id,a.layer_id,a.predicate,coalesce(a.subject_id,a.asset_id))
 a.id assertion_id,a.asset_id,a.scene_id,a.event_id,a.keyframe_id,a.layer_id,a.subject_type,a.subject_id,a.predicate,
 coalesce(g.canonical_concept_code,case when d.decision='CORRECT' then d.human_value->>'canonical_concept_code' end,a.canonical_concept_code) canonical_concept_code,
 case when g.id is not null then g.value_json when d.decision='CORRECT' then d.human_value else coalesce(a.value_json,to_jsonb(a.value_text),to_jsonb(a.value_number),to_jsonb(a.value_boolean)) end effective_value,
 coalesce(g.semantic_state,case d.decision when 'CONFIRM_UNKNOWN' then 'UNKNOWN' when 'NOT_APPLICABLE' then 'NOT_APPLICABLE' else a.semantic_state end) semantic_state,
 a.confidence,a.search_critical,a.analysis_run_id,a.origin,a.source_fingerprint,
 coalesce((select array_agg(e.id order by e.id) from public.semantic_assertion_evidence e where e.assertion_id=a.id),'{}'::uuid[]) evidence_ids,
 case when g.id is not null then 'HUMAN_GOLD' when d.decision in ('CORRECT','APPROVE_AS_IS','CONFIRM_UNKNOWN','NOT_APPLICABLE') then 'HUMAN_APPROVED' when a.human_review_status in ('APPROVED','CORRECTED') then 'APPROVED_AI' else 'UNVERIFIED_AI' end resolution_source
from public.semantic_assertions a
left join public.gold_standard_assets ga on ga.asset_id=a.asset_id and ga.status='SIGNED_OFF'
left join public.gold_standard_assertions g on g.gold_asset_id=ga.id and g.layer_id=a.layer_id and g.predicate=a.predicate and g.active
left join lateral(select rd.* from public.semantic_review_decisions rd where rd.assertion_id=a.id and rd.decision<>'REJECT' order by rd.revision desc,rd.reviewed_at desc limit 1)d on true
where a.active
order by a.asset_id,a.layer_id,a.predicate,coalesce(a.subject_id,a.asset_id),
 case when g.id is not null then 1 when d.id is not null then 2 when a.human_review_status in ('APPROVED','CORRECTED') then 3 else 4 end,a.created_at desc;

grant select on public.effective_semantic_assertions to authenticated;
commit;
