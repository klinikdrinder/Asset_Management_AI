begin;

create or replace function public.match_phase17_semantic_embeddings(
  query_embedding public.vector,
  requested_representation text,
  requested_provider text,
  requested_model text,
  requested_model_version text,
  requested_dimension integer,
  result_limit integer default 25,
  minimum_similarity real default 0
)
returns table(
  embedding_id uuid, asset_id uuid, filename text, representation_type text,
  raw_similarity real, scene_id uuid, event_id uuid, keyframe_id uuid,
  transcript_chunk_id bigint, ocr_observation_id uuid,
  time_start numeric, time_end numeric, source_document_id text,
  embedding_family text, embedding_dimension integer, evidence_source text
)
language sql stable security invoker set search_path=''
as $function$
  with compatible as materialized (
    select e.*
    from public.semantic_embeddings e
    where e.active and not e.stale
      and e.representation_type=requested_representation
      and e.provider=requested_provider and e.model=requested_model
      and e.model_version=requested_model_version
      and e.dimensions=requested_dimension
      and public.vector_dims(e.embedding)=requested_dimension
      and public.vector_dims(query_embedding)=requested_dimension
  ), scored as (
    select e.*, (1-(e.embedding OPERATOR(public.<=>) query_embedding))::real similarity
    from compatible e
  )
  select s.id,a.id,a.file_name,s.representation_type,s.similarity,
    s.scene_id,s.event_id,s.keyframe_id,s.transcript_chunk_id,s.ocr_observation_id,
    coalesce(tc.start_seconds,k.timestamp_seconds,o.timestamp_seconds,ev.start_time,sc.start_seconds)::numeric,
    coalesce(tc.end_seconds,o.end_time,ev.end_time,sc.end_seconds)::numeric,
    coalesce(s.metadata->>'source_unit_id',s.source_document_fingerprint),
    concat_ws(':',s.provider,s.model,s.model_version),s.dimensions,'semantic_embeddings'
  from scored s join public.assets a on a.id=s.asset_id
  left join public.asset_scenes sc on sc.id=s.scene_id
  left join public.asset_events ev on ev.id=s.event_id
  left join public.asset_keyframes k on k.id=s.keyframe_id
  left join public.asset_transcript_chunks tc on tc.id=s.transcript_chunk_id
  left join public.ocr_observations o on o.id=s.ocr_observation_id
  where s.similarity>=greatest(-1,least(coalesce(minimum_similarity,0),1))
  order by s.similarity desc,s.id
  limit greatest(1,least(coalesce(result_limit,25),100));
$function$;

revoke all on function public.match_phase17_semantic_embeddings(public.vector,text,text,text,text,integer,integer,real) from public,anon;
grant execute on function public.match_phase17_semantic_embeddings(public.vector,text,text,text,text,integer,integer,real) to authenticated,service_role;
comment on function public.match_phase17_semantic_embeddings(public.vector,text,text,text,text,integer,integer,real)
is 'Phase 17 cosine retrieval with mandatory provider/model/version/representation/dimension compatibility and child evidence roll-up fields.';

commit;
