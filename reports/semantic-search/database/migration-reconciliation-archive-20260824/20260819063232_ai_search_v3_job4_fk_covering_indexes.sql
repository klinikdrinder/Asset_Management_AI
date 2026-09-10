-- Advisor-driven covering indexes for Job 4 composite foreign keys.
create index scene_embeddings_scene_asset_idx on public.scene_embeddings(scene_id,asset_id);
create index keyframe_embeddings_keyframe_scene_asset_idx on public.keyframe_embeddings(keyframe_id,scene_id,asset_id);
create index transcript_embeddings_chunk_asset_idx on public.transcript_embeddings(transcript_chunk_id,asset_id);
create index transcript_embeddings_scene_asset_idx on public.transcript_embeddings(scene_id,asset_id);
create index scene_search_documents_scene_asset_idx on public.scene_search_documents(scene_id,asset_id);
create index search_results_scene_asset_idx on public.search_results(scene_id,asset_id);
create index search_results_keyframe_scene_asset_idx on public.search_results(keyframe_id,scene_id,asset_id);
create index search_results_transcript_asset_idx on public.search_results(transcript_chunk_id,asset_id);
create index search_feedback_asset_idx on public.search_feedback(asset_id);
create index search_feedback_result_query_idx on public.search_feedback(search_result_id,search_query_id);
create index search_feedback_scene_asset_idx on public.search_feedback(scene_id,asset_id);
