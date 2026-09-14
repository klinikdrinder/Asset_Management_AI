-- KDI AI Search V3 Job 3: canonical scene, keyframe, and visible-person structure.
-- Additive only. Does not populate media intelligence or alter legacy video segments.

create table public.asset_scenes (
  id uuid primary key default gen_random_uuid(),
  asset_id uuid not null references public.assets(id) on delete cascade,
  scene_index integer not null check (scene_index >= 0),
  start_seconds numeric(14,3) not null check (start_seconds >= 0),
  end_seconds numeric(14,3) not null,
  duration_seconds numeric(14,3) generated always as (end_seconds - start_seconds) stored,
  scene_type text,
  literal_description text,
  short_description text,
  primary_action_id uuid references public.actions(id) on delete set null,
  primary_treatment_id uuid references public.treatments(id) on delete set null,
  primary_anatomy_id uuid references public.anatomy_terms(id) on delete set null,
  primary_location_id uuid references public.locations(id) on delete set null,
  analysis_run_id uuid references public.ai_analysis_runs(id) on delete set null,
  detection_method text,
  confidence numeric(5,4) check (confidence between 0 and 1),
  review_status text not null default 'NOT_REVIEWED' check (review_status in ('NOT_REVIEWED','AI_SUGGESTED','PENDING','REVIEWED','VERIFIED','REJECTED')),
  reviewed_by uuid references auth.users(id) on delete set null,
  reviewed_at timestamptz,
  metadata jsonb not null default '{}'::jsonb check (jsonb_typeof(metadata) = 'object'),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint asset_scenes_valid_interval check (end_seconds > start_seconds),
  constraint asset_scenes_asset_scene_index_key unique (asset_id, scene_index),
  constraint asset_scenes_id_asset_key unique (id, asset_id)
);

create index asset_scenes_asset_time_idx on public.asset_scenes(asset_id, start_seconds, end_seconds);
create index asset_scenes_primary_action_idx on public.asset_scenes(primary_action_id) where primary_action_id is not null;
create index asset_scenes_primary_treatment_idx on public.asset_scenes(primary_treatment_id) where primary_treatment_id is not null;
create index asset_scenes_primary_anatomy_idx on public.asset_scenes(primary_anatomy_id) where primary_anatomy_id is not null;
create index asset_scenes_primary_location_idx on public.asset_scenes(primary_location_id) where primary_location_id is not null;
create index asset_scenes_analysis_run_idx on public.asset_scenes(analysis_run_id) where analysis_run_id is not null;

create table public.asset_keyframes (
  id uuid primary key default gen_random_uuid(),
  asset_id uuid not null references public.assets(id) on delete cascade,
  scene_id uuid not null,
  timestamp_seconds numeric(14,3) not null check (timestamp_seconds >= 0),
  frame_index bigint check (frame_index is null or frame_index >= 0),
  derivative_id uuid references public.asset_derivatives(id) on delete set null,
  selection_reason text,
  visual_description text,
  technical_quality_score numeric(5,4) check (technical_quality_score between 0 and 1),
  semantic_importance_score numeric(5,4) check (semantic_importance_score between 0 and 1),
  analysis_run_id uuid references public.ai_analysis_runs(id) on delete set null,
  is_representative boolean not null default false,
  review_status text not null default 'NOT_REVIEWED' check (review_status in ('NOT_REVIEWED','PENDING','REVIEWED','VERIFIED','REJECTED')),
  metadata jsonb not null default '{}'::jsonb check (jsonb_typeof(metadata) = 'object'),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint asset_keyframes_scene_asset_fkey foreign key (scene_id, asset_id) references public.asset_scenes(id, asset_id) on delete cascade,
  constraint asset_keyframes_id_scene_asset_key unique (id, scene_id, asset_id)
);

create index asset_keyframes_asset_idx on public.asset_keyframes(asset_id);
create index asset_keyframes_scene_time_idx on public.asset_keyframes(scene_id, timestamp_seconds);
create index asset_keyframes_derivative_idx on public.asset_keyframes(derivative_id) where derivative_id is not null;
create index asset_keyframes_analysis_run_idx on public.asset_keyframes(analysis_run_id) where analysis_run_id is not null;

create table public.scene_people (
  id uuid primary key default gen_random_uuid(),
  scene_id uuid not null,
  asset_id uuid not null references public.assets(id) on delete cascade,
  person_id uuid references public.people(id) on delete set null,
  person_role text not null,
  gender text,
  exact_age integer check (exact_age is null or exact_age between 0 and 130),
  age_min integer check (age_min is null or age_min between 0 and 130),
  age_max integer check (age_max is null or age_max between 0 and 130),
  activity_summary text,
  position_summary text,
  identity_status text not null default 'ANONYMOUS' check (identity_status in ('ANONYMOUS','UNVERIFIED','VERIFIED','NOT_APPLICABLE')),
  confidence numeric(5,4) check (confidence between 0 and 1),
  provenance text check (provenance is null or provenance in ('AI_VISUAL','AI_MULTIMODAL','AI_AUDIO','TRANSCRIPT','OCR','SOURCE_METADATA','VERIFIED_FILENAME','VERIFIED_FOLDER','HUMAN_REVIEW','CLINICIAN_VERIFIED')),
  analysis_run_id uuid references public.ai_analysis_runs(id) on delete set null,
  metadata jsonb not null default '{}'::jsonb check (jsonb_typeof(metadata) = 'object'),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint scene_people_age_range check (age_min is null or age_max is null or age_max >= age_min),
  constraint scene_people_verified_identity check (identity_status <> 'VERIFIED' or person_id is not null),
  constraint scene_people_scene_asset_fkey foreign key (scene_id, asset_id) references public.asset_scenes(id, asset_id) on delete cascade,
  constraint scene_people_id_scene_asset_key unique (id, scene_id, asset_id)
);

create index scene_people_asset_idx on public.scene_people(asset_id);
create index scene_people_scene_idx on public.scene_people(scene_id);
create index scene_people_person_idx on public.scene_people(person_id) where person_id is not null;
create index scene_people_role_idx on public.scene_people(person_role);
create index scene_people_analysis_run_idx on public.scene_people(analysis_run_id) where analysis_run_id is not null;

create table public.person_appearances (
  id uuid primary key default gen_random_uuid(),
  asset_id uuid not null references public.assets(id) on delete cascade,
  scene_id uuid not null,
  scene_person_id uuid not null,
  keyframe_id uuid,
  hair_color text,
  hair_length text,
  hair_texture text,
  hair_style text,
  hair_density_appearance text,
  facial_hair text,
  skin_tone_appearance text,
  face_shape text,
  body_build text,
  eyewear text,
  wardrobe text,
  uniform text,
  accessories text,
  makeup text,
  general_visual_description text,
  confidence numeric(5,4) check (confidence between 0 and 1),
  provenance text check (provenance is null or provenance in ('AI_VISUAL','AI_MULTIMODAL','AI_AUDIO','TRANSCRIPT','OCR','SOURCE_METADATA','VERIFIED_FILENAME','VERIFIED_FOLDER','HUMAN_REVIEW','CLINICIAN_VERIFIED')),
  analysis_run_id uuid references public.ai_analysis_runs(id) on delete set null,
  metadata jsonb not null default '{}'::jsonb check (jsonb_typeof(metadata) = 'object'),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint person_appearances_scene_person_fkey foreign key (scene_person_id, scene_id, asset_id) references public.scene_people(id, scene_id, asset_id) on delete cascade,
  constraint person_appearances_keyframe_requires_scene check (keyframe_id is null or scene_id is not null),
  constraint person_appearances_keyframe_fkey foreign key (keyframe_id, scene_id, asset_id) references public.asset_keyframes(id, scene_id, asset_id) on delete cascade
);

create index person_appearances_scene_idx on public.person_appearances(scene_id);
create index person_appearances_scene_person_idx on public.person_appearances(scene_person_id);
create index person_appearances_keyframe_idx on public.person_appearances(keyframe_id) where keyframe_id is not null;
create index person_appearances_analysis_run_idx on public.person_appearances(analysis_run_id) where analysis_run_id is not null;

alter table public.asset_scenes enable row level security;
alter table public.asset_keyframes enable row level security;
alter table public.scene_people enable row level security;
alter table public.person_appearances enable row level security;

revoke all on table public.asset_scenes, public.asset_keyframes, public.scene_people, public.person_appearances from public, anon, authenticated;
grant all on table public.asset_scenes, public.asset_keyframes, public.scene_people, public.person_appearances to service_role;

create trigger asset_scenes_set_updated_at before update on public.asset_scenes for each row execute function public.set_updated_at();
create trigger asset_keyframes_set_updated_at before update on public.asset_keyframes for each row execute function public.set_updated_at();
create trigger scene_people_set_updated_at before update on public.scene_people for each row execute function public.set_updated_at();
create trigger person_appearances_set_updated_at before update on public.person_appearances for each row execute function public.set_updated_at();

;
