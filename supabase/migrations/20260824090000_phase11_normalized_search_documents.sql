begin;

create table public.search_document_build_runs (
  id uuid primary key default gen_random_uuid(),
  status text not null check (status in ('RUNNING','COMPLETE','PARTIAL','FAILED')),
  search_document_version text not null,
  builder_version text not null,
  configuration_version text not null,
  configuration_fingerprint text not null,
  semantic_spec_version text not null,
  ontology_version text not null,
  source_semantic_version text not null,
  source_gold_version text,
  asset_count integer not null default 0 check (asset_count >= 0),
  asset_document_count integer not null default 0 check (asset_document_count >= 0),
  scene_document_count integer not null default 0 check (scene_document_count >= 0),
  event_document_count integer not null default 0 check (event_document_count >= 0),
  errors jsonb not null default '[]'::jsonb,
  started_at timestamptz not null default now(),
  completed_at timestamptz,
  created_at timestamptz not null default now()
);

alter table public.search_document_builds
  add column build_run_id uuid references public.search_document_build_runs(id),
  add column document_type text,
  add column filename text,
  add column media_type text,
  add column start_time numeric,
  add column end_time numeric,
  add column normalized_document jsonb,
  add column search_text text,
  add column search_vector tsvector generated always as (to_tsvector('english',coalesce(search_text,''))) stored,
  add column positive_concepts jsonb not null default '[]'::jsonb,
  add column negative_concepts jsonb not null default '[]'::jsonb,
  add column builder_version text,
  add column configuration_version text,
  add column configuration_fingerprint text,
  add column semantic_spec_version text,
  add column ontology_version text,
  add column source_semantic_fingerprint text,
  add column review_status text,
  add column gold_standard_version text,
  add column human_approved boolean not null default false,
  add column review_required boolean not null default false,
  add column active boolean not null default true,
  add column stale boolean not null default false,
  add column superseded_by uuid references public.search_document_builds(id),
  add column generated_at timestamptz;

alter table public.search_document_builds
  add constraint search_document_type_check check (document_type is null or document_type in ('ASSET','SCENE','EVENT')),
  add constraint search_document_review_check check (review_status is null or review_status in ('AI_UNREVIEWED','HUMAN_APPROVED')),
  add constraint search_document_time_check check (start_time is null or end_time is null or end_time >= start_time),
  add constraint search_document_human_check check (not human_approved or review_status='HUMAN_APPROVED'),
  add constraint search_document_gold_check check (gold_standard_version is null or human_approved);

create unique index search_document_active_identity_idx on public.search_document_builds
  (asset_id,document_type,coalesce(scene_id,'00000000-0000-0000-0000-000000000000'::uuid),coalesce(event_id,'00000000-0000-0000-0000-000000000000'::uuid),search_document_version)
  where active;
create index search_document_fts_idx on public.search_document_builds using gin(search_vector);
create index search_document_asset_type_idx on public.search_document_builds(asset_id,document_type,active,stale);
create index search_document_scene_idx on public.search_document_builds(scene_id) where scene_id is not null;
create index search_document_event_idx on public.search_document_builds(event_id) where event_id is not null;
create index search_document_review_idx on public.search_document_builds(review_status,active,stale);
create index search_document_positive_gin_idx on public.search_document_builds using gin(positive_concepts);

create table public.search_document_concepts (
  id uuid primary key default gen_random_uuid(),
  document_id uuid not null references public.search_document_builds(id) on delete cascade,
  asset_id uuid not null references public.assets(id) on delete cascade,
  scene_id uuid references public.asset_scenes(id) on delete cascade,
  event_id uuid references public.asset_events(id) on delete cascade,
  concept_type text not null,
  canonical_code text not null,
  display_text text not null,
  semantic_state text not null check (semantic_state in ('OBSERVED','FALSE','UNKNOWN','NOT_APPLICABLE')),
  confidence numeric check (confidence between 0 and 1),
  origin text not null check (origin in ('AI_MODEL','DETERMINISTIC_PROCESSOR','DATABASE_METADATA','HUMAN_REVIEW')),
  resolution_source text not null,
  review_status text not null check (review_status in ('AI_UNREVIEWED','HUMAN_APPROVED')),
  assertion_id uuid references public.semantic_assertions(id),
  search_critical boolean not null default false,
  created_at timestamptz not null default now(),
  unique(document_id,concept_type,canonical_code,semantic_state,scene_id,event_id)
);

create table public.search_document_evidence (
  id uuid primary key default gen_random_uuid(),
  document_id uuid not null references public.search_document_builds(id) on delete cascade,
  concept_id uuid references public.search_document_concepts(id) on delete cascade,
  assertion_id uuid references public.semantic_assertions(id),
  assertion_evidence_id uuid references public.semantic_assertion_evidence(id),
  asset_id uuid not null references public.assets(id) on delete cascade,
  scene_id uuid references public.asset_scenes(id) on delete cascade,
  event_id uuid references public.asset_events(id) on delete cascade,
  keyframe_id uuid references public.asset_keyframes(id) on delete cascade,
  transcript_chunk_id bigint references public.asset_transcript_chunks(id) on delete cascade,
  ocr_observation_id uuid references public.ocr_observations(id) on delete cascade,
  evidence_type text not null check (evidence_type in ('ASSET_LEVEL','SCENE_LEVEL','EVENT_LEVEL','KEYFRAME_LEVEL','TRANSCRIPT','OCR','HUMAN_REVIEW','DATABASE_METADATA')),
  created_at timestamptz not null default now()
);

create index search_document_concept_lookup_idx on public.search_document_concepts(canonical_code,concept_type,semantic_state);
create index search_document_concept_asset_idx on public.search_document_concepts(asset_id,document_id);
create index search_document_evidence_doc_idx on public.search_document_evidence(document_id,concept_id);
create index search_document_evidence_asset_idx on public.search_document_evidence(asset_id,scene_id,event_id);

alter table public.search_document_build_runs enable row level security;
alter table public.search_document_concepts enable row level security;
alter table public.search_document_evidence enable row level security;
create policy search_document_runs_no_client_read on public.search_document_build_runs for select to authenticated using(false);
create policy search_document_concepts_asset_read on public.search_document_concepts for select to authenticated using((select private.can_user_view_asset(asset_id)));
create policy search_document_evidence_asset_read on public.search_document_evidence for select to authenticated using((select private.can_user_view_asset(asset_id)));

revoke all on public.search_document_build_runs from anon,authenticated;
revoke insert,update,delete on public.search_document_builds,public.search_document_concepts,public.search_document_evidence from anon,authenticated;
grant select on public.search_document_builds,public.search_document_concepts,public.search_document_evidence to authenticated;

comment on table public.search_document_builds is 'Versioned normalized ASSET, SCENE, and EVENT retrieval documents. Legacy search tables remain comparison-only.';
comment on column public.search_document_builds.review_status is 'AI_UNREVIEWED until a later build is sourced from signed/approved human semantics.';

commit;
