create table public.semantic_layer_completeness_evaluations (
  id uuid primary key default gen_random_uuid(),
  evaluation_batch_id uuid not null,
  asset_semantic_layer_id uuid not null references public.asset_semantic_layers(id) on delete restrict,
  asset_id uuid not null references public.assets(id) on delete restrict,
  layer_id text not null references public.semantic_layer_definitions(layer_id) on delete restrict,
  filename text not null,
  previous_status text not null,
  new_status text not null check (new_status in ('COMPLETE','PARTIAL','NOT_EVALUATED')),
  applicable text not null check (applicable in ('TRUE','FALSE','UNKNOWN')),
  semantic_resolution text not null check (semantic_resolution in ('OBSERVED','FALSE','UNKNOWN','NOT_APPLICABLE','MIXED')),
  processing_status text not null,
  requirements_total integer not null check (requirements_total >= 0),
  requirements_satisfied integer not null check (requirements_satisfied >= 0),
  requirements_not_applicable integer not null default 0 check (requirements_not_applicable >= 0),
  requirements_unknown_but_evaluated integer not null default 0 check (requirements_unknown_but_evaluated >= 0),
  requirements_missing integer not null default 0 check (requirements_missing >= 0),
  missing_requirements jsonb not null default '[]'::jsonb check (jsonb_typeof(missing_requirements)='array'),
  evidence_sources jsonb not null default '[]'::jsonb check (jsonb_typeof(evidence_sources)='array'),
  failure_type text check (failure_type is null or failure_type in ('STATUS_BUG','EXTRACTION_GAP','INFRASTRUCTURE_GAP','DATA_QUALITY_LIMITATION')),
  rationale text not null,
  spec_version text not null references public.semantic_specifications(spec_version) on delete restrict,
  spec_fingerprint text not null check (spec_fingerprint ~ '^[0-9a-f]{64}$'),
  evaluator_version text not null,
  decision_fingerprint text not null check (decision_fingerprint ~ '^[0-9a-f]{64}$'),
  evaluation_mode text not null check (evaluation_mode in ('DRY_RUN','APPLIED')),
  evaluated_at timestamptz not null default now(),
  created_at timestamptz not null default now(),
  unique(evaluation_batch_id,asset_id,layer_id,evaluation_mode)
);

create index semantic_layer_completeness_asset_idx
  on public.semantic_layer_completeness_evaluations(asset_id,evaluated_at desc);
create index semantic_layer_completeness_batch_idx
  on public.semantic_layer_completeness_evaluations(evaluation_batch_id,evaluation_mode);

alter table public.semantic_layer_completeness_evaluations enable row level security;
create policy semantic_layer_completeness_read
  on public.semantic_layer_completeness_evaluations for select to authenticated
  using ((select private.can_user_view_asset(asset_id)));
revoke insert,update,delete on public.semantic_layer_completeness_evaluations from anon,authenticated;
grant select on public.semantic_layer_completeness_evaluations to authenticated;

comment on table public.semantic_layer_completeness_evaluations is
  'Immutable, evidence-only completeness decisions against an exact locked semantic specification.';

create or replace function public.reject_semantic_completeness_audit_mutation()
returns trigger language plpgsql set search_path = '' as $$
begin
  raise exception 'semantic completeness audit rows are immutable';
end $$;
create trigger semantic_completeness_audit_immutable
before update or delete on public.semantic_layer_completeness_evaluations
for each row execute function public.reject_semantic_completeness_audit_mutation();
