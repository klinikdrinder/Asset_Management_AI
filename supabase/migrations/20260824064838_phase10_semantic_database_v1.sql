begin;

-- Phase 10 canonical semantic database. Deployment is intentionally gated by
-- reports/semantic-search/database/migration_reconciliation.json.
create table if not exists public.semantic_layer_definitions (
  layer_id text primary key,
  layer_number smallint not null unique check (layer_number between 1 and 18),
  layer_name text not null,
  description text not null default '',
  scope text not null check (scope in ('ASSET','TEMPORAL','PERSON','MULTI_SCOPE')),
  is_search_critical boolean not null default false,
  spec_version text not null,
  active boolean not null default true,
  created_at timestamptz not null default now()
);

insert into public.semantic_layer_definitions(layer_number,layer_id,layer_name,scope,is_search_critical,spec_version) values
 (1,'ASSET_IDENTITY_PROVENANCE','Asset Identity & Provenance','ASSET',true,'semantic_index_v1'),
 (2,'GLOBAL_ASSET_UNDERSTANDING','Global Asset Understanding','ASSET',true,'semantic_index_v1'),
 (3,'TEMPORAL_SCENE_STRUCTURE','Temporal / Scene Structure','TEMPORAL',true,'semantic_index_v1'),
 (4,'PEOPLE_ROLES','People & Roles','PERSON',true,'semantic_index_v1'),
 (5,'PERSON_APPEARANCE','Person Appearance','PERSON',false,'semantic_index_v1'),
 (6,'ANATOMY','Anatomy','MULTI_SCOPE',true,'semantic_index_v1'),
 (7,'TREATMENT_PROCEDURE','Treatment / Procedure','MULTI_SCOPE',true,'semantic_index_v1'),
 (8,'ACTIONS_EVENTS','Actions & Events','TEMPORAL',true,'semantic_index_v1'),
 (9,'RELATIONSHIPS','Relationships','MULTI_SCOPE',true,'semantic_index_v1'),
 (10,'CLINICAL_VISUAL_OBSERVATIONS','Clinical Visual Observations','MULTI_SCOPE',true,'semantic_index_v1'),
 (11,'ENVIRONMENT','Environment','MULTI_SCOPE',false,'semantic_index_v1'),
 (12,'CINEMATOGRAPHY','Cinematography','TEMPORAL',false,'semantic_index_v1'),
 (13,'COMPOSITION','Composition','MULTI_SCOPE',false,'semantic_index_v1'),
 (14,'SPEECH_TRANSCRIPT_AUDIO','Speech / Transcript / Audio','MULTI_SCOPE',true,'semantic_index_v1'),
 (15,'OCR_VISIBLE_TEXT','OCR / Visible Text','MULTI_SCOPE',true,'semantic_index_v1'),
 (16,'MARKETING_CONTENT_USAGE','Marketing & Content Usage','ASSET',true,'semantic_index_v1'),
 (17,'SEMANTIC_NARRATIVE','Semantic Narrative','MULTI_SCOPE',true,'semantic_index_v1'),
 (18,'SEARCH_EMBEDDINGS','Search & Embeddings','MULTI_SCOPE',true,'semantic_index_v1')
on conflict(layer_id) do update set layer_number=excluded.layer_number,layer_name=excluded.layer_name,scope=excluded.scope,
 is_search_critical=excluded.is_search_critical,spec_version=excluded.spec_version,active=true;

create table if not exists public.semantic_analysis_runs (
  id uuid primary key default gen_random_uuid(), asset_id uuid not null references public.assets(id) on delete cascade,
  run_type text not null, status text not null check(status in ('QUEUED','RUNNING','COMPLETED','COMPLETED_WITH_ERRORS','FAILED','CANCELLED')),
  semantic_spec_version text not null default 'semantic_index_v1', ontology_version text not null default 'KDI_SEMANTIC_V2',
  indexing_version text, embedding_version text, query_parser_version text, retrieval_version text, ranking_version text,
  llm_reranker_version text, benchmark_version text, pilot_manifest_version text,
  processor_version text not null, configuration_version text, configuration_fingerprint text not null,
  source_fingerprint text not null, provider text, model text, model_version text, started_at timestamptz,
  completed_at timestamptz, parent_run_id uuid references public.semantic_analysis_runs(id),
  supersedes_run_id uuid references public.semantic_analysis_runs(id), error_code text, error_message text,
  created_at timestamptz not null default now(),
  check(completed_at is null or started_at is null or completed_at>=started_at),
  unique(asset_id,run_type,source_fingerprint,processor_version,configuration_fingerprint)
);

create table if not exists public.asset_semantic_layers (
  id uuid primary key default gen_random_uuid(), asset_id uuid not null references public.assets(id) on delete cascade,
  layer_id text not null references public.semantic_layer_definitions(layer_id), analysis_run_id uuid not null references public.semantic_analysis_runs(id),
  applicability text not null check(applicability in ('APPLICABLE','NOT_APPLICABLE','UNKNOWN')),
  semantic_state text not null check(semantic_state in ('OBSERVED','FALSE','UNKNOWN','NOT_APPLICABLE')),
  processing_status text not null check(processing_status in ('PENDING','PROCESSING','COMPLETE','FAILED','STALE')),
  completeness_status text not null check(completeness_status in ('NOT_STARTED','PARTIAL','COMPLETE','NOT_APPLICABLE')),
  confidence_summary jsonb not null default '{}'::jsonb check(jsonb_typeof(confidence_summary)='object'),
  human_review_status text not null default 'PENDING' check(human_review_status in ('PENDING','IN_REVIEW','APPROVED','CORRECTED','REJECTED')),
  ontology_version text not null, semantic_spec_version text not null, active boolean not null default true,
  superseded_by uuid references public.asset_semantic_layers(id), created_at timestamptz not null default now(), updated_at timestamptz not null default now(),
  unique(asset_id,layer_id,analysis_run_id), check((semantic_state='NOT_APPLICABLE')=(applicability='NOT_APPLICABLE'))
);

create table if not exists public.asset_events (
  id uuid primary key default gen_random_uuid(), asset_id uuid not null references public.assets(id) on delete cascade,
  scene_id uuid references public.asset_scenes(id) on delete cascade, start_time numeric not null check(start_time>=0),
  end_time numeric not null check(end_time>=start_time), event_type text not null, canonical_action text,
  semantic_state text not null check(semantic_state in ('OBSERVED','FALSE','UNKNOWN','NOT_APPLICABLE')),
  confidence numeric check(confidence between 0 and 1), technical_only boolean not null default false,
  analysis_run_id uuid not null references public.semantic_analysis_runs(id), review_status text not null default 'PENDING',
  gold_override_status text not null default 'NONE', created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);

alter table public.asset_scenes add column if not exists source text;
alter table public.asset_scenes add column if not exists processor_version text;
alter table public.asset_scenes add column if not exists configuration_version text;
alter table public.asset_scenes add column if not exists semantic_label text;
alter table public.asset_scenes add column if not exists semantic_state text default 'UNKNOWN';
alter table public.asset_scenes add column if not exists gold_override_status text default 'NONE';
alter table public.asset_keyframes add column if not exists event_id uuid references public.asset_events(id) on delete set null;
alter table public.asset_keyframes add column if not exists source_fingerprint text;
alter table public.asset_keyframes add column if not exists processor_version text;

create table if not exists public.semantic_assertions (
  id uuid primary key default gen_random_uuid(), asset_id uuid not null references public.assets(id) on delete cascade,
  scene_id uuid references public.asset_scenes(id) on delete cascade, event_id uuid references public.asset_events(id) on delete cascade,
  keyframe_id uuid references public.asset_keyframes(id) on delete set null, layer_id text not null references public.semantic_layer_definitions(layer_id),
  subject_type text not null, subject_id uuid, predicate text not null, canonical_concept_code text,
  canonical_concept_type text, value_text text, value_number numeric, value_boolean boolean, value_json jsonb,
  semantic_state text not null check(semantic_state in ('OBSERVED','FALSE','UNKNOWN','NOT_APPLICABLE')),
  confidence numeric check(confidence between 0 and 1), confidence_source text, search_critical boolean not null default false,
  analysis_run_id uuid not null references public.semantic_analysis_runs(id),
  origin text not null check(origin in ('AI_MODEL','DETERMINISTIC_PROCESSOR','DATABASE_METADATA','HUMAN_REVIEW')),
  ontology_version text not null, semantic_spec_version text not null, human_review_status text not null default 'PENDING',
  valid_from timestamptz, valid_to timestamptz, active boolean not null default true,
  superseded_by uuid references public.semantic_assertions(id), source_fingerprint text not null, idempotency_key text not null unique,
  created_at timestamptz not null default now(), check(valid_to is null or valid_from is null or valid_to>=valid_from),
  check(num_nonnulls(value_text,value_number,value_boolean,value_json)<=1)
);

create table if not exists public.semantic_assertion_evidence (
  id uuid primary key default gen_random_uuid(), assertion_id uuid not null references public.semantic_assertions(id) on delete cascade,
  evidence_type text not null check(evidence_type in ('ASSET_LEVEL','SCENE_LEVEL','EVENT_LEVEL','KEYFRAME_LEVEL','TRANSCRIPT','OCR','HUMAN_REVIEW')),
  polarity text not null default 'POSITIVE' check(polarity in ('POSITIVE','NEGATIVE')),
  completeness text not null default 'PARTIAL' check(completeness in ('PARTIAL','COMPLETE')),
  asset_id uuid not null references public.assets(id) on delete cascade, scene_id uuid references public.asset_scenes(id) on delete cascade,
  event_id uuid references public.asset_events(id) on delete cascade, keyframe_id uuid references public.asset_keyframes(id) on delete set null,
  transcript_chunk_id bigint references public.asset_transcript_chunks(id) on delete set null,
  ocr_observation_id uuid references public.ocr_observations(id) on delete set null, region_json jsonb,
  start_time numeric check(start_time is null or start_time>=0), end_time numeric check(end_time is null or start_time is null or end_time>=start_time),
  evidence_score numeric check(evidence_score between 0 and 1), source_fingerprint text not null,
  analysis_run_id uuid not null references public.semantic_analysis_runs(id), created_at timestamptz not null default now()
);

create or replace function public.enforce_search_assertion_evidence() returns trigger language plpgsql security invoker set search_path='' as $$
begin
 if new.search_critical and new.semantic_state='OBSERVED' and not exists(select 1 from public.semantic_assertion_evidence e where e.assertion_id=new.id) then
   raise exception 'search-critical OBSERVED assertion requires evidence';
 end if;
 if new.search_critical and new.semantic_state='FALSE' and not exists(select 1 from public.semantic_assertion_evidence e where e.assertion_id=new.id and e.polarity='NEGATIVE' and e.completeness='COMPLETE') then
   raise exception 'search-critical FALSE assertion requires complete negative evidence';
 end if; return new;
end $$;
create constraint trigger semantic_assertion_evidence_guard after insert or update on public.semantic_assertions
 deferrable initially deferred for each row execute function public.enforce_search_assertion_evidence();

alter table public.asset_transcript_chunks add column if not exists event_id uuid references public.asset_events(id) on delete set null;
alter table public.asset_transcript_chunks add column if not exists speaker_id text;
alter table public.asset_transcript_chunks add column if not exists raw_text text;
alter table public.asset_transcript_chunks add column if not exists normalized_text text;
alter table public.asset_transcript_chunks add column if not exists confidence numeric;
alter table public.asset_transcript_chunks add column if not exists search_status text default 'UNREVIEWED';
alter table public.asset_transcript_chunks add column if not exists source_text_fingerprint text;
alter table public.asset_transcript_chunks add column if not exists provider text;
alter table public.asset_transcript_chunks add column if not exists model text;
alter table public.asset_transcript_chunks add column if not exists version text;
alter table public.ocr_observations add column if not exists event_id uuid references public.asset_events(id) on delete set null;
alter table public.ocr_observations add column if not exists text_track_id uuid;
alter table public.ocr_observations add column if not exists end_time numeric;
alter table public.ocr_observations add column if not exists normalized_bounding_box jsonb;
alter table public.ocr_observations add column if not exists search_status text default 'UNREVIEWED';
alter table public.ocr_observations add column if not exists source_text_fingerprint text;
alter table public.ocr_observations add column if not exists provider text;
alter table public.ocr_observations add column if not exists model text;
alter table public.ocr_observations add column if not exists version text;

create table if not exists public.semantic_narratives (
 id uuid primary key default gen_random_uuid(), asset_id uuid not null references public.assets(id) on delete cascade,
 scene_id uuid references public.asset_scenes(id) on delete cascade, event_id uuid references public.asset_events(id) on delete cascade,
 narrative_type text not null check(narrative_type in ('ASSET_NARRATIVE','SHORT_SEMANTIC_SUMMARY','SEARCH_SUMMARY','SEARCH_SAFE_NARRATIVE','SCENE_NARRATIVE','EVENT_NARRATIVE')),
 text text not null, search_status text not null default 'UNREVIEWED', input_evidence_fingerprint text not null,
 generator_version text not null, configuration_version text, analysis_run_id uuid not null references public.semantic_analysis_runs(id),
 human_review_status text not null default 'PENDING', created_at timestamptz not null default now()
);
create table if not exists public.narrative_claims (
 id uuid primary key default gen_random_uuid(), narrative_id uuid not null references public.semantic_narratives(id) on delete cascade,
 claim_text text not null, modality_source text not null, confidence numeric check(confidence between 0 and 1),
 search_critical boolean not null default false, review_status text not null default 'PENDING'
);
create table if not exists public.narrative_claim_evidence (
 id uuid primary key default gen_random_uuid(),
 claim_id uuid not null references public.narrative_claims(id) on delete cascade,
 assertion_id uuid references public.semantic_assertions(id) on delete cascade,
 evidence_id uuid references public.semantic_assertion_evidence(id) on delete cascade,
 unique(claim_id,assertion_id,evidence_id), check(assertion_id is not null or evidence_id is not null)
);

create table if not exists public.semantic_review_sessions (
 id uuid primary key default gen_random_uuid(), reviewer_id uuid, reviewer_label text not null, status text not null default 'OPEN',
 semantic_spec_version text not null, started_at timestamptz not null default now(), completed_at timestamptz, created_at timestamptz not null default now()
);
create table if not exists public.semantic_review_decisions (
 id uuid primary key default gen_random_uuid(), session_id uuid not null references public.semantic_review_sessions(id),
 asset_id uuid not null references public.assets(id) on delete cascade, layer_id text not null references public.semantic_layer_definitions(layer_id),
 assertion_id uuid references public.semantic_assertions(id), field_path text, original_value jsonb,
 decision text not null check(decision in ('APPROVE_AS_IS','CORRECT','REJECT','CONFIRM_UNKNOWN','NOT_APPLICABLE')),
 human_value jsonb, reason text, reviewer_label text not null, reviewed_at timestamptz not null default now(), revision integer not null default 1 check(revision>0),
 unique(session_id,asset_id,layer_id,assertion_id,field_path,revision)
);
create table if not exists public.semantic_review_revisions (
 id uuid primary key default gen_random_uuid(), decision_id uuid not null references public.semantic_review_decisions(id),
 revision integer not null check(revision>0), decision text not null, human_value jsonb, reason text,
 reviewer_label text not null, created_at timestamptz not null default now(), unique(decision_id,revision)
);

create or replace function public.prevent_semantic_review_mutation() returns trigger language plpgsql security invoker set search_path='' as $$
begin raise exception 'human review history is append-only; create a new revision'; end $$;
create trigger semantic_review_decision_immutable before update or delete on public.semantic_review_decisions
 for each row execute function public.prevent_semantic_review_mutation();
create trigger semantic_review_revision_immutable before update or delete on public.semantic_review_revisions
 for each row execute function public.prevent_semantic_review_mutation();

create table if not exists public.gold_standard_sets (
 id uuid primary key default gen_random_uuid(), code text not null unique, revision integer not null check(revision>0), status text not null check(status in ('DRAFT','SIGNED_OFF','SUPERSEDED')),
 semantic_spec_version text not null, source_fingerprint text not null, gold_fingerprint text, signed_off_at timestamptz, created_at timestamptz not null default now()
);
create table if not exists public.gold_standard_assets (
 id uuid primary key default gen_random_uuid(), gold_set_id uuid not null references public.gold_standard_sets(id), asset_id uuid not null references public.assets(id),
 revision integer not null check(revision>0), source_fingerprint text not null, gold_fingerprint text, status text not null default 'DRAFT',
 created_at timestamptz not null default now(), unique(gold_set_id,asset_id,revision)
);
create table if not exists public.gold_standard_assertions (
 id uuid primary key default gen_random_uuid(), gold_asset_id uuid not null references public.gold_standard_assets(id),
 source_assertion_id uuid references public.semantic_assertions(id), layer_id text not null references public.semantic_layer_definitions(layer_id),
 predicate text not null, semantic_state text not null check(semantic_state in ('OBSERVED','FALSE','UNKNOWN','NOT_APPLICABLE')),
 canonical_concept_code text, value_json jsonb, human_decision_id uuid references public.semantic_review_decisions(id),
 human_reason text, revision integer not null check(revision>0), source_fingerprint text not null, gold_fingerprint text not null,
 active boolean not null default true, superseded_by uuid references public.gold_standard_assertions(id), created_at timestamptz not null default now()
);

create or replace function public.prevent_signed_gold_mutation() returns trigger language plpgsql security invoker set search_path='' as $$
begin if old.status='SIGNED_OFF' then raise exception 'signed-off gold is immutable; create a new revision'; end if; return new; end $$;
create trigger gold_set_immutable before update or delete on public.gold_standard_sets for each row execute function public.prevent_signed_gold_mutation();
create or replace function public.prevent_signed_gold_child_mutation() returns trigger language plpgsql security invoker set search_path='' as $$
declare v_set_id uuid; v_status text;
begin
 v_set_id:=case when tg_table_name='gold_standard_assets' then old.gold_set_id else (select ga.gold_set_id from public.gold_standard_assets ga where ga.id=old.gold_asset_id) end;
 select status into v_status from public.gold_standard_sets where id=v_set_id;
 if v_status='SIGNED_OFF' then raise exception 'signed-off gold children are immutable; create a new gold revision'; end if;
 return old;
end $$;
create trigger gold_asset_immutable before update or delete on public.gold_standard_assets for each row execute function public.prevent_signed_gold_child_mutation();
create trigger gold_assertion_immutable before update or delete on public.gold_standard_assertions for each row execute function public.prevent_signed_gold_child_mutation();

create table if not exists public.asset_search_concepts_v2 (
 id uuid primary key default gen_random_uuid(), asset_id uuid not null references public.assets(id) on delete cascade,
 scene_id uuid references public.asset_scenes(id) on delete cascade, event_id uuid references public.asset_events(id) on delete cascade,
 concept_type text not null, canonical_code text not null, display_text text not null,
 source text not null check(source in ('AI_MODEL','DETERMINISTIC_PROCESSOR','DATABASE_METADATA','HUMAN_REVIEW')),
 semantic_state text not null check(semantic_state in ('OBSERVED','FALSE','UNKNOWN','NOT_APPLICABLE')),
 confidence numeric check(confidence between 0 and 1), search_critical boolean not null default false,
 human_review_status text not null default 'PENDING', analysis_run_id uuid not null references public.semantic_analysis_runs(id), created_at timestamptz not null default now()
);
create table if not exists public.search_document_builds (
 id uuid primary key default gen_random_uuid(), asset_id uuid not null references public.assets(id), scene_id uuid references public.asset_scenes(id),
 event_id uuid references public.asset_events(id), search_document_version text not null, source_semantic_version text not null,
 source_gold_version text, source_fingerprint text not null, document_fingerprint text, status text not null check(status in ('PENDING','READY','STALE','FAILED')),
 created_at timestamptz not null default now(), unique(asset_id,scene_id,event_id,search_document_version,source_fingerprint)
);
create table if not exists public.semantic_embeddings (
 id uuid primary key default gen_random_uuid(), asset_id uuid not null references public.assets(id) on delete cascade,
 scene_id uuid references public.asset_scenes(id) on delete cascade, event_id uuid references public.asset_events(id) on delete cascade,
 transcript_chunk_id bigint references public.asset_transcript_chunks(id) on delete cascade, ocr_observation_id uuid references public.ocr_observations(id) on delete cascade,
 narrative_id uuid references public.semantic_narratives(id) on delete cascade, embedding_scope text not null,
 provider text not null, model text not null, version text not null, dimensions integer not null check(dimensions>0),
 embedding vector, source_text_fingerprint text not null, source_semantic_version text not null,
 analysis_run_id uuid not null references public.semantic_analysis_runs(id), stale boolean not null default false, created_at timestamptz not null default now(),
 check(public.vector_dims(embedding)=dimensions)
);

create index if not exists semantic_runs_asset_idx on public.semantic_analysis_runs(asset_id,created_at desc);
create index if not exists semantic_layers_asset_idx on public.asset_semantic_layers(asset_id,active,layer_id);
create index if not exists semantic_assertions_lookup_idx on public.semantic_assertions(asset_id,layer_id,predicate,active);
create index if not exists semantic_assertions_concept_idx on public.semantic_assertions(canonical_concept_code) where canonical_concept_code is not null;
create index if not exists semantic_assertions_run_idx on public.semantic_assertions(analysis_run_id);
create index if not exists semantic_assertions_search_idx on public.semantic_assertions(search_critical,semantic_state) where active;
create index if not exists semantic_assertions_value_json_gin on public.semantic_assertions using gin(value_json);
create index if not exists semantic_evidence_assertion_idx on public.semantic_assertion_evidence(assertion_id,evidence_type);
create index if not exists semantic_events_asset_time_idx on public.asset_events(asset_id,start_time,end_time);
create index if not exists semantic_review_asset_idx on public.semantic_review_decisions(asset_id,layer_id,reviewed_at desc);
create index if not exists gold_assertions_lookup_idx on public.gold_standard_assertions(gold_asset_id,layer_id,predicate,active);
create index if not exists search_concepts_v2_lookup_idx on public.asset_search_concepts_v2(asset_id,canonical_code,semantic_state);
create index if not exists semantic_embeddings_source_idx on public.semantic_embeddings(asset_id,embedding_scope,stale);

create or replace view public.effective_semantic_assertions with(security_invoker=true) as
select distinct on (a.asset_id,a.layer_id,a.predicate,coalesce(a.subject_id,a.asset_id))
 a.asset_id,a.scene_id,a.event_id,a.keyframe_id,a.layer_id,a.subject_type,a.subject_id,a.predicate,
 coalesce(g.canonical_concept_code,case when d.decision='CORRECT' then d.human_value->>'canonical_concept_code' end,a.canonical_concept_code) canonical_concept_code,
 case when g.id is not null then g.value_json when d.decision='CORRECT' then d.human_value else coalesce(a.value_json,to_jsonb(a.value_text),to_jsonb(a.value_number),to_jsonb(a.value_boolean)) end effective_value,
 coalesce(g.semantic_state,case d.decision when 'CONFIRM_UNKNOWN' then 'UNKNOWN' when 'NOT_APPLICABLE' then 'NOT_APPLICABLE' else a.semantic_state end) semantic_state,
 a.confidence,a.search_critical,a.analysis_run_id,
 case when g.id is not null then 'HUMAN_GOLD' when d.decision in ('CORRECT','APPROVE_AS_IS','CONFIRM_UNKNOWN','NOT_APPLICABLE') then 'HUMAN_APPROVED' when a.human_review_status in ('APPROVED','CORRECTED') then 'APPROVED_AI' else 'UNVERIFIED_AI' end resolution_source
from public.semantic_assertions a
left join public.gold_standard_assets ga on ga.asset_id=a.asset_id and ga.status='SIGNED_OFF'
left join public.gold_standard_assertions g on g.gold_asset_id=ga.id and g.layer_id=a.layer_id and g.predicate=a.predicate and g.active
left join lateral(select rd.* from public.semantic_review_decisions rd where rd.assertion_id=a.id and rd.decision<>'REJECT' order by rd.revision desc,rd.reviewed_at desc limit 1)d on true
where a.active
order by a.asset_id,a.layer_id,a.predicate,coalesce(a.subject_id,a.asset_id),
 case when g.id is not null then 1 when d.id is not null then 2 when a.human_review_status in ('APPROVED','CORRECTED') then 3 else 4 end,a.created_at desc;

create or replace view public.current_asset_semantic_state with(security_invoker=true) as
select a.id asset_id,count(l.id) filter(where l.active) layer_count,
 jsonb_object_agg(l.layer_id,jsonb_build_object('semantic_state',l.semantic_state,'processing_status',l.processing_status,'human_review_status',l.human_review_status)) filter(where l.active) layer_statuses,
 case when count(l.id) filter(where l.active)=18 and bool_and(l.processing_status='COMPLETE') filter(where l.active) then 'READY' else 'NOT_READY' end search_readiness,
 max(l.semantic_spec_version) semantic_spec_version,max(r.source_fingerprint) source_fingerprint
from public.assets a left join public.asset_semantic_layers l on l.asset_id=a.id and l.active
left join public.semantic_analysis_runs r on r.id=l.analysis_run_id group by a.id;

alter table public.semantic_layer_definitions enable row level security;
alter table public.semantic_analysis_runs enable row level security;
alter table public.asset_semantic_layers enable row level security;
alter table public.asset_events enable row level security;
alter table public.semantic_assertions enable row level security;
alter table public.semantic_assertion_evidence enable row level security;
alter table public.semantic_narratives enable row level security;
alter table public.narrative_claims enable row level security;
alter table public.narrative_claim_evidence enable row level security;
alter table public.semantic_review_sessions enable row level security;
alter table public.semantic_review_decisions enable row level security;
alter table public.semantic_review_revisions enable row level security;
alter table public.gold_standard_sets enable row level security;
alter table public.gold_standard_assets enable row level security;
alter table public.gold_standard_assertions enable row level security;
alter table public.asset_search_concepts_v2 enable row level security;
alter table public.search_document_builds enable row level security;
alter table public.semantic_embeddings enable row level security;

-- No client writes. Existing can_access_asset() remains the authorization source.
create policy semantic_assertions_asset_read on public.semantic_assertions for select to authenticated using((select private.can_user_view_asset(asset_id)));
create policy semantic_evidence_asset_read on public.semantic_assertion_evidence for select to authenticated using((select private.can_user_view_asset(asset_id)));
create policy semantic_layers_asset_read on public.asset_semantic_layers for select to authenticated using((select private.can_user_view_asset(asset_id)));
create policy semantic_events_asset_read on public.asset_events for select to authenticated using((select private.can_user_view_asset(asset_id)));
create policy semantic_narratives_asset_read on public.semantic_narratives for select to authenticated using((select private.can_user_view_asset(asset_id)));
create policy search_concepts_v2_asset_read on public.asset_search_concepts_v2 for select to authenticated using((select private.can_user_view_asset(asset_id)));
create policy semantic_runs_asset_read on public.semantic_analysis_runs for select to authenticated using((select private.can_user_view_asset(asset_id)));
create policy semantic_layers_catalog_read on public.semantic_layer_definitions for select to authenticated using(true);
create policy semantic_embeddings_asset_read on public.semantic_embeddings for select to authenticated using((select private.can_user_view_asset(asset_id)));
create policy search_document_builds_asset_read on public.search_document_builds for select to authenticated using((select private.can_user_view_asset(asset_id)));
create policy semantic_review_decisions_authorized_read on public.semantic_review_decisions for select to authenticated using((select private.can_user_view_asset(asset_id)));
create policy gold_assets_authorized_read on public.gold_standard_assets for select to authenticated using((select private.can_user_view_asset(asset_id)));
create policy gold_assertions_authorized_read on public.gold_standard_assertions for select to authenticated using(exists(select 1 from public.gold_standard_assets ga where ga.id=gold_asset_id and (select private.can_user_view_asset(ga.asset_id))));
revoke all on public.semantic_review_sessions,public.semantic_review_decisions,public.semantic_review_revisions,
 public.gold_standard_sets,public.gold_standard_assets,public.gold_standard_assertions from anon,authenticated;
revoke insert,update,delete on public.semantic_analysis_runs,public.asset_semantic_layers,public.asset_events,
 public.semantic_assertions,public.semantic_assertion_evidence,public.semantic_narratives,public.narrative_claims,
 public.narrative_claim_evidence,public.asset_search_concepts_v2,public.search_document_builds,public.semantic_embeddings
 from anon,authenticated;
grant select on public.semantic_layer_definitions,public.semantic_analysis_runs,public.asset_semantic_layers,public.asset_events,
 public.semantic_assertions,public.semantic_assertion_evidence,public.semantic_narratives,public.asset_search_concepts_v2,
 public.search_document_builds,public.semantic_embeddings,public.semantic_review_decisions,public.gold_standard_assets,public.gold_standard_assertions,
 public.effective_semantic_assertions,public.current_asset_semantic_state to authenticated;

commit;
