create table if not exists public.asset_ai_profiles (
  asset_id uuid primary key references public.assets(id) on delete cascade,
  title text,
  short_description text,
  detailed_description text,
  category text,
  subcategory text,
  specific_treatment text,
  content_type text,
  procedure_stage text,
  main_activity text,
  secondary_activities text[] not null default '{}',
  setting text,
  body_area text,
  patient_gender text,
  patient_age_exact integer,
  patient_age_min integer,
  patient_age_max integer,
  patient_main_concern text,
  patient_treatment text,
  consultation_topic text,
  patient_activity text,
  patient_position text,
  doctor_name text,
  doctor_role text,
  doctor_activity text,
  number_of_people integer,
  face_visible boolean,
  scalp_visible boolean,
  frontal_hairline_visible boolean,
  treatment_area_visible boolean,
  hairline_markings_visible boolean,
  medical_equipment_visible boolean,
  has_speech boolean,
  spoken_language text,
  spoken_summary text,
  search_concepts text[] not null default '{}',
  search_document text,
  provenance jsonb not null default '{}'::jsonb,
  analysis_status text not null default 'pending',
  analysis_version text,
  analyzed_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint asset_ai_profiles_age_order check (patient_age_min is null or patient_age_max is null or patient_age_min <= patient_age_max)
);

create index if not exists asset_ai_profiles_category_idx on public.asset_ai_profiles(category);
create index if not exists asset_ai_profiles_subcategory_idx on public.asset_ai_profiles(subcategory);
create index if not exists asset_ai_profiles_treatment_idx on public.asset_ai_profiles(specific_treatment);
create index if not exists asset_ai_profiles_content_type_idx on public.asset_ai_profiles(content_type);
create index if not exists asset_ai_profiles_procedure_stage_idx on public.asset_ai_profiles(procedure_stage);
create index if not exists asset_ai_profiles_patient_gender_idx on public.asset_ai_profiles(patient_gender);
create index if not exists asset_ai_profiles_age_range_idx on public.asset_ai_profiles(patient_age_min, patient_age_max);
create index if not exists asset_ai_profiles_search_concepts_gin_idx on public.asset_ai_profiles using gin(search_concepts);

create table if not exists public.asset_people (
  id bigserial primary key,
  asset_id uuid not null references public.assets(id) on delete cascade,
  person_role text not null,
  verified_name text,
  gender text,
  exact_age integer,
  age_min integer,
  age_max integer,
  activity text,
  position text,
  visible_characteristics text[],
  provenance jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint asset_people_age_order check (age_min is null or age_max is null or age_min <= age_max)
);
create index if not exists asset_people_asset_id_idx on public.asset_people(asset_id);
create index if not exists asset_people_role_idx on public.asset_people(person_role);
create index if not exists asset_people_gender_idx on public.asset_people(gender);

create table if not exists public.asset_video_segments (
  id bigserial primary key,
  asset_id uuid not null references public.assets(id) on delete cascade,
  start_seconds numeric(10,3) not null,
  end_seconds numeric(10,3) not null,
  segment_type text,
  description text not null,
  activity text,
  body_area text,
  treatment_context text,
  search_concepts text[] not null default '{}',
  provenance jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint asset_video_segments_time_order check (start_seconds >= 0 and end_seconds > start_seconds)
);
create index if not exists asset_video_segments_asset_id_idx on public.asset_video_segments(asset_id);
create index if not exists asset_video_segments_search_concepts_gin_idx on public.asset_video_segments using gin(search_concepts);

create table if not exists public.asset_transcript_chunks (
  id bigserial primary key,
  asset_id uuid not null references public.assets(id) on delete cascade,
  start_seconds numeric(10,3),
  end_seconds numeric(10,3),
  speaker_role text,
  language text,
  transcript_text text not null,
  summary text,
  topics text[] not null default '{}',
  transcription_status text not null default 'pending',
  provenance jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint asset_transcript_chunks_time_order check (start_seconds is null or end_seconds is null or (start_seconds >= 0 and end_seconds > start_seconds))
);
create index if not exists asset_transcript_chunks_asset_id_idx on public.asset_transcript_chunks(asset_id);
create index if not exists asset_transcript_chunks_topics_gin_idx on public.asset_transcript_chunks using gin(topics);

create table if not exists public.asset_search_concepts (
  id bigserial primary key,
  asset_id uuid not null references public.assets(id) on delete cascade,
  concept text not null,
  concept_type text,
  normalized_concept text,
  provenance_type text,
  confidence numeric(5,4),
  created_at timestamptz not null default now(),
  unique(asset_id, concept)
);
create index if not exists asset_search_concepts_asset_id_idx on public.asset_search_concepts(asset_id);
create index if not exists asset_search_concepts_normalized_idx on public.asset_search_concepts(normalized_concept);

create table if not exists public.asset_metadata_assertions (
  id bigserial primary key,
  asset_id uuid not null references public.assets(id) on delete cascade,
  field_name text not null,
  field_value jsonb,
  source_type text not null,
  confidence numeric(5,4),
  is_authoritative boolean not null default false,
  evidence text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists asset_metadata_assertions_asset_id_idx on public.asset_metadata_assertions(asset_id);
create index if not exists asset_metadata_assertions_field_name_idx on public.asset_metadata_assertions(field_name);
create index if not exists asset_metadata_assertions_authoritative_idx on public.asset_metadata_assertions(asset_id, field_name, is_authoritative);

alter table public.asset_ai_profiles enable row level security;
alter table public.asset_people enable row level security;
alter table public.asset_video_segments enable row level security;
alter table public.asset_transcript_chunks enable row level security;
alter table public.asset_search_concepts enable row level security;
alter table public.asset_metadata_assertions enable row level security;

create policy asset_ai_profiles_individual_read on public.asset_ai_profiles for select to authenticated using ((select private.is_active_app_user()));
create policy asset_people_individual_read on public.asset_people for select to authenticated using ((select private.is_active_app_user()));
create policy asset_video_segments_individual_read on public.asset_video_segments for select to authenticated using ((select private.is_active_app_user()));
create policy asset_transcript_chunks_individual_read on public.asset_transcript_chunks for select to authenticated using ((select private.is_active_app_user()));
create policy asset_search_concepts_individual_read on public.asset_search_concepts for select to authenticated using ((select private.is_active_app_user()));
create policy asset_metadata_assertions_individual_read on public.asset_metadata_assertions for select to authenticated using ((select private.is_active_app_user()));;
