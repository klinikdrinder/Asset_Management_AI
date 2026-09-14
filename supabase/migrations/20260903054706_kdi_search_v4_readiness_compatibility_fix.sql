begin;
create or replace view public.kdi_search_ready_assets_v1 with(security_invoker=true) as
with layers as (
 select asset_id,count(*) layer_count,
  bool_and(processing_status='COMPLETE' and completeness_status in('COMPLETE','NOT_APPLICABLE')) layers_complete
 from public.asset_semantic_layers where active group by asset_id
), docs as (
 select asset_id,count(*) filter(where document_type='ASSET' and status='READY' and active and not stale) asset_docs,
  count(*) filter(where document_type='SCENE' and status='READY' and active and not stale) scene_docs
 from public.search_document_builds group by asset_id
), scenes as (
 select asset_id,count(*) scenes,bool_and(start_seconds<end_seconds and coalesce(short_description,literal_description,'')<>'') scenes_valid
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
 coalesce(l.layer_count,0)=18 and coalesce(l.layers_complete,false) and coalesce(d.asset_docs,0)=1 and coalesce(e.text_asset,0)=1
 and (coalesce(e.canonical_visual_asset,0)=1 or coalesce(v.visual_asset,0)=1)
 and (case when a.mime_type like 'video/%' then coalesce(s.scenes,0)>0 and coalesce(s.scenes_valid,false)
  and coalesce(d.scene_docs,0)=coalesce(s.scenes,0) and coalesce(e.text_scene,0)=coalesce(s.scenes,0)
  and coalesce(e.visual_scene,0)=coalesce(s.scenes,0) and coalesce(k.keyframes,0)>0 and coalesce(e.visual_keyframe,0)=coalesce(k.keyframes,0)
  else true end) search_ready,
 coalesce(l.layer_count,0) layer_count,coalesce(d.asset_docs,0) asset_document_count,
 coalesce(s.scenes,0) canonical_scene_count,coalesce(d.scene_docs,0) scene_document_count
from public.assets a left join layers l on l.asset_id=a.id left join docs d on d.asset_id=a.id left join scenes s on s.asset_id=a.id
left join keys k on k.asset_id=a.id left join emb e on e.asset_id=a.id left join legacy_visual v on v.asset_id=a.id;
comment on view public.kdi_search_ready_assets_v1 is 'Sole derived SEARCH_READY authority for KDI_SEARCH_V4_CANONICAL; mixed historical spec lineage is accepted only when exactly 18 active layers independently pass completeness.';
commit;
