-- KDI AI Search V3 job8-v3.5: keep inferred structured concepts as ranking evidence, not mandatory all-of constraints.
-- V1 and V2 are deliberately not replaced or altered.

create index if not exists asset_visual_embeddings_hnsw_512_idx
  on public.asset_visual_embeddings using hnsw (embedding public.vector_cosine_ops)
  where model_provider='open_clip' and model_name='ViT-B-32'
    and model_version='laion2b_s34b_b79k' and embedding_dimensions=512;
create index if not exists scene_embeddings_hnsw_visual_512_idx
  on public.scene_embeddings using hnsw ((embedding::public.vector(512)) public.vector_cosine_ops)
  where is_active and embedding_type='VISUAL' and embedding_dimensions=512;
create index if not exists keyframe_embeddings_hnsw_visual_512_idx
  on public.keyframe_embeddings using hnsw ((embedding::public.vector(512)) public.vector_cosine_ops)
  where is_active and embedding_type='VISUAL' and embedding_dimensions=512;

create or replace function public.hybrid_search_assets_v3(
  search_query text,
  visual_query_embedding public.vector(512) default null,
  structured_filters jsonb default '{}'::jsonb,
  excluded_asset_ids uuid[] default '{}'::uuid[],
  result_limit integer default 5,
  result_offset integer default 0,
  minimum_relevance numeric default 0.08
)
returns table(
  asset_id uuid, match_score numeric, visual_asset_score numeric,
  visual_scene_score numeric, visual_keyframe_score numeric,
  lexical_asset_score numeric, lexical_scene_score numeric,
  structured_score numeric, filename_score numeric,
  matched_scene_id uuid, matched_start_seconds numeric, matched_end_seconds numeric,
  matched_features jsonb, match_reason text, total_count bigint
)
language sql stable security definer set search_path='' as $$
with params as (
  select nullif(btrim(left(coalesce(search_query,''),300)),'') q,
    case when nullif(btrim(left(coalesce(search_query,''),300)),'') is null then null
         else websearch_to_tsquery('english',left(search_query,300)) end tsq,
    case when jsonb_typeof(coalesce(structured_filters,'{}'::jsonb))='object'
         then coalesce(structured_filters,'{}'::jsonb) else '{}'::jsonb end f,
    coalesce(excluded_asset_ids,'{}'::uuid[]) excluded,
    greatest(1,least(coalesce(result_limit,5),50)) lim,
    greatest(0,coalesce(result_offset,0)) off,
    greatest(0,least(coalesce(minimum_relevance,0.08),1)) threshold
), authorized as materialized (
  select a.id,a.file_name,a.file_extension,a.mime_type
  from private.authorized_asset_ids() aa
  join public.assets a on a.id=aa.asset_id cross join params p
  where not (a.id=any(p.excluded))
    and exists(select 1 from public.asset_destinations d where d.asset_id=a.id and d.upload_status='VERIFIED' and d.destination_google_file_id is not null)
    and exists(select 1 from public.asset_sources l join public.source_files sf on sf.id=l.source_file_id join public.source_folders fol on fol.id=sf.source_folder_id where l.asset_id=a.id and not coalesce(sf.is_missing,false) and sf.sync_classification is distinct from 'REMOVED_FROM_SOURCE' and fol.active)
    and (not (p.f ? 'media_type') or lower(coalesce(a.mime_type,'')) like lower(p.f->>'media_type')||'/%')
    and (not (p.f ? 'extension') or lower(coalesce(a.file_extension,''))=lower(p.f->>'extension'))
    and (not (p.f ? 'excluded_media_type') or lower(coalesce(a.mime_type,'')) not like lower(p.f->>'excluded_media_type')||'/%')
    and (not (p.f ? 'excluded_content_type') or not exists(select 1 from public.marketing_annotations mx where mx.asset_id=a.id and lower(mx.marketing_role)=lower(p.f->>'excluded_content_type')))
), asset_signals as (
  select a.*,
    case when visual_query_embedding is null then 0 else greatest(0,least(1,coalesce(1-(ve.embedding operator(public.<=>) visual_query_embedding),0))) end av,
    case when p.tsq is null then 0 else least(1,coalesce(ts_rank_cd(ad.search_vector,p.tsq),0)/(coalesce(ts_rank_cd(ad.search_vector,p.tsq),0)+0.15)) end al,
    case when p.q is not null and a.file_name ilike '%'||replace(replace(p.q,'%','\%'),'_','\_')||'%' escape '\' then 1 else 0 end fn,
    ad.structured_document,ad.primary_treatment_id,ad.primary_anatomy_id
  from authorized a cross join params p
  left join public.asset_visual_embeddings ve on ve.asset_id=a.id and ve.model_provider='open_clip' and ve.model_name='ViT-B-32' and ve.model_version='laion2b_s34b_b79k' and ve.embedding_dimensions=512
  left join public.asset_search_documents ad on ad.asset_id=a.id and ad.build_status='READY'
), scene_signals as (
  select a.id,
    coalesce((select max(greatest(0,least(1,1-(se.embedding::public.vector(512) operator(public.<=>) visual_query_embedding)))) from public.scene_embeddings se where visual_query_embedding is not null and se.asset_id=a.id and se.is_active and se.embedding_type='VISUAL' and se.embedding_dimensions=512 and se.provider='open_clip' and se.model_name='ViT-B-32' and se.model_version='laion2b_s34b_b79k'),0) sv,
    coalesce((select max(greatest(0,least(1,1-(ke.embedding::public.vector(512) operator(public.<=>) visual_query_embedding)))) from public.keyframe_embeddings ke where visual_query_embedding is not null and ke.asset_id=a.id and ke.is_active and ke.embedding_type='VISUAL' and ke.embedding_dimensions=512 and ke.provider='open_clip' and ke.model_name='ViT-B-32' and ke.model_version='laion2b_s34b_b79k'),0) kv,
    coalesce((select max(least(1,ts_rank_cd(sd.search_vector,p.tsq)/(ts_rank_cd(sd.search_vector,p.tsq)+0.15))) from public.scene_search_documents sd where p.tsq is not null and sd.asset_id=a.id and sd.build_status='READY'),0) sl,
    best.id best_scene,best.start_seconds scene_start,best.end_seconds scene_end
  from authorized a cross join params p
  left join lateral (select s.id,s.start_seconds,s.end_seconds from public.asset_scenes s left join public.scene_search_documents sd on sd.scene_id=s.id where s.asset_id=a.id order by case when p.tsq is null then 0 else coalesce(ts_rank_cd(sd.search_vector,p.tsq),0) end desc,s.scene_index limit 1) best on true
), structured as (
  select a.id,
    case when requested.n=0 then 0 else matches.n::numeric/requested.n end ss,
    jsonb_strip_nulls(jsonb_build_object(
      'treatment',case when treatment_match then p.f->>'treatment' end,
      'anatomy',case when anatomy_match then p.f->>'anatomy' end,
      'action',case when action_match then p.f->>'action' end,
      'role',case when role_match then p.f->>'role' end,
      'scene_type',case when scene_type_match then p.f->>'scene_type' end,
      'environment',case when environment_match then p.f->>'environment' end,
      'shot_type',case when shot_match then p.f->>'shot_type' end,
      'content_type',case when content_match then p.f->>'content_type' end)) features
  from authorized a cross join params p
  cross join lateral (select
    (p.f ? 'treatment')::int+(p.f ? 'anatomy')::int+(p.f ? 'action')::int+(p.f ? 'role')::int+
    (p.f ? 'scene_type')::int+(p.f ? 'environment')::int+(p.f ? 'shot_type')::int+(p.f ? 'content_type')::int n) requested
  cross join lateral (select
    not(p.f?'treatment') or exists(select 1 from public.scene_treatments st join public.treatments t on t.id=st.treatment_id where st.asset_id=a.id and lower(t.code)=lower(p.f->>'treatment'))
      or exists(select 1 from public.asset_search_documents d where d.asset_id=a.id and lower(coalesce(d.structured_document->>'treatment',''))=lower(p.f->>'treatment')) treatment_match,
    not(p.f?'anatomy') or exists(select 1 from public.scene_anatomy sa join public.anatomy_terms an on an.id=sa.anatomy_id left join public.anatomy_terms parent on parent.id=an.parent_id where sa.asset_id=a.id and (lower(an.code)=lower(p.f->>'anatomy') or lower(parent.code)=lower(p.f->>'anatomy')))
      or exists(select 1 from public.asset_search_documents d cross join lateral jsonb_array_elements_text(coalesce(d.structured_document->'anatomy','[]'::jsonb)) v where d.asset_id=a.id and lower(v.value)=lower(p.f->>'anatomy')) anatomy_match,
    not(p.f?'action') or exists(select 1 from public.scene_actions x join public.actions ac on ac.id=x.action_id where x.asset_id=a.id and lower(ac.code)=lower(p.f->>'action'))
      or exists(select 1 from public.asset_search_documents d cross join lateral jsonb_array_elements_text(coalesce(d.structured_document->'actions','[]'::jsonb)) v where d.asset_id=a.id and lower(v.value)=lower(p.f->>'action')) action_match,
    not(p.f?'role') or exists(select 1 from public.scene_people sp where sp.asset_id=a.id and lower(sp.person_role)=lower(p.f->>'role')) role_match,
    not(p.f?'scene_type') or exists(select 1 from public.asset_scenes s where s.asset_id=a.id and lower(s.scene_type)=lower(p.f->>'scene_type')) scene_type_match,
    not(p.f?'environment') or exists(select 1 from public.scene_environment e where e.asset_id=a.id and (lower(e.environment_type) like '%'||lower(p.f->>'environment')||'%' or (lower(p.f->>'environment')='clinic' and lower(e.environment_type) in ('treatment room','operating room')))) environment_match,
    not(p.f?'shot_type') or exists(select 1 from public.scene_cinematography c where c.asset_id=a.id and lower(c.shot_size) like '%'||lower(p.f->>'shot_type')||'%') shot_match,
    not(p.f?'content_type') or exists(select 1 from public.marketing_annotations m where m.asset_id=a.id and lower(m.marketing_role)=lower(p.f->>'content_type')) content_match) m
  cross join lateral (select (m.treatment_match::int+m.anatomy_match::int+m.action_match::int+m.role_match::int+m.scene_type_match::int+m.environment_match::int+m.shot_match::int+m.content_match::int - (8-requested.n)) n) matches
), scored as (
 select a.id,a.av,s.sv,s.kv,a.al,s.sl,st.ss,a.fn,s.best_scene,s.scene_start,s.scene_end,st.features,
   greatest(0,least(1,0.30*st.ss+0.20*s.sv+0.18*a.av+0.12*a.al+0.08*s.sl+0.07*s.kv+0.05*a.fn)) final
 from asset_signals a join scene_signals s on s.id=a.id join structured st on st.id=a.id
), relevant as (
 select * from scored cross join params p
 where final>=greatest(p.threshold,case
   when ss=0 and greatest(al,sl,fn)=0
    and lower(coalesce(p.q,'')) !~ '(hair|scalp|hairline|clinic|consultation|patient|clinician|doctor|treatment|procedure|transplant|injection|injecting|portrait|face|neck|graft|fue|b-?roll)'
   then 0.18 else 0 end)
   and (p.q is not null or visual_query_embedding is not null or ss>0)
), ranked as (
 select *,count(*) over() found from relevant order by final desc,id
)
select id,round((final*100)::numeric,2),round((av*100)::numeric,2),round((sv*100)::numeric,2),round((kv*100)::numeric,2),
 round((al*100)::numeric,2),round((sl*100)::numeric,2),round((ss*100)::numeric,2),round((fn*100)::numeric,2),
 best_scene,scene_start,scene_end,
 features||jsonb_build_object('ranking_version','job8-v3.5','signals',jsonb_build_object('visual_asset',av,'visual_scene',sv,'visual_keyframe',kv,'lexical_asset',al,'lexical_scene',sl,'structured',ss,'filename',fn)),
 concat_ws('; ',case when ss>0 then 'structured intent match' end,case when sv>0 then 'scene visual match' end,case when av>0 then 'asset visual match' end,case when greatest(al,sl)>0 then 'lexical evidence match' end,case when fn>0 then 'filename match' end),found
from ranked order by final desc,id limit(select lim from params) offset(select off from params)
$$;

comment on function public.hybrid_search_assets_v3(text,public.vector,jsonb,uuid[],integer,integer,numeric) is
'KDI AI Search V3 job8-v3.5: permission-prefiltered OpenCLIP visual, lexical and structured hybrid ranking. Inferred structured concepts are soft ranking evidence; explicit media, extension, exclusion, permission and eligibility filters remain mandatory. Weights and thresholds unchanged. Default 5, max 50.';
revoke all on function public.hybrid_search_assets_v3(text,public.vector,jsonb,uuid[],integer,integer,numeric) from public,anon,authenticated,service_role;
grant execute on function public.hybrid_search_assets_v3(text,public.vector,jsonb,uuid[],integer,integer,numeric) to authenticated,service_role;



;
