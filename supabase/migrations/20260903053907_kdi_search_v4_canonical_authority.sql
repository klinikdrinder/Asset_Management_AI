begin;

-- Duplicate audits are a mandatory deployment precondition. The statements
-- abort before any DDL if current active truth is ambiguous.
do $$
begin
  if exists(select 1 from public.asset_semantic_layers where active group by asset_id,layer_id,semantic_spec_version having count(*)>1) then
    raise exception 'ACTIVE_SEMANTIC_LAYER_DUPLICATES';
  end if;
  if exists(select 1 from public.search_document_builds where active group by asset_id,document_type,coalesce(scene_id,'00000000-0000-0000-0000-000000000000'::uuid),coalesce(event_id,'00000000-0000-0000-0000-000000000000'::uuid),search_document_version having count(*)>1) then
    raise exception 'ACTIVE_SEARCH_DOCUMENT_DUPLICATES';
  end if;
  if exists(select 1 from public.semantic_embeddings where active and representation_type is not null group by asset_id,coalesce(scene_id,'00000000-0000-0000-0000-000000000000'::uuid),coalesce(event_id,'00000000-0000-0000-0000-000000000000'::uuid),coalesce(keyframe_id,'00000000-0000-0000-0000-000000000000'::uuid),coalesce(transcript_chunk_id,-1),coalesce(ocr_observation_id,'00000000-0000-0000-0000-000000000000'::uuid),representation_type,embedding_version,model_version having count(*)>1) then
    raise exception 'ACTIVE_SEMANTIC_EMBEDDING_DUPLICATES';
  end if;
end $$;

create unique index if not exists asset_semantic_layers_active_authority_idx
  on public.asset_semantic_layers(asset_id,layer_id,semantic_spec_version) where active;

create index if not exists semantic_embeddings_hnsw_e5_384_idx
  on public.semantic_embeddings using hnsw ((embedding::public.vector(384)) public.vector_cosine_ops)
  where active and not stale and dimensions=384 and provider='sentence_transformers' and model='intfloat/multilingual-e5-small';
create index if not exists semantic_embeddings_hnsw_openclip_512_idx
  on public.semantic_embeddings using hnsw ((embedding::public.vector(512)) public.vector_cosine_ops)
  where active and not stale and dimensions=512 and provider='open_clip' and model='ViT-B-32';

create or replace view public.kdi_search_ready_assets_v1 with(security_invoker=true) as
with layers as (
 select asset_id,count(*) layer_count,
  bool_and(processing_status='COMPLETE' and completeness_status in('COMPLETE','NOT_APPLICABLE')) layers_complete
 from public.asset_semantic_layers where active group by asset_id
), docs as (
 select asset_id,
  count(*) filter(where document_type='ASSET' and status='READY' and active and not stale) asset_docs,
  count(*) filter(where document_type='SCENE' and status='READY' and active and not stale) scene_docs
 from public.search_document_builds group by asset_id
), scenes as (
 select asset_id,count(*) scenes,
  bool_and(start_seconds<end_seconds and coalesce(short_description,literal_description,'')<>'') scenes_valid
 from public.asset_scenes where canonical_active group by asset_id
), keys as (
 select k.asset_id,count(*) keyframes from public.asset_keyframes k join public.asset_scenes s on s.id=k.scene_id and s.canonical_active group by k.asset_id
), emb as (
 select asset_id,
  count(*) filter(where representation_type='TEXT_ASSET' and provider='sentence_transformers' and model='intfloat/multilingual-e5-small' and model_version='hf-main-pinned-runtime-v1' and dimensions=384) text_asset,
  count(*) filter(where representation_type='VISUAL_ASSET' and provider='open_clip' and model='ViT-B-32' and dimensions=512) canonical_visual_asset,
  count(*) filter(where representation_type='TEXT_SCENE' and provider='sentence_transformers' and model='intfloat/multilingual-e5-small' and model_version='hf-main-pinned-runtime-v1' and dimensions=384) text_scene,
  count(*) filter(where representation_type='VISUAL_SCENE' and provider='open_clip' and model='ViT-B-32' and dimensions=512) visual_scene,
  count(*) filter(where representation_type='VISUAL_KEYFRAME' and provider='open_clip' and model='ViT-B-32' and dimensions=512) visual_keyframe
 from public.semantic_embeddings where active and not stale group by asset_id
), legacy_visual as (
 select asset_id,count(*) visual_asset from public.asset_visual_embeddings
 where model_provider='open_clip' and model_name='ViT-B-32' and model_version='laion2b_s34b_b79k' and embedding_dimensions=512 group by asset_id
)
select a.id asset_id,a.file_name,a.mime_type,
 coalesce(l.layer_count,0)=18 and coalesce(l.layers_complete,false)
 and coalesce(d.asset_docs,0)=1 and coalesce(e.text_asset,0)=1
 and (coalesce(e.canonical_visual_asset,0)=1 or coalesce(v.visual_asset,0)=1)
 and (case when a.mime_type like 'video/%' then coalesce(s.scenes,0)>0 and coalesce(s.scenes_valid,false)
       and coalesce(d.scene_docs,0)=coalesce(s.scenes,0) and coalesce(e.text_scene,0)=coalesce(s.scenes,0)
       and coalesce(e.visual_scene,0)=coalesce(s.scenes,0) and coalesce(k.keyframes,0)>0
       and coalesce(e.visual_keyframe,0)=coalesce(k.keyframes,0) else true end) search_ready,
 coalesce(l.layer_count,0) layer_count,coalesce(d.asset_docs,0) asset_document_count,
 coalesce(s.scenes,0) canonical_scene_count,coalesce(d.scene_docs,0) scene_document_count
from public.assets a left join layers l on l.asset_id=a.id left join docs d on d.asset_id=a.id
left join scenes s on s.asset_id=a.id left join keys k on k.asset_id=a.id left join emb e on e.asset_id=a.id
left join legacy_visual v on v.asset_id=a.id;

comment on view public.kdi_search_ready_assets_v1 is 'Sole derived SEARCH_READY authority for KDI_SEARCH_V4_CANONICAL; legacy profile/document statuses cannot override it.';
grant select on public.kdi_search_ready_assets_v1 to authenticated,service_role;

create or replace function public.match_kdi_search_v4_embeddings(
 query_embedding public.vector,requested_representation text,requested_provider text,requested_model text,
 requested_model_version text,requested_dimension integer,result_limit integer default 25,minimum_similarity real default 0)
returns table(embedding_id uuid,asset_id uuid,filename text,representation_type text,raw_similarity real,
 scene_id uuid,event_id uuid,keyframe_id uuid,transcript_chunk_id bigint,ocr_observation_id uuid,
 time_start numeric,time_end numeric,source_document_id text,embedding_family text,embedding_dimension integer,evidence_source text)
language sql stable security invoker set search_path='' as $fn$
 with canonical as (
  select e.id,e.asset_id,e.representation_type,e.embedding,e.scene_id,e.event_id,e.keyframe_id,e.transcript_chunk_id,e.ocr_observation_id,
   coalesce(tc.start_seconds,k.timestamp_seconds,o.timestamp_seconds,ev.start_time,sc.start_seconds)::numeric time_start,
   coalesce(tc.end_seconds,o.end_time,ev.end_time,sc.end_seconds)::numeric time_end,
   coalesce(e.metadata->>'source_unit_id',e.source_document_fingerprint) source_document_id,'semantic_embeddings'::text evidence_source
  from public.semantic_embeddings e left join public.asset_scenes sc on sc.id=e.scene_id left join public.asset_events ev on ev.id=e.event_id
  left join public.asset_keyframes k on k.id=e.keyframe_id left join public.asset_transcript_chunks tc on tc.id=e.transcript_chunk_id
  left join public.ocr_observations o on o.id=e.ocr_observation_id
  where e.active and not e.stale and e.representation_type=requested_representation and e.provider=requested_provider
   and e.model=requested_model and e.model_version=requested_model_version and e.dimensions=requested_dimension
   and public.vector_dims(e.embedding)=requested_dimension
 ), compatible as (
  select * from canonical
  union all
  select v.id,v.asset_id,'VISUAL_ASSET',v.embedding,null::uuid,null::uuid,null::uuid,null::bigint,null::uuid,
   null::numeric,null::numeric,v.source_fingerprint,'derived_legacy_visual_projection'
  from public.asset_visual_embeddings v
  where requested_representation='VISUAL_ASSET' and requested_provider='open_clip' and requested_model='ViT-B-32'
   and requested_model_version='laion2b_s34b_b79k' and requested_dimension=512
   and v.model_provider=requested_provider and v.model_name=requested_model and v.model_version=requested_model_version and v.embedding_dimensions=512
 ), scored as (
  select c.*,(1-(c.embedding OPERATOR(public.<=>) query_embedding))::real similarity from compatible c
  where public.vector_dims(query_embedding)=requested_dimension
 )
 select s.id,a.id,a.file_name,s.representation_type,s.similarity,s.scene_id,s.event_id,s.keyframe_id,s.transcript_chunk_id,s.ocr_observation_id,
  s.time_start,s.time_end,s.source_document_id,concat_ws(':',requested_provider,requested_model,requested_model_version),requested_dimension,s.evidence_source
 from scored s join public.assets a on a.id=s.asset_id join public.kdi_search_ready_assets_v1 r on r.asset_id=s.asset_id and r.search_ready
 where s.similarity>=greatest(-1,least(coalesce(minimum_similarity,0),1)) order by s.similarity desc,s.id
 limit greatest(1,least(coalesce(result_limit,25),100));
$fn$;

revoke all on function public.match_kdi_search_v4_embeddings(public.vector,text,text,text,text,integer,integer,real) from public,anon;
grant execute on function public.match_kdi_search_v4_embeddings(public.vector,text,text,text,text,integer,integer,real) to authenticated,service_role;

commit;
