-- KDI AI Search V3 Job 3: normalized semantic, clinical, production, and marketing layers.

create table public.scene_treatments (
 id uuid primary key default gen_random_uuid(), scene_id uuid not null, asset_id uuid not null references public.assets(id) on delete cascade,
 treatment_id uuid not null references public.treatments(id) on delete restrict,
 relationship_type text not null check (relationship_type in ('VISIBLE_PROCEDURE','DISCUSSED','PLANNED','PRE_PROCEDURE','DURING_PROCEDURE','POST_PROCEDURE','FOLLOW_UP','CONTEXT_ONLY')),
 confidence numeric(5,4) check (confidence between 0 and 1), provenance text check (provenance is null or provenance in ('AI_VISUAL','AI_MULTIMODAL','AI_AUDIO','TRANSCRIPT','OCR','SOURCE_METADATA','VERIFIED_FILENAME','VERIFIED_FOLDER','HUMAN_REVIEW','CLINICIAN_VERIFIED')),
 analysis_run_id uuid references public.ai_analysis_runs(id) on delete set null, is_primary boolean not null default false, created_at timestamptz not null default now(),
 constraint scene_treatments_scene_asset_fkey foreign key(scene_id,asset_id) references public.asset_scenes(id,asset_id) on delete cascade,
 constraint scene_treatments_unique unique(scene_id,treatment_id,relationship_type)
);
create index scene_treatments_asset_idx on public.scene_treatments(asset_id); create index scene_treatments_treatment_idx on public.scene_treatments(treatment_id); create index scene_treatments_run_idx on public.scene_treatments(analysis_run_id) where analysis_run_id is not null;

create table public.scene_anatomy (
 id uuid primary key default gen_random_uuid(), scene_id uuid not null, asset_id uuid not null references public.assets(id) on delete cascade,
 anatomy_id uuid not null references public.anatomy_terms(id) on delete restrict,
 relationship_type text not null check (relationship_type in ('VISIBLE','DISCUSSED','TREATED','EXAMINED','MARKED','FOCUS_AREA')),
 visibility text check (visibility is null or visibility in ('VISIBLE','PARTIAL','OCCLUDED','NOT_VISIBLE','UNKNOWN')), prominence numeric(5,4) check (prominence between 0 and 1),
 confidence numeric(5,4) check (confidence between 0 and 1), provenance text check (provenance is null or provenance in ('AI_VISUAL','AI_MULTIMODAL','AI_AUDIO','TRANSCRIPT','OCR','SOURCE_METADATA','VERIFIED_FILENAME','VERIFIED_FOLDER','HUMAN_REVIEW','CLINICIAN_VERIFIED')),
 analysis_run_id uuid references public.ai_analysis_runs(id) on delete set null, is_primary boolean not null default false, created_at timestamptz not null default now(),
 constraint scene_anatomy_scene_asset_fkey foreign key(scene_id,asset_id) references public.asset_scenes(id,asset_id) on delete cascade,
 constraint scene_anatomy_unique unique(scene_id,anatomy_id,relationship_type)
);
create index scene_anatomy_asset_idx on public.scene_anatomy(asset_id); create index scene_anatomy_anatomy_idx on public.scene_anatomy(anatomy_id); create index scene_anatomy_run_idx on public.scene_anatomy(analysis_run_id) where analysis_run_id is not null;

create table public.scene_actions (
 id uuid primary key default gen_random_uuid(), scene_id uuid not null, asset_id uuid not null references public.assets(id) on delete cascade,
 action_id uuid not null references public.actions(id) on delete restrict, subject_scene_person_id uuid, object_scene_person_id uuid,
 target_anatomy_id uuid references public.anatomy_terms(id) on delete set null, target_treatment_id uuid references public.treatments(id) on delete set null,
 description text, confidence numeric(5,4) check (confidence between 0 and 1), provenance text check (provenance is null or provenance in ('AI_VISUAL','AI_MULTIMODAL','AI_AUDIO','TRANSCRIPT','OCR','SOURCE_METADATA','VERIFIED_FILENAME','VERIFIED_FOLDER','HUMAN_REVIEW','CLINICIAN_VERIFIED')),
 analysis_run_id uuid references public.ai_analysis_runs(id) on delete set null, start_seconds numeric(14,3), end_seconds numeric(14,3), created_at timestamptz not null default now(),
 constraint scene_actions_time check ((start_seconds is null or start_seconds >= 0) and (end_seconds is null or end_seconds >= 0) and (start_seconds is null or end_seconds is null or end_seconds > start_seconds)),
 constraint scene_actions_scene_asset_fkey foreign key(scene_id,asset_id) references public.asset_scenes(id,asset_id) on delete cascade,
 constraint scene_actions_subject_fkey foreign key(subject_scene_person_id,scene_id,asset_id) references public.scene_people(id,scene_id,asset_id) on delete cascade,
 constraint scene_actions_object_fkey foreign key(object_scene_person_id,scene_id,asset_id) references public.scene_people(id,scene_id,asset_id) on delete cascade
);
create index scene_actions_asset_idx on public.scene_actions(asset_id); create index scene_actions_scene_idx on public.scene_actions(scene_id); create index scene_actions_action_idx on public.scene_actions(action_id); create index scene_actions_subject_idx on public.scene_actions(subject_scene_person_id) where subject_scene_person_id is not null; create index scene_actions_target_anatomy_idx on public.scene_actions(target_anatomy_id) where target_anatomy_id is not null;

create table public.scene_relationships (
 id uuid primary key default gen_random_uuid(), scene_id uuid not null, asset_id uuid not null references public.assets(id) on delete cascade,
 participant_1_scene_person_id uuid not null, participant_2_scene_person_id uuid not null,
 relationship_type text not null check (relationship_type in ('DOCTOR_CONSULTING_PATIENT','DOCTOR_EXAMINING_PATIENT','DOCTOR_MARKING_PATIENT','DOCTOR_TREATING_PATIENT','DOCTOR_INJECTING_PATIENT','DOCTOR_EXPLAINING_TO_PATIENT','PATIENT_LISTENING_TO_DOCTOR','STAFF_ASSISTING_DOCTOR')),
 treatment_id uuid references public.treatments(id) on delete set null, anatomy_id uuid references public.anatomy_terms(id) on delete set null, description text,
 confidence numeric(5,4) check (confidence between 0 and 1), provenance text check (provenance is null or provenance in ('AI_VISUAL','AI_MULTIMODAL','AI_AUDIO','TRANSCRIPT','OCR','SOURCE_METADATA','VERIFIED_FILENAME','VERIFIED_FOLDER','HUMAN_REVIEW','CLINICIAN_VERIFIED')),
 analysis_run_id uuid references public.ai_analysis_runs(id) on delete set null, created_at timestamptz not null default now(),
 constraint scene_relationships_distinct_participants check(participant_1_scene_person_id <> participant_2_scene_person_id),
 constraint scene_relationships_scene_asset_fkey foreign key(scene_id,asset_id) references public.asset_scenes(id,asset_id) on delete cascade,
 constraint scene_relationships_p1_fkey foreign key(participant_1_scene_person_id,scene_id,asset_id) references public.scene_people(id,scene_id,asset_id) on delete cascade,
 constraint scene_relationships_p2_fkey foreign key(participant_2_scene_person_id,scene_id,asset_id) references public.scene_people(id,scene_id,asset_id) on delete cascade,
 constraint scene_relationships_unique unique(scene_id,participant_1_scene_person_id,participant_2_scene_person_id,relationship_type)
);
create index scene_relationships_asset_idx on public.scene_relationships(asset_id); create index scene_relationships_type_idx on public.scene_relationships(scene_id,relationship_type); create index scene_relationships_p2_idx on public.scene_relationships(participant_2_scene_person_id);

create table public.clinical_observations (
 id uuid primary key default gen_random_uuid(), asset_id uuid not null references public.assets(id) on delete cascade, scene_id uuid, keyframe_id uuid, scene_person_id uuid,
 anatomy_id uuid references public.anatomy_terms(id) on delete set null, observation_domain text not null, observation_type text not null,
 value_text text, value_number numeric, value_boolean boolean, value_json jsonb, severity text, side text check(side is null or side in ('LEFT','RIGHT','BILATERAL','MIDLINE','NOT_APPLICABLE','UNKNOWN')),
 confidence numeric(5,4) check(confidence between 0 and 1), source_type text not null check(source_type in ('AI_VISUAL','AI_MULTIMODAL','AI_AUDIO','TRANSCRIPT','OCR','SOURCE_METADATA','VERIFIED_FILENAME','VERIFIED_FOLDER','HUMAN_REVIEW','CLINICIAN_VERIFIED')),
 verification_status text not null default 'UNVERIFIED' check(verification_status in ('UNVERIFIED','AI_SUGGESTED','REVIEWED','VERIFIED','REJECTED')),
 analysis_run_id uuid references public.ai_analysis_runs(id) on delete set null, verified_by uuid references auth.users(id) on delete set null, verified_at timestamptz, evidence jsonb not null default '{}'::jsonb, metadata jsonb not null default '{}'::jsonb,
 created_at timestamptz not null default now(), updated_at timestamptz not null default now(),
 constraint clinical_observations_has_value check(num_nonnulls(value_text,value_number,value_boolean,value_json) >= 1),
 constraint clinical_observations_scoped_refs check((keyframe_id is null and scene_person_id is null) or scene_id is not null),
 constraint clinical_observations_scene_asset_fkey foreign key(scene_id,asset_id) references public.asset_scenes(id,asset_id) on delete cascade,
 constraint clinical_observations_keyframe_fkey foreign key(keyframe_id,scene_id,asset_id) references public.asset_keyframes(id,scene_id,asset_id) on delete cascade,
 constraint clinical_observations_scene_person_fkey foreign key(scene_person_id,scene_id,asset_id) references public.scene_people(id,scene_id,asset_id) on delete cascade
);
create index clinical_observations_asset_idx on public.clinical_observations(asset_id); create index clinical_observations_scene_idx on public.clinical_observations(scene_id) where scene_id is not null; create index clinical_observations_keyframe_idx on public.clinical_observations(keyframe_id) where keyframe_id is not null; create index clinical_observations_anatomy_idx on public.clinical_observations(anatomy_id) where anatomy_id is not null; create index clinical_observations_type_idx on public.clinical_observations(observation_type); create index clinical_observations_verification_idx on public.clinical_observations(verification_status);

create table public.scene_environment (
 scene_id uuid primary key, asset_id uuid not null references public.assets(id) on delete cascade, location_id uuid references public.locations(id) on delete set null,
 environment_type text, brightness text, visual_style text, cleanliness_impression text, background_activity text, clinical_environment boolean, premium_environment boolean, indoor_outdoor text check(indoor_outdoor is null or indoor_outdoor in ('INDOOR','OUTDOOR','MIXED','UNKNOWN')),
 description text, confidence numeric(5,4) check(confidence between 0 and 1), provenance text check(provenance is null or provenance in ('AI_VISUAL','AI_MULTIMODAL','AI_AUDIO','TRANSCRIPT','OCR','SOURCE_METADATA','VERIFIED_FILENAME','VERIFIED_FOLDER','HUMAN_REVIEW','CLINICIAN_VERIFIED')), analysis_run_id uuid references public.ai_analysis_runs(id) on delete set null,
 metadata jsonb not null default '{}'::jsonb, created_at timestamptz not null default now(), updated_at timestamptz not null default now(),
 constraint scene_environment_scene_asset_fkey foreign key(scene_id,asset_id) references public.asset_scenes(id,asset_id) on delete cascade
);
create index scene_environment_asset_idx on public.scene_environment(asset_id); create index scene_environment_location_idx on public.scene_environment(location_id) where location_id is not null;

create table public.scene_cinematography (
 scene_id uuid primary key, asset_id uuid not null references public.assets(id) on delete cascade,
 shot_size text check(shot_size is null or shot_size in ('EXTREME_CLOSEUP','CLOSEUP','MEDIUM_CLOSEUP','MEDIUM','MEDIUM_WIDE','WIDE')),
 camera_angle text check(camera_angle is null or camera_angle in ('FRONT','LEFT_PROFILE','RIGHT_PROFILE','THREE_QUARTER','TOP_DOWN','OVER_SHOULDER','OTHER')),
 camera_motion text check(camera_motion is null or camera_motion in ('STATIC','PAN','TILT','DOLLY','HANDHELD','GIMBAL','ZOOM','OTHER')),
 subject_motion text, primary_focus text, depth_of_field text, lighting text,
 visual_style text check(visual_style is null or visual_style in ('UGC','CINEMATIC','CLINICAL','DOCUMENTARY','TESTIMONIAL','COMMERCIAL','OTHER')),
 orientation_override text, technical_quality_score numeric(5,4) check(technical_quality_score between 0 and 1), confidence numeric(5,4) check(confidence between 0 and 1),
 provenance text check(provenance is null or provenance in ('AI_VISUAL','AI_MULTIMODAL','AI_AUDIO','TRANSCRIPT','OCR','SOURCE_METADATA','VERIFIED_FILENAME','VERIFIED_FOLDER','HUMAN_REVIEW','CLINICIAN_VERIFIED')), analysis_run_id uuid references public.ai_analysis_runs(id) on delete set null,
 metadata jsonb not null default '{}'::jsonb, created_at timestamptz not null default now(), updated_at timestamptz not null default now(),
 constraint scene_cinematography_scene_asset_fkey foreign key(scene_id,asset_id) references public.asset_scenes(id,asset_id) on delete cascade
);
create index scene_cinematography_asset_idx on public.scene_cinematography(asset_id);

create table public.scene_composition (
 scene_id uuid primary key, asset_id uuid not null references public.assets(id) on delete cascade, subject_position text, headroom_score numeric(5,4) check(headroom_score between 0 and 1),
 negative_space_left numeric(5,4), negative_space_right numeric(5,4), negative_space_top numeric(5,4), negative_space_bottom numeric(5,4),
 text_safe_area_left boolean, text_safe_area_right boolean, text_safe_area_top boolean, text_safe_area_bottom boolean,
 background_clutter_level text, logo_visibility text, composition_description text, confidence numeric(5,4) check(confidence between 0 and 1),
 provenance text check(provenance is null or provenance in ('AI_VISUAL','AI_MULTIMODAL','AI_AUDIO','TRANSCRIPT','OCR','SOURCE_METADATA','VERIFIED_FILENAME','VERIFIED_FOLDER','HUMAN_REVIEW','CLINICIAN_VERIFIED')), analysis_run_id uuid references public.ai_analysis_runs(id) on delete set null,
 metadata jsonb not null default '{}'::jsonb, created_at timestamptz not null default now(), updated_at timestamptz not null default now(),
 constraint scene_composition_spaces check(negative_space_left between 0 and 1 and negative_space_right between 0 and 1 and negative_space_top between 0 and 1 and negative_space_bottom between 0 and 1),
 constraint scene_composition_scene_asset_fkey foreign key(scene_id,asset_id) references public.asset_scenes(id,asset_id) on delete cascade
);
create index scene_composition_asset_idx on public.scene_composition(asset_id);

create table public.marketing_annotations (
 id uuid primary key default gen_random_uuid(), asset_id uuid not null references public.assets(id) on delete cascade, scene_id uuid, keyframe_id uuid,
 marketing_role text not null check(marketing_role in ('HOOK','PROBLEM','CONSULTATION','EDUCATION','PROCEDURE','PROOF','RESULT','REACTION','LIFESTYLE','CTA','B_ROLL','TRANSITION')),
 funnel_stage text check(funnel_stage is null or funnel_stage in ('AWARENESS','CONSIDERATION','CONVERSION','RETARGETING')), potential_topic text, potential_hook text, suggested_use text, platform_suitability text[],
 confidence numeric(5,4) check(confidence between 0 and 1), provenance text check(provenance is null or provenance in ('AI_VISUAL','AI_MULTIMODAL','AI_AUDIO','TRANSCRIPT','OCR','SOURCE_METADATA','VERIFIED_FILENAME','VERIFIED_FOLDER','HUMAN_REVIEW','CLINICIAN_VERIFIED')), analysis_run_id uuid references public.ai_analysis_runs(id) on delete set null,
 review_status text not null default 'NOT_REVIEWED' check(review_status in ('NOT_REVIEWED','PENDING','REVIEWED','VERIFIED','REJECTED')), metadata jsonb not null default '{}'::jsonb, created_at timestamptz not null default now(), updated_at timestamptz not null default now(),
 constraint marketing_annotations_scene_asset_fkey foreign key(scene_id,asset_id) references public.asset_scenes(id,asset_id) on delete cascade,
 constraint marketing_annotations_keyframe_requires_scene check(keyframe_id is null or scene_id is not null),
 constraint marketing_annotations_keyframe_fkey foreign key(keyframe_id,scene_id,asset_id) references public.asset_keyframes(id,scene_id,asset_id) on delete cascade
);
create index marketing_annotations_asset_idx on public.marketing_annotations(asset_id); create index marketing_annotations_scene_idx on public.marketing_annotations(scene_id) where scene_id is not null; create index marketing_annotations_role_idx on public.marketing_annotations(marketing_role); create index marketing_annotations_funnel_idx on public.marketing_annotations(funnel_stage) where funnel_stage is not null;

create table public.scene_narratives (
 id uuid primary key default gen_random_uuid(), scene_id uuid not null, asset_id uuid not null references public.assets(id) on delete cascade,
 narrative_type text not null check(narrative_type in ('LITERAL','CLINICAL_VISUAL','STORYTELLING','MARKETING','EMOTIONAL')), text text not null check(btrim(text) <> ''),
 confidence numeric(5,4) check(confidence between 0 and 1), provenance text check(provenance is null or provenance in ('AI_VISUAL','AI_MULTIMODAL','AI_AUDIO','TRANSCRIPT','OCR','SOURCE_METADATA','VERIFIED_FILENAME','VERIFIED_FOLDER','HUMAN_REVIEW','CLINICIAN_VERIFIED')), analysis_run_id uuid references public.ai_analysis_runs(id) on delete set null,
 review_status text not null default 'NOT_REVIEWED' check(review_status in ('NOT_REVIEWED','PENDING','REVIEWED','VERIFIED','REJECTED')), created_at timestamptz not null default now(), updated_at timestamptz not null default now(),
 constraint scene_narratives_scene_asset_fkey foreign key(scene_id,asset_id) references public.asset_scenes(id,asset_id) on delete cascade,
 constraint scene_narratives_unique unique(scene_id,narrative_type,text)
);
create index scene_narratives_asset_idx on public.scene_narratives(asset_id); create index scene_narratives_type_idx on public.scene_narratives(scene_id,narrative_type);

alter table public.scene_treatments enable row level security; alter table public.scene_anatomy enable row level security; alter table public.scene_actions enable row level security; alter table public.scene_relationships enable row level security; alter table public.clinical_observations enable row level security; alter table public.scene_environment enable row level security; alter table public.scene_cinematography enable row level security; alter table public.scene_composition enable row level security; alter table public.marketing_annotations enable row level security; alter table public.scene_narratives enable row level security;
revoke all on table public.scene_treatments,public.scene_anatomy,public.scene_actions,public.scene_relationships,public.clinical_observations,public.scene_environment,public.scene_cinematography,public.scene_composition,public.marketing_annotations,public.scene_narratives from public,anon,authenticated;
grant all on table public.scene_treatments,public.scene_anatomy,public.scene_actions,public.scene_relationships,public.clinical_observations,public.scene_environment,public.scene_cinematography,public.scene_composition,public.marketing_annotations,public.scene_narratives to service_role;

create trigger clinical_observations_set_updated_at before update on public.clinical_observations for each row execute function public.set_updated_at();
create trigger scene_environment_set_updated_at before update on public.scene_environment for each row execute function public.set_updated_at();
create trigger scene_cinematography_set_updated_at before update on public.scene_cinematography for each row execute function public.set_updated_at();
create trigger scene_composition_set_updated_at before update on public.scene_composition for each row execute function public.set_updated_at();
create trigger marketing_annotations_set_updated_at before update on public.marketing_annotations for each row execute function public.set_updated_at();
create trigger scene_narratives_set_updated_at before update on public.scene_narratives for each row execute function public.set_updated_at();
