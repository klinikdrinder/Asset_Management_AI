-- KDI AI Search V3 Job 5: propagate the authoritative asset decision through
-- every asset-derived table. No write grants are added.

drop policy if exists assets_individual_read on public.assets;
create policy assets_asset_permission_read on public.assets for select to authenticated
using ((select private.can_user_view_asset(id)));

do $policies$
declare t text; old_policy text;
begin
 foreach t in array array[
  'asset_access_control','asset_ai_profiles','asset_metadata_assertions','asset_people','asset_search_concepts',
  'asset_transcript_chunks','asset_video_segments','asset_semantic_index','asset_embeddings','asset_visual_embeddings',
  'asset_visual_index_jobs','asset_derivatives','ai_analysis_runs','asset_sources','asset_destinations',
  'asset_scenes','asset_keyframes','scene_people','person_appearances','scene_treatments','scene_anatomy','scene_actions',
  'scene_relationships','clinical_observations','scene_environment','scene_cinematography','scene_composition',
  'marketing_annotations','scene_narratives','ocr_observations','scene_embeddings','keyframe_embeddings',
  'transcript_embeddings','asset_search_documents','scene_search_documents'
 ] loop
  old_policy:=t||'_individual_read';
  execute format('drop policy if exists %I on public.%I',old_policy,t);
  execute format('drop policy if exists %I on public.%I',t||'_asset_permission_read',t);
  execute format('create policy %I on public.%I for select to authenticated using ((select private.can_user_view_asset(asset_id)))',t||'_asset_permission_read',t);
 end loop;
end $policies$;

drop policy if exists search_sessions_owner_read on public.search_sessions;
create policy search_sessions_owner_read on public.search_sessions for select to authenticated
using (user_id=(select private.current_app_user_id()));
drop policy if exists search_queries_owner_read on public.search_queries;
create policy search_queries_owner_read on public.search_queries for select to authenticated
using ((select private.is_search_session_owner(session_id)));
drop policy if exists search_results_owner_read on public.search_results;
create policy search_results_owner_read on public.search_results for select to authenticated
using (exists(select 1 from public.search_queries q where q.id=search_query_id and private.is_search_session_owner(q.session_id)));
drop policy if exists search_feedback_owner_read on public.search_feedback;
create policy search_feedback_owner_read on public.search_feedback for select to authenticated
using (exists(select 1 from public.search_queries q where q.id=search_query_id and private.is_search_session_owner(q.session_id)));

-- Explicitly retain backend-only access for raw vectors/search projections.
revoke all on table public.asset_access_control,public.asset_embeddings,public.asset_visual_embeddings,
 public.scene_embeddings,public.keyframe_embeddings,public.transcript_embeddings,
 public.asset_search_documents,public.scene_search_documents from public,anon,authenticated;

;
