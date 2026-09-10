-- KDI AI Search V3 Job 2: normalized core schema.
-- Additive only. Preserves all canonical assets and existing embeddings.

begin;

create table public.people (
  id uuid primary key default gen_random_uuid(),
  code text not null unique,
  display_name text not null,
  person_type text not null,
  role text,
  organization text,
  is_verified boolean not null default false,
  verification_source text,
  is_active boolean not null default true,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint people_code_format_check check (code ~ '^[A-Z][A-Z0-9_]*$'),
  constraint people_type_check check (person_type in ('DOCTOR','STAFF','PRESENTER','OTHER')),
  constraint people_metadata_object_check check (jsonb_typeof(metadata)='object')
);

create table public.treatments (
  id uuid primary key default gen_random_uuid(),
  code text not null unique,
  name text not null,
  parent_id uuid references public.treatments(id) on delete restrict,
  level integer not null default 0,
  category text,
  description text,
  is_active boolean not null default true,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint treatments_code_format_check check (code ~ '^[A-Z][A-Z0-9_]*$'),
  constraint treatments_level_check check (level >= 0),
  constraint treatments_not_own_parent_check check (parent_id is null or parent_id <> id),
  constraint treatments_metadata_object_check check (jsonb_typeof(metadata)='object')
);

create table public.treatment_aliases (
  id uuid primary key default gen_random_uuid(),
  treatment_id uuid not null references public.treatments(id) on delete cascade,
  alias text not null,
  normalized_alias text not null,
  alias_type text not null default 'SYNONYM',
  language text not null default 'en',
  is_active boolean not null default true,
  created_at timestamptz not null default now(),
  constraint treatment_aliases_alias_nonblank_check check (btrim(alias) <> ''),
  constraint treatment_aliases_normalized_check check (
    normalized_alias = lower(regexp_replace(btrim(alias), '\s+', ' ', 'g'))
  ),
  constraint treatment_aliases_language_check check (language ~ '^[a-z]{2}(-[A-Z]{2})?$'),
  constraint treatment_aliases_normalized_language_unique unique(normalized_alias,language)
);

create table public.anatomy_terms (
  id uuid primary key default gen_random_uuid(),
  code text not null unique,
  name text not null,
  parent_id uuid references public.anatomy_terms(id) on delete restrict,
  domain text not null,
  description text,
  is_active boolean not null default true,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint anatomy_terms_code_format_check check (code ~ '^[A-Z][A-Z0-9_]*$'),
  constraint anatomy_terms_not_own_parent_check check (parent_id is null or parent_id <> id),
  constraint anatomy_terms_metadata_object_check check (jsonb_typeof(metadata)='object')
);

create table public.actions (
  id uuid primary key default gen_random_uuid(),
  code text not null unique,
  name text not null,
  category text not null,
  description text,
  is_active boolean not null default true,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint actions_code_format_check check (code ~ '^[A-Z][A-Z0-9_]*$'),
  constraint actions_metadata_object_check check (jsonb_typeof(metadata)='object')
);

create table public.locations (
  id uuid primary key default gen_random_uuid(),
  code text not null unique,
  name text not null,
  location_type text not null,
  parent_id uuid references public.locations(id) on delete restrict,
  organization text,
  country text,
  region text,
  city text,
  is_verified boolean not null default false,
  is_active boolean not null default true,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint locations_code_format_check check (code ~ '^[A-Z][A-Z0-9_]*$'),
  constraint locations_not_own_parent_check check (parent_id is null or parent_id <> id),
  constraint locations_metadata_object_check check (jsonb_typeof(metadata)='object')
);

create table public.ai_analysis_runs (
  id uuid primary key default gen_random_uuid(),
  asset_id uuid not null references public.assets(id) on delete cascade,
  analysis_type text not null,
  provider text,
  model_name text,
  model_version text,
  pipeline_version text,
  ontology_version text,
  status text not null default 'QUEUED',
  started_at timestamptz,
  completed_at timestamptz,
  attempt_number integer not null default 1,
  frames_processed integer,
  input_units bigint,
  output_units bigint,
  cost_usd numeric(14,6),
  error_code text,
  error_message text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint ai_analysis_runs_type_check check (analysis_type in ('ASSET_PROFILE','SCENE_DETECTION','VISUAL_ANALYSIS','TRANSCRIPTION','OCR','EMBEDDING','SEARCH_DOCUMENT')),
  constraint ai_analysis_runs_status_check check (status in ('QUEUED','PROCESSING','COMPLETED','FAILED','CANCELLED','SKIPPED')),
  constraint ai_analysis_runs_attempt_check check (attempt_number > 0),
  constraint ai_analysis_runs_nonnegative_check check (
    (frames_processed is null or frames_processed >= 0) and
    (input_units is null or input_units >= 0) and
    (output_units is null or output_units >= 0) and
    (cost_usd is null or cost_usd >= 0)
  ),
  constraint ai_analysis_runs_time_check check (completed_at is null or started_at is null or completed_at >= started_at),
  constraint ai_analysis_runs_metadata_object_check check (jsonb_typeof(metadata)='object')
);

create table public.asset_derivatives (
  id uuid primary key default gen_random_uuid(),
  asset_id uuid not null references public.assets(id) on delete cascade,
  derivative_type text not null,
  storage_provider text not null,
  storage_bucket text,
  storage_path text not null,
  mime_type text,
  file_extension text,
  file_size_bytes bigint,
  width integer,
  height integer,
  duration_seconds numeric(14,3),
  content_hash text,
  generation_status text not null default 'PENDING',
  analysis_run_id uuid references public.ai_analysis_runs(id) on delete set null,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint asset_derivatives_type_check check (derivative_type in ('THUMBNAIL','PREVIEW','PROXY_VIDEO','KEYFRAME_IMAGE','AUDIO_EXTRACTION','WAVEFORM','TEMPORARY_PROCESSING')),
  constraint asset_derivatives_status_check check (generation_status in ('PENDING','PROCESSING','READY','FAILED','EXPIRED')),
  constraint asset_derivatives_size_check check (file_size_bytes is null or file_size_bytes >= 0),
  constraint asset_derivatives_dimensions_check check ((width is null or width > 0) and (height is null or height > 0)),
  constraint asset_derivatives_duration_check check (duration_seconds is null or duration_seconds >= 0),
  constraint asset_derivatives_hash_check check (content_hash is null or content_hash ~ '^[0-9A-Fa-f]{64}$'),
  constraint asset_derivatives_metadata_object_check check (jsonb_typeof(metadata)='object')
);

create table public.asset_access_control (
  asset_id uuid primary key references public.assets(id) on delete cascade,
  classification_status text not null default 'UNCLASSIFIED',
  is_clinical boolean,
  sensitivity_level text not null default 'GENERAL',
  consent_status text not null default 'UNKNOWN',
  consent_reference text,
  internal_usage_status text not null default 'UNKNOWN',
  marketing_usage_status text not null default 'UNKNOWN',
  external_ai_status text not null default 'NOT_REVIEWED',
  requires_clinical_permission boolean,
  download_allowed boolean,
  usage_restrictions text,
  review_status text not null default 'NOT_REVIEWED',
  reviewed_by uuid references auth.users(id) on delete set null,
  reviewed_at timestamptz,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint asset_access_control_classification_check check (classification_status in ('UNCLASSIFIED','AI_SUGGESTED','REVIEW_REQUIRED','VERIFIED')),
  constraint asset_access_control_sensitivity_check check (sensitivity_level in ('GENERAL','INTERNAL','RESTRICTED','CLINICAL','HIGHLY_RESTRICTED')),
  constraint asset_access_control_consent_check check (consent_status in ('UNKNOWN','NOT_REQUIRED','PENDING','CONFIRMED','RESTRICTED','EXPIRED','REVOKED')),
  constraint asset_access_control_internal_check check (internal_usage_status in ('UNKNOWN','ALLOWED','RESTRICTED','NOT_ALLOWED')),
  constraint asset_access_control_marketing_check check (marketing_usage_status in ('UNKNOWN','PENDING','APPROVED','RESTRICTED','NOT_ALLOWED')),
  constraint asset_access_control_external_ai_check check (external_ai_status in ('NOT_REVIEWED','ALLOWED','RESTRICTED','NOT_ALLOWED')),
  constraint asset_access_control_review_check check (review_status in ('NOT_REVIEWED','PENDING','REVIEWED','REQUIRES_REVIEW')),
  constraint asset_access_control_review_fields_check check (
    (reviewed_at is null and reviewed_by is null) or review_status in ('REVIEWED','REQUIRES_REVIEW')
  ),
  constraint asset_access_control_metadata_object_check check (jsonb_typeof(metadata)='object')
);

alter table public.asset_people
  add column person_id uuid references public.people(id) on delete set null;

alter table public.asset_ai_profiles
  add column primary_treatment_id uuid references public.treatments(id) on delete set null,
  add column primary_anatomy_id uuid references public.anatomy_terms(id) on delete set null,
  add column primary_location_id uuid references public.locations(id) on delete set null;

create index people_display_name_idx on public.people(lower(display_name));
create index treatments_parent_id_idx on public.treatments(parent_id) where parent_id is not null;
create index treatments_name_idx on public.treatments(lower(name));
create index treatment_aliases_treatment_id_idx on public.treatment_aliases(treatment_id);
create index anatomy_terms_parent_id_idx on public.anatomy_terms(parent_id) where parent_id is not null;
create index anatomy_terms_name_idx on public.anatomy_terms(lower(name));
create index actions_name_idx on public.actions(lower(name));
create index locations_parent_id_idx on public.locations(parent_id) where parent_id is not null;
create index locations_name_idx on public.locations(lower(name));
create index ai_analysis_runs_asset_created_idx on public.ai_analysis_runs(asset_id,created_at desc);
create index ai_analysis_runs_status_idx on public.ai_analysis_runs(status);
create index ai_analysis_runs_type_idx on public.ai_analysis_runs(analysis_type);
create index asset_derivatives_asset_type_idx on public.asset_derivatives(asset_id,derivative_type);
create index asset_derivatives_status_idx on public.asset_derivatives(generation_status);
create index asset_derivatives_analysis_run_idx on public.asset_derivatives(analysis_run_id) where analysis_run_id is not null;
create index asset_access_control_classification_review_idx on public.asset_access_control(classification_status,review_status);
create index asset_access_control_external_ai_idx on public.asset_access_control(external_ai_status);
create index asset_people_person_id_idx on public.asset_people(person_id) where person_id is not null;
create index asset_ai_profiles_treatment_id_idx on public.asset_ai_profiles(primary_treatment_id) where primary_treatment_id is not null;
create index asset_ai_profiles_anatomy_id_idx on public.asset_ai_profiles(primary_anatomy_id) where primary_anatomy_id is not null;
create index asset_ai_profiles_location_id_idx on public.asset_ai_profiles(primary_location_id) where primary_location_id is not null;

create trigger people_set_updated_at before update on public.people for each row execute function public.set_updated_at();
create trigger treatments_set_updated_at before update on public.treatments for each row execute function public.set_updated_at();
create trigger anatomy_terms_set_updated_at before update on public.anatomy_terms for each row execute function public.set_updated_at();
create trigger actions_set_updated_at before update on public.actions for each row execute function public.set_updated_at();
create trigger locations_set_updated_at before update on public.locations for each row execute function public.set_updated_at();
create trigger ai_analysis_runs_set_updated_at before update on public.ai_analysis_runs for each row execute function public.set_updated_at();
create trigger asset_derivatives_set_updated_at before update on public.asset_derivatives for each row execute function public.set_updated_at();
create trigger asset_access_control_set_updated_at before update on public.asset_access_control for each row execute function public.set_updated_at();

alter table public.people enable row level security;
alter table public.treatments enable row level security;
alter table public.treatment_aliases enable row level security;
alter table public.anatomy_terms enable row level security;
alter table public.actions enable row level security;
alter table public.locations enable row level security;
alter table public.asset_derivatives enable row level security;
alter table public.asset_access_control enable row level security;
alter table public.ai_analysis_runs enable row level security;

revoke all on table
  public.people,public.treatments,public.treatment_aliases,public.anatomy_terms,
  public.actions,public.locations,public.asset_derivatives,
  public.asset_access_control,public.ai_analysis_runs
from public,anon,authenticated;

grant select on table
  public.people,public.treatments,public.treatment_aliases,
  public.anatomy_terms,public.actions,public.locations
to authenticated;

grant all on table
  public.people,public.treatments,public.treatment_aliases,public.anatomy_terms,
  public.actions,public.locations,public.asset_derivatives,
  public.asset_access_control,public.ai_analysis_runs
to service_role;

create policy people_active_app_read on public.people for select to authenticated
  using ((select private.is_active_app_user()));
create policy treatments_active_app_read on public.treatments for select to authenticated
  using ((select private.is_active_app_user()));
create policy treatment_aliases_active_app_read on public.treatment_aliases for select to authenticated
  using ((select private.is_active_app_user()));
create policy anatomy_terms_active_app_read on public.anatomy_terms for select to authenticated
  using ((select private.is_active_app_user()));
create policy actions_active_app_read on public.actions for select to authenticated
  using ((select private.is_active_app_user()));
create policy locations_active_app_read on public.locations for select to authenticated
  using ((select private.is_active_app_user()));

insert into public.asset_access_control(asset_id)
select id from public.assets
on conflict(asset_id) do nothing;

commit;


