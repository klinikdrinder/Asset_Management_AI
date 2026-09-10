-- KDI AI Search V3 Job 9: complete semantic-layer core without deleting existing intelligence.

-- 1) Let still images participate in the same scene intelligence model as videos.
alter table public.asset_scenes drop constraint if exists asset_scenes_valid_interval;
alter table public.asset_scenes
  add constraint asset_scenes_valid_interval
  check (
    end_seconds > start_seconds
    or (
      scene_type = 'STILL_IMAGE'
      and start_seconds = 0
      and end_seconds = 0
      and coalesce(duration_seconds,0) = 0
    )
  );

-- 2) Explicit technical/business metadata layers instead of burying important fields in JSON.
create table if not exists public.asset_technical_metadata (
  asset_id uuid primary key references public.assets(id) on delete cascade,
  width_px integer check (width_px is null or width_px > 0),
  height_px integer check (height_px is null or height_px > 0),
  aspect_ratio numeric check (aspect_ratio is null or aspect_ratio > 0),
  orientation text check (orientation is null or orientation in ('PORTRAIT','LANDSCAPE','SQUARE','PANORAMIC','UNKNOWN')),
  duration_seconds numeric check (duration_seconds is null or duration_seconds >= 0),
  fps numeric check (fps is null or fps > 0),
  codec text,
  camera_make text,
  camera_model text,
  capture_device text,
  captured_at timestamptz,
  rotation_degrees integer,
  has_audio boolean,
  audio_codec text,
  sample_rate_hz integer,
  exif jsonb not null default '{}'::jsonb check (jsonb_typeof(exif)='object'),
  technical_quality_score numeric check (technical_quality_score is null or (technical_quality_score between 0 and 1)),
  provenance text,
  analysis_run_id uuid references public.ai_analysis_runs(id) on delete set null,
  metadata jsonb not null default '{}'::jsonb check (jsonb_typeof(metadata)='object'),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.asset_context (
  asset_id uuid primary key references public.assets(id) on delete cascade,
  clinic text,
  organization text,
  country text,
  state_region text,
  city text,
  location_id uuid references public.locations(id) on delete set null,
  campaign text,
  source_folder text,
  photographer text,
  capture_context text,
  content_owner text,
  notes text,
  provenance text,
  metadata jsonb not null default '{}'::jsonb check (jsonb_typeof(metadata)='object'),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- 3) A formal ontology/layer catalog plus per-asset completeness ledger.
create table if not exists public.semantic_layer_catalog (
  layer_code text primary key,
  layer_order integer not null unique check (layer_order > 0),
  layer_name text not null,
  scope text not null check (scope in ('ALL','IMAGE','VIDEO','VIDEO_AUDIO','OPTIONAL')),
  required_by_default boolean not null default true,
  description text not null,
  ontology_version text not null default 'KDI_SEMANTIC_V2',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.asset_layer_status (
  asset_id uuid not null references public.assets(id) on delete cascade,
  layer_code text not null references public.semantic_layer_catalog(layer_code) on delete cascade,
  status text not null default 'NOT_STARTED' check (status in ('NOT_STARTED','QUEUED','PROCESSING','PARTIAL','COMPLETE','REVIEW_REQUIRED','VERIFIED','FAILED','NOT_APPLICABLE')),
  coverage_score numeric not null default 0 check (coverage_score between 0 and 1),
  evidence_count integer not null default 0 check (evidence_count >= 0),
  analysis_run_id uuid references public.ai_analysis_runs(id) on delete set null,
  analyzed_at timestamptz,
  last_error text,
  metadata jsonb not null default '{}'::jsonb check (jsonb_typeof(metadata)='object'),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  primary key (asset_id, layer_code)
);
create index if not exists asset_layer_status_status_idx on public.asset_layer_status(status,layer_code);
create index if not exists asset_layer_status_asset_idx on public.asset_layer_status(asset_id,status);

-- 4) Controlled clinical concept definitions. AI observations remain distinct from clinician verification.
create table if not exists public.clinical_observation_definitions (
  id uuid primary key default gen_random_uuid(),
  code text not null unique,
  domain text not null,
  label text not null,
  anatomy_code text,
  value_kind text not null check (value_kind in ('BOOLEAN','TEXT','NUMBER','ENUM','JSON')),
  allowed_values text[],
  ai_observable boolean not null default true,
  requires_clinician_verification boolean not null default false,
  description text,
  is_active boolean not null default true,
  metadata jsonb not null default '{}'::jsonb check (jsonb_typeof(metadata)='object'),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
alter table public.clinical_observations add column if not exists definition_id uuid;
do $$ begin
  if not exists (select 1 from pg_constraint where conname='clinical_observations_definition_id_fkey') then
    alter table public.clinical_observations
      add constraint clinical_observations_definition_id_fkey
      foreign key (definition_id) references public.clinical_observation_definitions(id) on delete set null;
  end if;
end $$;
create index if not exists clinical_observations_definition_idx on public.clinical_observations(definition_id);

-- 5) Controlled interaction ontology.
create table if not exists public.relationship_types (
  id uuid primary key default gen_random_uuid(),
  code text not null unique,
  name text not null,
  category text not null,
  description text,
  is_active boolean not null default true,
  metadata jsonb not null default '{}'::jsonb check (jsonb_typeof(metadata)='object'),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
alter table public.scene_relationships add column if not exists relationship_type_id uuid;
do $$ begin
  if not exists (select 1 from pg_constraint where conname='scene_relationships_relationship_type_id_fkey') then
    alter table public.scene_relationships
      add constraint scene_relationships_relationship_type_id_fkey
      foreign key (relationship_type_id) references public.relationship_types(id) on delete set null;
  end if;
end $$;
create index if not exists scene_relationships_type_id_idx on public.scene_relationships(relationship_type_id);

-- 6) Authorized identity reference gallery. Kept locked behind RLS by default.
create table if not exists public.person_reference_assets (
  id uuid primary key default gen_random_uuid(),
  person_id uuid not null references public.people(id) on delete cascade,
  asset_id uuid references public.assets(id) on delete set null,
  reference_type text not null default 'FACE' check (reference_type in ('FACE','VOICE','FULL_BODY','OTHER')),
  consent_status text not null default 'NOT_REVIEWED' check (consent_status in ('NOT_REVIEWED','APPROVED','RESTRICTED','REVOKED')),
  is_primary boolean not null default false,
  is_active boolean not null default true,
  provenance text,
  metadata jsonb not null default '{}'::jsonb check (jsonb_typeof(metadata)='object'),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists person_reference_assets_person_idx on public.person_reference_assets(person_id,is_active);

create table if not exists public.person_identity_embeddings (
  id uuid primary key default gen_random_uuid(),
  person_id uuid not null references public.people(id) on delete cascade,
  reference_asset_id uuid references public.person_reference_assets(id) on delete cascade,
  provider text not null,
  model_name text not null,
  model_version text not null,
  embedding_dimensions integer not null check (embedding_dimensions > 0 and embedding_dimensions <= 2000),
  embedding vector not null,
  source_fingerprint text,
  is_active boolean not null default true,
  embedded_at timestamptz not null default now(),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (vector_dims(embedding)=embedding_dimensions)
);
create index if not exists person_identity_embeddings_person_idx on public.person_identity_embeddings(person_id,is_active);

-- 7) Make asset embeddings genuinely multi-layer instead of text-only/1024-only.
alter table public.asset_embeddings add column if not exists embedding_type text not null default 'SEMANTIC_TEXT';
alter table public.asset_embeddings drop constraint if exists asset_embeddings_dimensions_check;
do $$ begin
  if not exists (select 1 from pg_constraint where conname='asset_embeddings_dimensions_flexible_check') then
    alter table public.asset_embeddings add constraint asset_embeddings_dimensions_flexible_check
      check (embedding_dimensions > 0 and embedding_dimensions <= 2000);
  end if;
  if not exists (select 1 from pg_constraint where conname='asset_embeddings_dimensions_match') then
    alter table public.asset_embeddings add constraint asset_embeddings_dimensions_match
      check (vector_dims(embedding)=embedding_dimensions);
  end if;
end $$;
alter table public.asset_embeddings drop constraint if exists asset_embeddings_provider_model_version_unique;
do $$ begin
  if not exists (select 1 from pg_constraint where conname='asset_embeddings_type_provider_model_version_unique') then
    alter table public.asset_embeddings add constraint asset_embeddings_type_provider_model_version_unique
      unique (asset_id,embedding_type,embedding_provider,embedding_model,embedding_version);
  end if;
end $$;

-- 8) Multiple scene/keyframe embedding channels for hybrid retrieval.
alter table public.scene_embeddings drop constraint if exists scene_embeddings_embedding_type_check;
alter table public.scene_embeddings add constraint scene_embeddings_embedding_type_check
  check (embedding_type in ('VISUAL','IDENTITY','CLINICAL','ACTION','SCENE','ENVIRONMENT','COMPOSITION','MARKETING','SEMANTIC_TEXT','NARRATIVE','AUDIO','OCR'));
alter table public.keyframe_embeddings drop constraint if exists keyframe_embeddings_embedding_type_check;
alter table public.keyframe_embeddings add constraint keyframe_embeddings_embedding_type_check
  check (embedding_type in ('VISUAL','IDENTITY','CLINICAL','ACTION','SCENE','ENVIRONMENT','COMPOSITION','MARKETING','SEMANTIC_TEXT','NARRATIVE','OCR'));

-- 9) RLS defense-in-depth on all new exposed-schema tables. No permissive policies are added here.
alter table public.asset_technical_metadata enable row level security;
alter table public.asset_context enable row level security;
alter table public.semantic_layer_catalog enable row level security;
alter table public.asset_layer_status enable row level security;
alter table public.clinical_observation_definitions enable row level security;
alter table public.relationship_types enable row level security;
alter table public.person_reference_assets enable row level security;
alter table public.person_identity_embeddings enable row level security;
;
