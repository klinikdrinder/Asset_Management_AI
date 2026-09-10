alter table public.semantic_narratives
  add column semantic_spec_version text,
  add column semantic_spec_fingerprint text,
  add column narrative_fingerprint text,
  add column active boolean not null default true,
  add column stale boolean not null default false,
  add column superseded_by uuid references public.semantic_narratives(id),
  add column updated_at timestamptz not null default now();

alter table public.search_document_builds
  add column semantic_spec_fingerprint text;

alter table public.semantic_embeddings
  add column semantic_spec_fingerprint text;

alter table public.semantic_analysis_runs
  add column semantic_spec_fingerprint text,
  add column metadata jsonb not null default '{}'::jsonb;

create unique index semantic_narratives_active_asset_type_idx
  on public.semantic_narratives(asset_id,narrative_type)
  where active and scene_id is null and event_id is null;

create table public.semantic_remediation_model_calls (
  id uuid primary key default gen_random_uuid(),
  remediation_batch_id uuid not null,
  asset_id uuid not null references public.assets(id) on delete restrict,
  layer_id text not null references public.semantic_layer_definitions(layer_id) on delete restrict,
  purpose text not null,
  provider text not null,
  model text not null,
  model_version text,
  started_at timestamptz not null,
  completed_at timestamptz not null,
  duration_ms bigint not null check(duration_ms >= 0),
  input_tokens bigint,
  output_tokens bigint,
  cost_amount numeric,
  cost_currency text,
  unavailable_reason text,
  spec_version text not null references public.semantic_specifications(spec_version) on delete restrict,
  spec_fingerprint text not null,
  created_at timestamptz not null default now(),
  unique(remediation_batch_id,asset_id,layer_id,purpose)
);

alter table public.semantic_remediation_model_calls enable row level security;
create policy semantic_remediation_model_calls_read
  on public.semantic_remediation_model_calls for select to authenticated
  using ((select private.can_user_view_asset(asset_id)));
revoke insert,update,delete on public.semantic_remediation_model_calls from anon,authenticated;
grant select on public.semantic_remediation_model_calls to authenticated;

comment on column public.semantic_narratives.semantic_spec_fingerprint is
  'Exact locked semantic specification fingerprint used to generate and validate this narrative.';
comment on column public.search_document_builds.semantic_spec_fingerprint is
  'Exact locked semantic specification fingerprint used for this search document build.';
comment on column public.semantic_embeddings.semantic_spec_fingerprint is
  'Exact locked semantic specification fingerprint used for this embedding representation.';
comment on table public.semantic_remediation_model_calls is
  'Actual model-call lineage for selective semantic remediation; unavailable token/cost values remain NULL with a reason.';
