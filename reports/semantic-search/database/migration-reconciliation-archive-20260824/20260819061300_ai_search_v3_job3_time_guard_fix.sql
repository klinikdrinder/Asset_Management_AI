-- Correct the shared Job 3 scene-time guard to access table-specific fields safely.
create or replace function public.validate_job3_scene_time_bounds() returns trigger
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
