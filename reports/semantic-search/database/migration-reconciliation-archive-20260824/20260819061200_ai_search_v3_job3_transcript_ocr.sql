-- KDI AI Search V3 Job 3: transcript linkage, OCR observations, and parent-scene time validation.

alter table public.asset_transcript_chunks
 add column scene_id uuid,
 add column speaker_person_id uuid references public.people(id) on delete set null,
 add column speaker_scene_person_id uuid,
 add column analysis_run_id uuid references public.ai_analysis_runs(id) on delete set null,
 add constraint asset_transcript_chunks_scene_asset_fkey foreign key(scene_id,asset_id) references public.asset_scenes(id,asset_id) on delete cascade,
 add constraint asset_transcript_chunks_speaker_requires_scene check(speaker_scene_person_id is null or scene_id is not null),
 add constraint asset_transcript_chunks_speaker_scene_person_fkey foreign key(speaker_scene_person_id,scene_id,asset_id) references public.scene_people(id,scene_id,asset_id) on delete restrict;

create index asset_transcript_chunks_scene_idx on public.asset_transcript_chunks(scene_id) where scene_id is not null;
create index asset_transcript_chunks_speaker_person_idx on public.asset_transcript_chunks(speaker_person_id) where speaker_person_id is not null;
create index asset_transcript_chunks_speaker_scene_person_idx on public.asset_transcript_chunks(speaker_scene_person_id) where speaker_scene_person_id is not null;
create index asset_transcript_chunks_time_idx on public.asset_transcript_chunks(asset_id,start_seconds,end_seconds);
create index asset_transcript_chunks_analysis_run_idx on public.asset_transcript_chunks(analysis_run_id) where analysis_run_id is not null;

create table public.ocr_observations (
 id uuid primary key default gen_random_uuid(), asset_id uuid not null references public.assets(id) on delete cascade, scene_id uuid, keyframe_id uuid,
 timestamp_seconds numeric(14,3) check(timestamp_seconds is null or timestamp_seconds >= 0), raw_text text not null check(btrim(raw_text) <> ''), normalized_text text,
 text_type text not null check(text_type in ('CLINIC_SIGN','DEVICE_NAME','PRODUCT_NAME','PRESENTATION','CAPTION','LABEL','BEFORE_AFTER_CARD','SCREEN_TEXT','OTHER')),
 language text, confidence numeric(5,4) check(confidence between 0 and 1), bounding_box jsonb, analysis_run_id uuid references public.ai_analysis_runs(id) on delete set null,
 provenance text check(provenance is null or provenance in ('AI_VISUAL','AI_MULTIMODAL','AI_AUDIO','TRANSCRIPT','OCR','SOURCE_METADATA','VERIFIED_FILENAME','VERIFIED_FOLDER','HUMAN_REVIEW','CLINICIAN_VERIFIED')),
 metadata jsonb not null default '{}'::jsonb, created_at timestamptz not null default now(), updated_at timestamptz not null default now(),
 constraint ocr_observations_scene_asset_fkey foreign key(scene_id,asset_id) references public.asset_scenes(id,asset_id) on delete cascade,
 constraint ocr_observations_keyframe_requires_scene check(keyframe_id is null or scene_id is not null),
 constraint ocr_observations_keyframe_fkey foreign key(keyframe_id,scene_id,asset_id) references public.asset_keyframes(id,scene_id,asset_id) on delete cascade
);
create index ocr_observations_asset_idx on public.ocr_observations(asset_id); create index ocr_observations_scene_idx on public.ocr_observations(scene_id) where scene_id is not null; create index ocr_observations_keyframe_idx on public.ocr_observations(keyframe_id) where keyframe_id is not null; create index ocr_observations_run_idx on public.ocr_observations(analysis_run_id) where analysis_run_id is not null;

alter table public.ocr_observations enable row level security;
revoke all on table public.ocr_observations from public,anon,authenticated;
grant all on table public.ocr_observations to service_role;
create trigger ocr_observations_set_updated_at before update on public.ocr_observations for each row execute function public.set_updated_at();

create function public.validate_job3_scene_time_bounds() returns trigger
language plpgsql security invoker set search_path = '' as $$
declare v_start numeric; v_end numeric; v_row jsonb; v_point numeric; v_row_start numeric; v_row_end numeric;
begin
  if new.scene_id is null then return new; end if;
  v_row := to_jsonb(new);
  v_point := nullif(v_row->>'timestamp_seconds','')::numeric;
  v_row_start := nullif(v_row->>'start_seconds','')::numeric;
  v_row_end := nullif(v_row->>'end_seconds','')::numeric;
  select s.start_seconds,s.end_seconds into v_start,v_end from public.asset_scenes s where s.id=new.scene_id and s.asset_id=new.asset_id;
  if not found then raise exception using errcode='23503', message='scene does not belong to asset'; end if;
  if tg_table_name='asset_keyframes' and (v_point < v_start or v_point > v_end) then raise exception using errcode='23514', message='keyframe timestamp must fall within scene'; end if;
  if tg_table_name='scene_actions' and ((v_row_start is not null and v_row_start < v_start) or (v_row_end is not null and v_row_end > v_end)) then raise exception using errcode='23514', message='action timestamps must fall within scene'; end if;
  if tg_table_name='asset_transcript_chunks' and ((v_row_start is not null and v_row_start < v_start) or (v_row_end is not null and v_row_end > v_end)) then raise exception using errcode='23514', message='transcript timestamps must fall within scene'; end if;
  if tg_table_name='ocr_observations' and v_point is not null and (v_point < v_start or v_point > v_end) then raise exception using errcode='23514', message='OCR timestamp must fall within scene'; end if;
  return new;
end $$;
revoke all on function public.validate_job3_scene_time_bounds() from public,anon,authenticated,service_role;

create trigger asset_keyframes_scene_time before insert or update on public.asset_keyframes for each row execute function public.validate_job3_scene_time_bounds();
create trigger scene_actions_scene_time before insert or update on public.scene_actions for each row execute function public.validate_job3_scene_time_bounds();
create trigger asset_transcript_chunks_scene_time before insert or update on public.asset_transcript_chunks for each row execute function public.validate_job3_scene_time_bounds();
create trigger ocr_observations_scene_time before insert or update on public.ocr_observations for each row execute function public.validate_job3_scene_time_bounds();
