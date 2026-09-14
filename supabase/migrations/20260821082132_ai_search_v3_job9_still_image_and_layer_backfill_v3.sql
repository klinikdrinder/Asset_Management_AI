insert into public.asset_technical_metadata(asset_id,provenance,metadata)
select a.id,'ASSET_BASE_FIELDS_ONLY',jsonb_build_object('base_mime_type',a.mime_type,'base_file_size_bytes',coalesce(a.size_bytes,a.file_size_bytes),'advanced_extraction_required',true)
from public.assets a
on conflict (asset_id) do nothing;

insert into public.asset_scenes(
  asset_id,scene_index,start_seconds,end_seconds,scene_type,
  literal_description,short_description,primary_treatment_id,primary_anatomy_id,primary_location_id,
  analysis_run_id,detection_method,confidence,review_status,metadata
)
select
  a.id,0,0,0,'STILL_IMAGE',
  p.detailed_description,p.short_description,p.primary_treatment_id,p.primary_anatomy_id,p.primary_location_id,
  case when (p.provenance->>'analysis_run_id') ~* '^[0-9a-f-]{36}$' then (p.provenance->>'analysis_run_id')::uuid else null end,
  case when p.analysis_status='completed' then 'IMAGE_SINGLE_FRAME_AI_PROFILE' else 'IMAGE_SINGLE_FRAME_PLACEHOLDER' end,
  case when (sd.structured_document#>>'{evidence,confidence}') ~ '^[0-9]+(\.[0-9]+)?$' then (sd.structured_document#>>'{evidence,confidence}')::numeric else null end,
  case when p.analysis_status='completed' then 'AI_SUGGESTED' else 'NOT_REVIEWED' end,
  jsonb_build_object('synthetic_still_scene',true,'source_profile_status',coalesce(p.analysis_status,'MISSING'))
from public.assets a
left join public.asset_ai_profiles p on p.asset_id=a.id
left join public.asset_search_documents sd on sd.asset_id=a.id
where a.mime_type like 'image/%'
  and not exists (select 1 from public.asset_scenes s where s.asset_id=a.id and s.scene_index=0)
on conflict (asset_id,scene_index) do nothing;

insert into public.asset_keyframes(asset_id,scene_id,timestamp_seconds,frame_index,selection_reason,visual_description,semantic_importance_score,analysis_run_id,is_representative,review_status,metadata)
select s.asset_id,s.id,0,0,'STILL_IMAGE_SOURCE',coalesce(s.literal_description,s.short_description),1,s.analysis_run_id,true,
       case when s.review_status='AI_SUGGESTED' then 'PENDING' else 'NOT_REVIEWED' end,
       jsonb_build_object('still_image_source',true)
from public.asset_scenes s
where s.scene_type='STILL_IMAGE'
  and not exists (select 1 from public.asset_keyframes k where k.scene_id=s.id and k.timestamp_seconds=0);

insert into public.scene_people(scene_id,asset_id,person_id,person_role,gender,exact_age,age_min,age_max,activity_summary,position_summary,identity_status,confidence,provenance,analysis_run_id,metadata)
select s.id,s.asset_id,null,
       case when lower(coalesce(p.category,'')) like '%doctor%' then 'DOCTOR' else 'SUBJECT' end,
       p.patient_gender,p.patient_age_exact,p.patient_age_min,p.patient_age_max,p.patient_activity,p.patient_position,
       'ANONYMOUS',s.confidence,'AI_VISUAL',s.analysis_run_id,jsonb_build_object('source','asset_ai_profiles','still_image',true)
from public.asset_scenes s
join public.asset_ai_profiles p on p.asset_id=s.asset_id
where s.scene_type='STILL_IMAGE' and p.number_of_people=1
  and not exists (select 1 from public.scene_people sp where sp.scene_id=s.id);

insert into public.scene_narratives(scene_id,asset_id,narrative_type,text,confidence,provenance,analysis_run_id,review_status)
select s.id,s.asset_id,'LITERAL',coalesce(s.literal_description,s.short_description),s.confidence,'AI_VISUAL',s.analysis_run_id,'NOT_REVIEWED'
from public.asset_scenes s
where s.scene_type='STILL_IMAGE'
  and coalesce(btrim(s.literal_description),btrim(s.short_description),'') <> ''
on conflict (scene_id,narrative_type,text) do nothing;

insert into public.scene_anatomy(scene_id,asset_id,anatomy_id,relationship_type,confidence,provenance,analysis_run_id,is_primary)
select s.id,s.asset_id,at.id,'VISIBLE',s.confidence,'AI_VISUAL',s.analysis_run_id,
       coalesce(at.id=s.primary_anatomy_id,false)
from public.asset_scenes s
join public.asset_search_documents sd on sd.asset_id=s.asset_id
cross join lateral jsonb_array_elements_text(coalesce(sd.structured_document->'anatomy','[]'::jsonb)) j(code)
join public.anatomy_terms at on at.code=j.code
where s.scene_type='STILL_IMAGE'
  and not exists (
    select 1 from public.scene_anatomy sa where sa.scene_id=s.id and sa.anatomy_id=at.id and sa.relationship_type='VISIBLE'
  );

insert into public.clinical_observations(asset_id,scene_id,keyframe_id,scene_person_id,anatomy_id,definition_id,observation_domain,observation_type,value_boolean,confidence,source_type,verification_status,analysis_run_id,evidence,metadata)
select s.asset_id,s.id,k.id,sp.id,at.id,d.id,'HAIR',d.code,true,s.confidence,'AI_VISUAL','AI_SUGGESTED',s.analysis_run_id,
       jsonb_build_object('derived_from','existing_pilot_search_document','summary',sd.short_description),
       jsonb_build_object('migration_rule','explicit_phrase_mapping_only')
from public.asset_scenes s
join public.asset_search_documents sd on sd.asset_id=s.asset_id
join public.clinical_observation_definitions d on d.code='FRONTAL_THINNING_VISIBLE'
left join public.asset_keyframes k on k.scene_id=s.id and k.is_representative=true
left join public.scene_people sp on sp.scene_id=s.id
left join public.anatomy_terms at on at.code='FRONTAL_SCALP'
where s.scene_type='STILL_IMAGE'
  and lower(coalesce(sd.searchable_text,'')) like '%visible hair thinning%'
  and not exists (select 1 from public.clinical_observations co where co.scene_id=s.id and co.definition_id=d.id);

insert into public.clinical_observations(asset_id,scene_id,keyframe_id,scene_person_id,anatomy_id,definition_id,observation_domain,observation_type,value_boolean,confidence,source_type,verification_status,analysis_run_id,evidence,metadata)
select s.asset_id,s.id,k.id,sp.id,at.id,d.id,'HAIR',d.code,true,s.confidence,'AI_VISUAL','AI_SUGGESTED',s.analysis_run_id,
       jsonb_build_object('derived_from','existing_pilot_search_document','summary',sd.short_description),
       jsonb_build_object('migration_rule','explicit_anatomy_mapping_only')
from public.asset_scenes s
join public.asset_search_documents sd on sd.asset_id=s.asset_id
join public.clinical_observation_definitions d on d.code='HAIRLINE_VISIBLE'
left join public.asset_keyframes k on k.scene_id=s.id and k.is_representative=true
left join public.scene_people sp on sp.scene_id=s.id
left join public.anatomy_terms at on at.code='FRONTAL_HAIRLINE'
where s.scene_type='STILL_IMAGE'
  and coalesce(sd.structured_document->'anatomy','[]'::jsonb) ? 'FRONTAL_HAIRLINE'
  and not exists (select 1 from public.clinical_observations co where co.scene_id=s.id and co.definition_id=d.id);

insert into public.asset_layer_status(asset_id,layer_code,status,coverage_score,evidence_count,metadata)
select a.id,l.layer_code,
       case
         when l.scope='VIDEO' and a.mime_type not like 'video/%' then 'NOT_APPLICABLE'
         when l.scope='VIDEO_AUDIO' and a.mime_type not like 'video/%' then 'NOT_APPLICABLE'
         else 'NOT_STARTED'
       end,
       0,0,'{}'::jsonb
from public.assets a cross join public.semantic_layer_catalog l
on conflict (asset_id,layer_code) do nothing;

update public.asset_layer_status
set status='PARTIAL',coverage_score=0.35,evidence_count=1,updated_at=now(),metadata=jsonb_build_object('reason','base asset metadata present; advanced technical extraction pending')
where layer_code='TECHNICAL_METADATA' and status <> 'NOT_APPLICABLE';

update public.asset_layer_status als
set status='COMPLETE',coverage_score=1,evidence_count=q.cnt,updated_at=now(),metadata=jsonb_build_object('reason','representative keyframe exists')
from (select asset_id,count(*) cnt from public.asset_keyframes group by asset_id) q
where als.asset_id=q.asset_id and als.layer_code='KEYFRAMES';

update public.asset_layer_status als set status='PARTIAL',coverage_score=0.5,evidence_count=q.cnt,updated_at=now()
from (select asset_id,count(*) cnt from public.scene_people group by asset_id) q where als.asset_id=q.asset_id and als.layer_code='PERSON_APPEARANCE';
update public.asset_layer_status als set status='PARTIAL',coverage_score=0.5,evidence_count=q.cnt,updated_at=now()
from (select asset_id,count(*) cnt from public.clinical_observations group by asset_id) q where als.asset_id=q.asset_id and als.layer_code='CLINICAL_VISUAL';
update public.asset_layer_status als set status='PARTIAL',coverage_score=0.5,evidence_count=q.cnt,updated_at=now()
from (select asset_id,count(*) cnt from public.clinical_observations where observation_domain='AESTHETIC_FACE' group by asset_id) q where als.asset_id=q.asset_id and als.layer_code='AESTHETIC_FACIAL';
update public.asset_layer_status als set status='PARTIAL',coverage_score=0.5,evidence_count=q.cnt,updated_at=now()
from (select asset_id,count(*) cnt from public.scene_treatments group by asset_id) q where als.asset_id=q.asset_id and als.layer_code='TREATMENT';
update public.asset_layer_status als set status='PARTIAL',coverage_score=0.5,evidence_count=q.cnt,updated_at=now()
from (select asset_id,count(*) cnt from public.scene_actions group by asset_id) q where als.asset_id=q.asset_id and als.layer_code='ACTION';
update public.asset_layer_status als set status='PARTIAL',coverage_score=0.5,evidence_count=q.cnt,updated_at=now()
from (select asset_id,count(*) cnt from public.scene_relationships group by asset_id) q where als.asset_id=q.asset_id and als.layer_code='RELATIONSHIP';
update public.asset_layer_status als set status='PARTIAL',coverage_score=0.5,evidence_count=q.cnt,updated_at=now()
from (select asset_id,count(*) cnt from public.scene_environment group by asset_id) q where als.asset_id=q.asset_id and als.layer_code='ENVIRONMENT';
update public.asset_layer_status als set status='PARTIAL',coverage_score=0.5,evidence_count=q.cnt,updated_at=now()
from (select asset_id,count(*) cnt from public.scene_cinematography group by asset_id) q where als.asset_id=q.asset_id and als.layer_code='CINEMATOGRAPHY';
update public.asset_layer_status als set status='PARTIAL',coverage_score=0.5,evidence_count=q.cnt,updated_at=now()
from (select asset_id,count(*) cnt from public.scene_composition group by asset_id) q where als.asset_id=q.asset_id and als.layer_code='COMPOSITION';
update public.asset_layer_status als set status='PARTIAL',coverage_score=0.5,evidence_count=q.cnt,updated_at=now()
from (select asset_id,count(*) cnt from public.marketing_annotations group by asset_id) q where als.asset_id=q.asset_id and als.layer_code='MARKETING_STORY';
update public.asset_layer_status als set status='PARTIAL',coverage_score=0.5,evidence_count=q.cnt,updated_at=now()
from (select asset_id,count(*) cnt from public.scene_narratives group by asset_id) q where als.asset_id=q.asset_id and als.layer_code='SEMANTIC_NARRATIVE';
update public.asset_layer_status als set status='COMPLETE',coverage_score=1,evidence_count=q.cnt,updated_at=now()
from (select asset_id,count(*) cnt from public.asset_scenes where scene_type<>'STILL_IMAGE' group by asset_id) q where als.asset_id=q.asset_id and als.layer_code='VIDEO_TIMELINE';
update public.asset_layer_status als set status='PARTIAL',coverage_score=0.5,evidence_count=q.cnt,updated_at=now()
from (select asset_id,count(*) cnt from public.asset_transcript_chunks group by asset_id) q where als.asset_id=q.asset_id and als.layer_code='AUDIO_TRANSCRIPT';
update public.asset_layer_status als set status='PARTIAL',coverage_score=0.5,evidence_count=q.cnt,updated_at=now()
from (select asset_id,count(*) cnt from public.ocr_observations group by asset_id) q where als.asset_id=q.asset_id and als.layer_code='OCR';
update public.asset_layer_status als set status='PARTIAL',coverage_score=0.6,evidence_count=q.cnt,updated_at=now()
from (
 select asset_id,count(*) cnt from (
   select asset_id from public.asset_embeddings union all
   select asset_id from public.asset_visual_embeddings union all
   select asset_id from public.scene_embeddings union all
   select asset_id from public.keyframe_embeddings union all
   select asset_id from public.transcript_embeddings
 ) e group by asset_id
) q where als.asset_id=q.asset_id and als.layer_code='EMBEDDINGS';;
