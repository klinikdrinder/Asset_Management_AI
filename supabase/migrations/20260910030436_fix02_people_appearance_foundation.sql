-- KDI FIX 2: additive People + Appearance structured-search foundation.
-- No cohort backfill is performed by this migration.

create table public.person_tracks (
  id uuid primary key default gen_random_uuid(),
  asset_id uuid not null references public.assets(id) on delete cascade,
  track_key text not null,
  tracking_status text not null default 'UNVERIFIED'
    check (tracking_status in ('UNVERIFIED','EVIDENCE_LINKED','HUMAN_VERIFIED','REJECTED')),
  confidence numeric(5,4) check (confidence is null or confidence between 0 and 1),
  source_type text not null
    check (source_type in ('VISUAL','OCR','TRANSCRIPT','METADATA','HUMAN_REVIEW','DERIVED_ASSERTION')),
  model_name text,
  model_version text,
  semantic_run_id uuid references public.semantic_analysis_runs(id) on delete set null,
  evidence jsonb not null default '[]'::jsonb check (jsonb_typeof(evidence) = 'array'),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (id, asset_id),
  unique (asset_id, track_key)
);

alter table public.scene_people
  add column person_track_id uuid,
  add column canonical_person_role text,
  add column clinician_identity_id uuid references public.people(id) on delete set null,
  add column gender_presentation text,
  add column apparent_age_min smallint,
  add column apparent_age_max smallint,
  add column apparent_age_confidence numeric(5,4),
  add column face_visibility text,
  add column scalp_visibility text,
  add column body_orientation text,
  add column person_confidence numeric(5,4),
  add column source_type text,
  add column model_name text,
  add column model_version text,
  add column semantic_run_id uuid references public.semantic_analysis_runs(id) on delete set null,
  add column authority_rank smallint not null default 20,
  add column active boolean not null default true,
  add column superseded_by uuid references public.scene_people(id) on delete set null;

alter table public.scene_people
  add constraint scene_people_track_asset_fkey foreign key (person_track_id, asset_id)
    references public.person_tracks(id, asset_id) on delete set null,
  add constraint scene_people_canonical_role_check check (canonical_person_role is null or canonical_person_role in ('PATIENT','DOCTOR','CLINICIAN','STAFF','PRESENTER','OTHER','UNKNOWN')),
  add constraint scene_people_gender_presentation_check check (gender_presentation is null or gender_presentation in ('MALE','FEMALE','AMBIGUOUS','UNKNOWN')),
  add constraint scene_people_apparent_age_min_check check (apparent_age_min is null or apparent_age_min between 0 and 130),
  add constraint scene_people_apparent_age_max_check check (apparent_age_max is null or apparent_age_max between 0 and 130),
  add constraint scene_people_apparent_age_range_check check (apparent_age_min is null or apparent_age_max is null or apparent_age_min <= apparent_age_max),
  add constraint scene_people_apparent_age_pair_check check ((apparent_age_min is null) = (apparent_age_max is null)),
  add constraint scene_people_apparent_age_confidence_check check (apparent_age_confidence is null or apparent_age_confidence between 0 and 1),
  add constraint scene_people_face_visibility_check check (face_visibility is null or face_visibility in ('CLEAR','PARTIAL','OCCLUDED','NOT_VISIBLE','UNKNOWN')),
  add constraint scene_people_scalp_visibility_check check (scalp_visibility is null or scalp_visibility in ('CLEAR','PARTIAL','OCCLUDED','NOT_VISIBLE','UNKNOWN')),
  add constraint scene_people_body_orientation_check check (body_orientation is null or body_orientation in ('FRONT','BACK','LEFT_PROFILE','RIGHT_PROFILE','THREE_QUARTER','MIXED','UNKNOWN')),
  add constraint scene_people_person_confidence_check check (person_confidence is null or person_confidence between 0 and 1),
  add constraint scene_people_source_type_check check (source_type is null or source_type in ('VISUAL','OCR','TRANSCRIPT','METADATA','HUMAN_REVIEW','DERIVED_ASSERTION')),
  add constraint scene_people_authority_rank_check check (authority_rank between 0 and 100),
  add constraint scene_people_not_self_superseded_check check (superseded_by is null or superseded_by <> id);

alter table public.person_appearances
  add column canonical_hair_color text,
  add column canonical_hair_length text,
  add column hair_density text,
  add column hairline_pattern text,
  add column clothing_type text,
  add column clothing_color text,
  add column posture text,
  add column ppe text[] not null default '{}'::text[],
  add column appearance_confidence numeric(5,4),
  add column source_type text,
  add column model_name text,
  add column model_version text,
  add column semantic_run_id uuid references public.semantic_analysis_runs(id) on delete set null,
  add column authority_rank smallint not null default 20,
  add column materialization_key text,
  add column active boolean not null default true,
  add column superseded_by uuid references public.person_appearances(id) on delete set null;

alter table public.person_appearances
  add constraint person_appearances_hair_color_check check (canonical_hair_color is null or canonical_hair_color in ('BLACK','DARK_BROWN','BROWN','LIGHT_BROWN','BLONDE','GRAY','WHITE','RED','DYED_OTHER','MIXED','UNKNOWN')),
  add constraint person_appearances_hair_length_check check (canonical_hair_length is null or canonical_hair_length in ('SHAVED','VERY_SHORT','SHORT','MEDIUM','LONG','VERY_LONG','UNKNOWN')),
  add constraint person_appearances_hair_density_check check (hair_density is null or hair_density in ('FULL','MILD_THINNING','THINNING','SEVERE_THINNING','BALD','UNKNOWN')),
  add constraint person_appearances_hairline_pattern_check check (hairline_pattern is null or hairline_pattern in ('NORMAL','MATURE','RECEDING','FRONTAL_RECESSION','TEMPORAL_RECESSION','M_SHAPED','DIFFUSE_FRONTAL_THINNING','POST_TRANSPLANT','UNKNOWN')),
  add constraint person_appearances_clothing_type_check check (clothing_type is null or clothing_type in ('SHIRT','TSHIRT','POLO','BLOUSE','DRESS','JACKET','SCRUBS','LAB_COAT','HIJAB','CAP','OTHER','UNKNOWN')),
  add constraint person_appearances_clothing_color_check check (clothing_color is null or clothing_color in ('BLACK','WHITE','GRAY','BLUE','NAVY','LIGHT_BLUE','GREEN','RED','PINK','PURPLE','YELLOW','ORANGE','BROWN','BEIGE','MULTICOLOR','UNKNOWN')),
  add constraint person_appearances_posture_check check (posture is null or posture in ('STANDING','SEATED','LYING','LEANING','WALKING','UNKNOWN')),
  add constraint person_appearances_ppe_check check (ppe <@ array['GLOVES','MASK','EYE_PROTECTION','CAP','GOWN','OTHER','UNKNOWN']::text[]),
  add constraint person_appearances_confidence_v2_check check (appearance_confidence is null or appearance_confidence between 0 and 1),
  add constraint person_appearances_source_type_check check (source_type is null or source_type in ('VISUAL','OCR','TRANSCRIPT','METADATA','HUMAN_REVIEW','DERIVED_ASSERTION')),
  add constraint person_appearances_authority_rank_check check (authority_rank between 0 and 100),
  add constraint person_appearances_not_self_superseded_check check (superseded_by is null or superseded_by <> id);

create table public.person_attribute_evidence (
  id uuid primary key default gen_random_uuid(),
  asset_id uuid not null references public.assets(id) on delete cascade,
  scene_id uuid not null,
  scene_person_id uuid not null,
  appearance_id uuid references public.person_appearances(id) on delete cascade,
  keyframe_id uuid,
  assertion_id uuid references public.semantic_assertions(id) on delete restrict,
  attribute_name text not null,
  attribute_value jsonb not null,
  confidence numeric(5,4) not null check (confidence between 0 and 1),
  source_type text not null check (source_type in ('VISUAL','OCR','TRANSCRIPT','METADATA','HUMAN_REVIEW','DERIVED_ASSERTION')),
  model_name text,
  model_version text,
  semantic_run_id uuid references public.semantic_analysis_runs(id) on delete set null,
  authority_rank smallint not null check (authority_rank between 0 and 100),
  materialization_key text not null unique,
  active boolean not null default true,
  created_at timestamptz not null default now(),
  constraint person_attribute_evidence_scene_person_fkey foreign key (scene_person_id, scene_id, asset_id)
    references public.scene_people(id, scene_id, asset_id) on delete cascade,
  constraint person_attribute_evidence_keyframe_fkey foreign key (keyframe_id, scene_id, asset_id)
    references public.asset_keyframes(id, scene_id, asset_id) on delete restrict
);

create index person_tracks_asset_idx on public.person_tracks(asset_id);
create index scene_people_track_idx on public.scene_people(person_track_id) where person_track_id is not null;
create index scene_people_canonical_search_idx on public.scene_people(canonical_person_role, gender_presentation, apparent_age_min, apparent_age_max)
  where active and superseded_by is null;
create index person_appearances_scene_person_active_idx on public.person_appearances(scene_person_id)
  where active and superseded_by is null;
create unique index person_appearances_materialization_key_active_uidx on public.person_appearances(materialization_key)
  where materialization_key is not null and active and superseded_by is null;
create index person_appearances_canonical_search_idx on public.person_appearances(hairline_pattern, clothing_color, clothing_type, scene_person_id)
  where active and superseded_by is null;
create index person_attribute_evidence_person_idx on public.person_attribute_evidence(scene_person_id, attribute_name)
  where active;
create index person_attribute_evidence_appearance_idx on public.person_attribute_evidence(appearance_id)
  where appearance_id is not null and active;

alter table public.person_tracks enable row level security;
alter table public.person_attribute_evidence enable row level security;
revoke all on table public.person_tracks, public.person_attribute_evidence from public, anon, authenticated;
grant all on table public.person_tracks, public.person_attribute_evidence to service_role;

create view public.person_appearance_search_v1
with (security_invoker = true)
as
select
  sp.asset_id,
  sp.scene_id,
  sp.id as person_id,
  sp.person_track_id,
  coalesce(sp.canonical_person_role,
    case sp.person_role when 'PATIENT_LIKE' then 'PATIENT' when 'CLINICIAN_LIKE' then 'CLINICIAN'
      when 'STAFF_LIKE' then 'STAFF' when 'SUBJECT' then 'OTHER' else sp.person_role end) as person_role,
  sp.clinician_identity_id,
  coalesce(sp.gender_presentation, sp.gender, 'UNKNOWN') as gender_presentation,
  coalesce(sp.apparent_age_min, sp.age_min) as apparent_age_min,
  coalesce(sp.apparent_age_max, sp.age_max) as apparent_age_max,
  coalesce(sp.apparent_age_confidence, sp.confidence) as apparent_age_confidence,
  sp.face_visibility,
  sp.scalp_visibility,
  sp.body_orientation,
  coalesce(sp.person_confidence, sp.confidence) as person_confidence,
  pa.id as appearance_id,
  coalesce(pa.canonical_hair_color, upper(replace(pa.hair_color, ' ', '_'))) as hair_color,
  coalesce(pa.canonical_hair_length, upper(replace(pa.hair_length, ' ', '_'))) as hair_length,
  coalesce(pa.hair_density, upper(replace(pa.hair_density_appearance, ' ', '_'))) as hair_density,
  pa.hairline_pattern,
  pa.facial_hair,
  pa.clothing_type,
  pa.clothing_color,
  pa.posture,
  pa.ppe,
  coalesce(pa.appearance_confidence, pa.confidence) as appearance_confidence,
  greatest(sp.authority_rank, coalesce(pa.authority_rank, 0)) as authority_rank,
  coalesce(pa.source_type, sp.source_type,
    case coalesce(pa.provenance, sp.provenance)
      when 'AI_VISUAL' then 'VISUAL' when 'AI_MULTIMODAL' then 'VISUAL'
      when 'TRANSCRIPT' then 'TRANSCRIPT' when 'OCR' then 'OCR'
      when 'HUMAN_REVIEW' then 'HUMAN_REVIEW' when 'CLINICIAN_VERIFIED' then 'HUMAN_REVIEW'
      else 'DERIVED_ASSERTION' end) as source_type,
  coalesce(pa.semantic_run_id, sp.semantic_run_id) as semantic_run_id
from public.scene_people sp
left join lateral (
  select x.* from public.person_appearances x
  where x.scene_person_id = sp.id and x.scene_id = sp.scene_id and x.asset_id = sp.asset_id
    and x.active and x.superseded_by is null
  order by x.authority_rank desc, x.updated_at desc, x.id
  limit 1
) pa on true
where sp.active and sp.superseded_by is null;

revoke all on table public.person_appearance_search_v1 from public, anon, authenticated;
grant select on table public.person_appearance_search_v1 to service_role;

create trigger person_tracks_set_updated_at before update on public.person_tracks
for each row execute function public.set_updated_at();

comment on view public.person_appearance_search_v1 is
  'Fix 2 same-person/same-scene structured access contract. Service-only; production ranking is not connected in Fix 2.';
