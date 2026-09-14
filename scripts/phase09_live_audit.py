import json,os
from pathlib import Path
from dotenv import dotenv_values
from supabase import create_client
R=Path(__file__).resolve().parents[1]; A='a9c4cf6f-c86c-4d9d-8a6d-2a815fe211bd'
e={}
for f in (R/'.env',R/'.env.local',R/'dashboard/.env.local'):
 if f.exists(): e.update({k:v for k,v in dotenv_values(f).items() if v})
e.update(os.environ); url=e.get('SUPABASE_URL') or e.get('NEXT_PUBLIC_SUPABASE_URL'); key=e.get('SUPABASE_SERVICE_ROLE_KEY')
c=create_client(url,key)
def rows(t,fields='*'):
 q=c.table(t).select(fields).eq('asset_id',A)
 return q.execute().data or []
out={'asset':c.table('assets').select('id,file_name,mime_type,file_extension').eq('id',A).single().execute().data,
 'profile':rows('asset_ai_profiles'), 'asset_search_documents':rows('asset_search_documents'),
 'search_document_builds':rows('search_document_builds'), 'semantic_embeddings':rows('semantic_embeddings','id,asset_id,embedding_scope,provider,model,version,dimensions,source_text_fingerprint,source_semantic_version,analysis_run_id,stale'),
 'visual_embeddings':rows('asset_visual_embeddings','id,asset_id,model_provider,model_name,model_version,embedding_dimensions'),
 'assertions':rows('semantic_assertions','id,asset_id,layer_id,canonical_concept_code,value_text,semantic_state,analysis_run_id,active'),
 'layers':rows('asset_semantic_layers','id,asset_id,layer_id,semantic_state,processing_status,analysis_run_id,active'),
 'acl':rows('asset_access_control'),
 'active_users':c.table('app_users').select('user_id,is_active,can_view_clinical,can_download').eq('is_active',True).limit(3).execute().data or [],
 'pilot_acl':c.table('asset_access_control').select('asset_id,classification_status,is_clinical,sensitivity_level,internal_usage_status,requires_clinical_permission,download_allowed').in_('asset_id',['7f72217d-3839-4920-86b4-ccc33e9e3d95','babae120-9372-42ad-b535-02a3276ea2be','c86344e9-5b32-4d86-9205-67952d508651','444da390-0117-4380-8c87-d7c32f2903ff','37838d30-a0ce-4f90-8cc3-c986db0aaa65','6215ad8b-12be-4a8e-bc49-f6b3dcf55c21','64712c6a-c02c-46e9-9f73-16786109468b','47611c6d-7923-42a4-87b6-c2a416a90f5c','bfae6c51-5d71-47ae-a3e1-6d07092b8896','753eb5f3-82c7-4148-a226-d5b960fd8619']).execute().data or []}
out['sample_search_document_builds']=c.table('search_document_builds').select('*').eq('active',True).eq('stale',False).limit(2).execute().data or []
out['sample_current_text_embeddings']=c.table('semantic_embeddings').select('id,asset_id,embedding_scope,representation_type,provider,model,version,model_version,dimensions,embedding_version,embedding_bundle_version,preprocessing_version,text_normalization_version,source_fingerprint,source_document_fingerprint,source_text_fingerprint,source_semantic_version,semantic_spec_version,ontology_version,vector_fingerprint,analysis_run_id,stale,active').eq('representation_type','TEXT_ASSET').eq('active',True).eq('stale',False).limit(2).execute().data or []
for table in ('asset_embeddings','visual_embeddings','keyframe_embeddings'):
 try: out[table]=rows(table)
 except Exception as ex: out[table]={'error':type(ex).__name__}
artifact=R/'reports'/'semantic-search'/'rollout'/'phase-09'/'phase_09_live_audit.json'
artifact.parent.mkdir(parents=True,exist_ok=True)
artifact.write_text(json.dumps(out,default=str,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'status':'PASS','artifact':str(artifact),'visual_rows':len(out['visual_embeddings']) if isinstance(out['visual_embeddings'],list) else 0,'pilot_acl_rows':len(out['pilot_acl'])}))
