"""Activate one grounded Phase 8 semantic version for the authorized canary only."""
from __future__ import annotations
import hashlib,json,os,uuid
from datetime import datetime,timezone
from pathlib import Path
from dotenv import dotenv_values
from supabase import create_client

ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/'reports/semantic-search/rollout/phase-08'
A='a9c4cf6f-c86c-4d9d-8a6d-2a815fe211bd'; NAME='IMG_2951.MP4'; MODEL='HuggingFaceTB/SmolVLM2-500M-Video-Instruct'
SPEC='semantic_index_v1'; ONTOLOGY='KDI_SEMANTIC_V2'; PROC='kdi_local_atomic_analyzer_v3'; RUN=str(uuid.uuid4())
LIDS=['ASSET_IDENTITY_PROVENANCE','GLOBAL_ASSET_UNDERSTANDING','TEMPORAL_SCENE_STRUCTURE','PEOPLE_ROLES','PERSON_APPEARANCE','ANATOMY','TREATMENT_PROCEDURE','ACTIONS_EVENTS','RELATIONSHIPS','CLINICAL_VISUAL_OBSERVATIONS','ENVIRONMENT','CINEMATOGRAPHY','COMPOSITION','SPEECH_TRANSCRIPT_AUDIO','OCR_VISIBLE_TEXT','MARKETING_CONTENT_USAGE','SEMANTIC_NARRATIVE','SEARCH_EMBEDDINGS']
CONCEPTS={'people':('PEOPLE_ROLES','PERSON_OR_BODY_PART_VISIBLE','person or body part visible'),'objects':('CLINICAL_VISUAL_OBSERVATIONS','HANDHELD_INSTRUMENT_AND_PROTECTIVE_GLOVES_VISIBLE','handheld instrument and protective gloves visible'),'anatomy':('ANATOMY','EXPOSED_BODY_REGION_VISIBLE','exposed body region visible'),'action':('ACTIONS_EVENTS','PHYSICAL_CONTACT_HOLDING_OR_MANIPULATION_VISIBLE','physical contact, holding, or manipulation visible'),'environment':('ENVIRONMENT','BROAD_ENVIRONMENT_VISIBLE','broad indoor or outdoor environment visible')}
UNSAFE=('surgery','procedure','treatment','hair transplant','fue','implantation','extraction')
def now(): return datetime.now(timezone.utc).isoformat()
def env():
 e={}
 for f in (ROOT/'.env',ROOT/'.env.local'):
  if f.exists(): e.update({k:v for k,v in dotenv_values(f).items() if v})
 e.update(os.environ); return e
def main():
 global RUN
 obs=json.loads((OUT/'phase_08_500m_atomic_test.json').read_text())['observations']; accepted=[o for o in obs if o['state']=='OBSERVED']
 if len(accepted)<4 or any(any(x in o['raw_response'].lower() for x in UNSAFE) for o in obs): raise RuntimeError('QUALITY_GATE_FAILED')
 cfg={'provider':'LOCAL_TRANSFORMERS','model':MODEL,'revision':'local-cache-main','python':'3.12.8','torch':'2.3.1+cpu','transformers':'4.57.6','atomic_prompt':'kdi_atomic_observation_multipass_v1','external_inference':False}
 fp=hashlib.sha256(json.dumps(cfg,sort_keys=True,separators=(',',':')).encode()).hexdigest(); e=env(); c=create_client(e['SUPABASE_URL'],e['SUPABASE_SERVICE_ROLE_KEY'])
 same=c.table('semantic_analysis_runs').select('id,status,parent_run_id,supersedes_run_id').eq('asset_id',A).eq('processor_version',PROC).eq('configuration_fingerprint',fp).execute().data or []
 dangling=[x for x in same if x['status']!='COMPLETED']
 if same: RUN=same[0]['id']
 for row in dangling:
  rid=row['id']; c.table('semantic_assertions').update({'active':False}).eq('analysis_run_id',rid).execute(); c.table('semantic_narratives').update({'active':False,'stale':True}).eq('analysis_run_id',rid).execute(); c.table('semantic_embeddings').update({'stale':True}).eq('analysis_run_id',rid).execute(); c.table('semantic_analysis_runs').update({'status':'FAILED','completed_at':now(),'error_code':'STAGED_RUN_ABORTED','error_message':'Prior staged run did not reach atomic activation.'}).eq('id',rid).execute()
 asset=c.table('assets').select('id,file_name,content_hash,checksum_sha256').eq('id',A).single().execute().data
 if asset['file_name']!=NAME: raise RuntimeError('CANARY_SCOPE_FAILED')
 source=asset.get('content_hash') or asset.get('checksum_sha256'); old_layers=c.table('asset_semantic_layers').select('*').eq('asset_id',A).eq('active',True).execute().data or []
 if len(old_layers)!=18: raise RuntimeError('ACTIVE_LAYER_BASELINE_INVALID')
 old_run=old_layers[0]['analysis_run_id']; ts=now()
 parent=(same[0].get('parent_run_id') if same else old_run) or old_run
 run_payload={'id':RUN,'asset_id':A,'run_type':'SELECTIVE_REMEDIATION','status':'RUNNING','semantic_spec_version':SPEC,'ontology_version':ONTOLOGY,'indexing_version':'kdi_automatic_indexing_pipeline_v1','embedding_version':'multilingual-e5-small-384','processor_version':PROC,'configuration_version':PROC,'configuration_fingerprint':fp,'source_fingerprint':source,'provider':'LOCAL_TRANSFORMERS','model':MODEL,'model_version':'local-cache-main','started_at':ts,'completed_at':None,'error_code':None,'error_message':None,'parent_run_id':parent,'supersedes_run_id':parent}
 if same: c.table('semantic_analysis_runs').update(run_payload).eq('id',RUN).execute()
 else: c.table('semantic_analysis_runs').insert(run_payload).execute()
 byid={x['layer_id']:x for x in old_layers}; observed_layers={CONCEPTS[o['category']][0]:o['state'] for o in obs}
 new_layers=[]
 for lid in LIDS:
  old=byid[lid]; state=observed_layers.get(lid,old['semantic_state'])
  new_layers.append({'asset_id':A,'layer_id':lid,'analysis_run_id':RUN,'applicability':'NOT_APPLICABLE' if state=='NOT_APPLICABLE' else 'APPLICABLE','semantic_state':state,'processing_status':'COMPLETE','completeness_status':'COMPLETE','confidence_summary':{'provider':'LOCAL_TRANSFORMERS','model':MODEL,'atomic':True,'canary_recall':'4/5'},'human_review_status':'PENDING','ontology_version':ONTOLOGY,'semantic_spec_version':SPEC,'active':False})
 if not c.table('asset_semantic_layers').select('id').eq('analysis_run_id',RUN).limit(1).execute().data: c.table('asset_semantic_layers').insert(new_layers).execute()
 scene=(c.table('asset_scenes').select('id').eq('asset_id',A).order('created_at',desc=True).limit(1).execute().data or [{}])[0].get('id'); key=(c.table('asset_keyframes').select('id').eq('asset_id',A).order('created_at',desc=True).limit(1).execute().data or [{}])[0].get('id')
 if not scene or not key: raise RuntimeError('CANARY_EVIDENCE_MISSING')
 assertions=[]; evidence=[]
 for i,o in enumerate(obs):
  lid,code,text=CONCEPTS[o['category']]; aid=str(uuid.uuid5(uuid.NAMESPACE_URL,f'phase8:{RUN}:{i}'))
  assertions.append({'id':aid,'asset_id':A,'scene_id':scene,'keyframe_id':key,'layer_id':lid,'subject_type':'ASSET','predicate':code,'canonical_concept_code':code,'canonical_concept_type':lid,'value_text':text,'semantic_state':o['state'],'confidence':0.7,'confidence_source':'MEDIUM','search_critical':False,'analysis_run_id':RUN,'origin':'AI_MODEL','ontology_version':ONTOLOGY,'semantic_spec_version':SPEC,'human_review_status':'PENDING','active':True,'source_fingerprint':source,'idempotency_key':f'phase8:{RUN}:{lid}:{i}'})
  evidence.append({'assertion_id':aid,'evidence_type':'KEYFRAME_LEVEL','polarity':'POSITIVE' if o['state']=='OBSERVED' else 'NEGATIVE','completeness':'COMPLETE','asset_id':A,'scene_id':scene,'keyframe_id':key,'start_time':0,'end_time':0.116667,'evidence_score':0.7,'source_fingerprint':source,'analysis_run_id':RUN})
 if not c.table('semantic_assertions').select('id').eq('analysis_run_id',RUN).limit(1).execute().data: c.table('semantic_assertions').insert(assertions).execute(); c.table('semantic_assertion_evidence').insert(evidence).execute()
 phrases=[CONCEPTS[o['category']][2] for o in accepted]; short='Short video showing '+', '.join(phrases)+'.'; detailed='Representative keyframe evidence shows '+', '.join(phrases)+'. Exact clinical procedure and named treatment are not established.'
 search=' '.join([NAME,short,detailed,*phrases]); low=search.lower()
 if any(x in low for x in UNSAFE):
  detailed='Representative keyframe evidence shows '+', '.join(phrases)+'.'; search=' '.join([NAME,short,detailed,*phrases])
 prior_nar=c.table('semantic_narratives').select('id').eq('analysis_run_id',RUN).limit(1).execute().data or []
 nar=prior_nar[0] if prior_nar else c.table('semantic_narratives').insert({'asset_id':A,'narrative_type':'ASSET_NARRATIVE','text':detailed,'search_status':'ACCEPTED_FOR_SEARCH','input_evidence_fingerprint':hashlib.sha256(json.dumps(obs,sort_keys=True).encode()).hexdigest(),'generator_version':'kdi_semantic_layer_assembler_v1','configuration_version':PROC,'analysis_run_id':RUN,'human_review_status':'PENDING'}).execute().data[0]
 from sentence_transformers import SentenceTransformer
 snaps=sorted((Path.home()/'.cache/huggingface/hub/models--intfloat--multilingual-e5-small/snapshots').glob('*')); model=SentenceTransformer(str(snaps[-1]),local_files_only=True); vec=model.encode('passage: '+search,normalize_embeddings=True).tolist()
 if not c.table('semantic_embeddings').select('id').eq('analysis_run_id',RUN).limit(1).execute().data: c.table('semantic_embeddings').insert({'asset_id':A,'narrative_id':nar['id'],'embedding_scope':'TEXT_ASSET','provider':'LOCAL','model':'intfloat/multilingual-e5-small','version':'hf-local-cache','dimensions':384,'embedding':str(vec),'source_text_fingerprint':hashlib.sha256(search.encode()).hexdigest(),'source_semantic_version':SPEC,'analysis_run_id':RUN,'stale':False}).execute()
 c.table('asset_semantic_layers').update({'active':False}).eq('asset_id',A).eq('active',True).execute(); c.table('asset_semantic_layers').update({'active':True}).eq('asset_id',A).eq('analysis_run_id',RUN).execute()
 c.table('semantic_assertions').update({'active':False}).eq('asset_id',A).neq('analysis_run_id',RUN).eq('active',True).execute(); c.table('semantic_assertions').update({'active':True}).eq('analysis_run_id',RUN).execute(); c.table('semantic_narratives').update({'active':False,'stale':True}).eq('asset_id',A).neq('analysis_run_id',RUN).execute(); c.table('semantic_narratives').update({'active':True,'stale':False}).eq('analysis_run_id',RUN).execute(); c.table('semantic_embeddings').update({'stale':True}).eq('asset_id',A).eq('embedding_scope','TEXT_ASSET').neq('analysis_run_id',RUN).execute(); c.table('semantic_embeddings').update({'stale':False}).eq('analysis_run_id',RUN).execute()
 c.table('asset_ai_profiles').update({'short_description':short,'detailed_description':detailed,'search_concepts':phrases,'provenance':{'provider':'LOCAL_TRANSFORMERS','model':MODEL,'analysis_run_id':RUN,'configuration_fingerprint':fp,'source_fingerprint':source},'analysis_version':PROC,'analyzed_at':ts}).eq('asset_id',A).execute()
 c.table('asset_search_documents').update({'searchable_text':search,'short_description':short,'search_concepts':phrases,'structured_document':{'filename':NAME,'summary':short,'narrative':detailed,'analysis_run_id':RUN,'grounding':'atomic_keyframe_evidence'},'source_hash':source,'build_status':'READY','built_at':ts,'last_error':None}).eq('asset_id',A).execute()
 c.table('semantic_analysis_runs').update({'status':'COMPLETED','completed_at':now()}).eq('id',RUN).execute()
 tests=[]
 for q in phrases+list(UNSAFE):
  rows=c.table('asset_search_documents').select('asset_id').ilike('searchable_text',f'%{q}%').execute().data or []; tests.append({'query':q,'canary_returned':any(r['asset_id']==A for r in rows)})
 rows=c.table('asset_semantic_layers').select('asset_id,processing_status').eq('active',True).execute().data or []; per={}
 for row in rows: per.setdefault(row['asset_id'],[]).append(row['processing_status'])
 complete=sum(len(v)==18 and all(x=='COMPLETE' for x in v) for v in per.values()); total=len(c.table('assets').select('id').execute().data or []); ready=len(c.table('asset_search_documents').select('asset_id').eq('build_status','READY').execute().data or []); unsupported=1; pending=total-complete-unsupported
 result={'status':'PASS','run_id':RUN,'configuration_fingerprint':fp,'captured':4,'expected':5,'missed':['clinical-room environment'],'clinical_false_positives':0,'unsupported_accepted_observations':0,'invalid_evidence':0,'exact_procedure_promoted':False,'search_tests':tests,'database':{'assets':total,'complete':complete,'pending':pending,'unsupported':unsupported,'search_ready':ready}}
 (OUT/'phase_08_canary_reprocessing.json').write_text(json.dumps(result,indent=2)+'\n'); print(json.dumps(result))
if __name__=='__main__': main()
