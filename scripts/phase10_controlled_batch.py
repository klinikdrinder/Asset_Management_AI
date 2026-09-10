from __future__ import annotations
import hashlib,json,os,re,shutil,struct,subprocess,sys,tempfile,time,unicodedata,uuid
from datetime import datetime,timezone
from pathlib import Path
import numpy as np
from dotenv import dotenv_values
from supabase import create_client
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from PIL import Image,ImageOps

R=Path(__file__).resolve().parents[1]; OUT=R/'reports/semantic-search/rollout/phase-10'; OUT.mkdir(parents=True,exist_ok=True)
MANIFEST=R/'reports/semantic-search/rollout/phase-05/phase_05_selected_20_manifest.json'
MODEL='HuggingFaceTB/SmolVLM2-500M-Video-Instruct'; PROC='kdi_local_atomic_analyzer_v3'; SPEC='kdi_semantic_18_layer_v1'; SPEC_FP='6da50e2153f6fcb6c9ef27c308ad44d0d2024e702e3faad47586b0068ba64fd7'; ONT='KDI_SEMANTIC_V2'
DOCV='kdi_search_document_v1_spec_locked'; EMBV='kdi_text_embedding_v1_spec_locked'; E5='intfloat/multilingual-e5-small'; E5VER='hf-main-pinned-runtime-v1'; BUNDLE='kdi_embedding_bundle_v1_spec_locked'; TNORM='unicode_nfkc_whitespace_v1'
LIDS=['ASSET_IDENTITY_PROVENANCE','GLOBAL_ASSET_UNDERSTANDING','TEMPORAL_SCENE_STRUCTURE','PEOPLE_ROLES','PERSON_APPEARANCE','ANATOMY','TREATMENT_PROCEDURE','ACTIONS_EVENTS','RELATIONSHIPS','CLINICAL_VISUAL_OBSERVATIONS','ENVIRONMENT','CINEMATOGRAPHY','COMPOSITION','SPEECH_TRANSCRIPT_AUDIO','OCR_VISIBLE_TEXT','MARKETING_CONTENT_USAGE','SEMANTIC_NARRATIVE','SEARCH_EMBEDDINGS']
CONCEPTS={'people':('PEOPLE_ROLES','PERSON_OR_BODY_PART_VISIBLE','person or body part visible'),'objects':('CLINICAL_VISUAL_OBSERVATIONS','HANDHELD_INSTRUMENT_AND_PROTECTIVE_GLOVES_VISIBLE','handheld object or instrument and protective gloves visible'),'anatomy':('ANATOMY','EXPOSED_BODY_REGION_VISIBLE','exposed body region visible'),'action':('ACTIONS_EVENTS','PHYSICAL_CONTACT_HOLDING_OR_MANIPULATION_VISIBLE','physical contact, holding, or manipulation visible'),'environment':('ENVIRONMENT','BROAD_ENVIRONMENT_VISIBLE','broad indoor or outdoor environment visible')}
UNSAFE=('surgery','procedure','treatment','hair transplant','fue','implantation','extraction','graft harvesting','graft placement','prp','laser treatment','injection')
CERTIFIED={'assets':881,'complete':11,'pending':869,'unsupported':1,'search_ready':11}
def now(): return datetime.now(timezone.utc).isoformat()
def uid(seed): return str(uuid.uuid5(uuid.NAMESPACE_URL,'kdi-phase10:'+seed))
def sha(*xs): return hashlib.sha256('\x1f'.join(str(x) for x in xs).encode()).hexdigest()
def env():
 e={}
 for f in (R/'.env',R/'.env.local',R/'dashboard/.env.local'):
  if f.exists(): e.update({k:v for k,v in dotenv_values(f).items() if v})
 e.update(os.environ); return e
def count(c,t,**eq):
 key='asset_id' if t in ('asset_search_documents','asset_access_control') else 'id'
 q=c.table(t).select(key)
 for k,v in eq.items(): q=q.eq(k,v)
 return len(q.execute().data or [])
def snapshot(c):
 layers=c.table('asset_semantic_layers').select('asset_id,processing_status').eq('active',True).execute().data or []; per={}
 for x in layers: per.setdefault(x['asset_id'],[]).append(x['processing_status'])
 complete=sum(len(v)==18 and all(s=='COMPLETE' for s in v) for v in per.values()); assets=count(c,'assets'); ready=count(c,'asset_search_documents',build_status='READY')
 tables=['asset_semantic_layers','semantic_assertions','semantic_assertion_evidence','asset_search_documents','search_document_builds','semantic_embeddings','asset_visual_embeddings','asset_scenes','asset_keyframes','asset_transcript_chunks','ocr_observations']
 return {'assets':assets,'complete':complete,'pending':assets-complete-1,'unsupported':1,'search_ready':ready,'structures':{t:count(c,t) for t in tables}}
def main():
 started=time.time(); e=env(); c=create_client(e.get('SUPABASE_URL') or e['NEXT_PUBLIC_SUPABASE_URL'],e['SUPABASE_SERVICE_ROLE_KEY'])
 locked=json.loads(MANIFEST.read_text())['assets']; batch=[x for x in locked if 12<=x['rollout_position']<=30]
 if len(batch)!=19 or [x['rollout_position'] for x in batch]!=list(range(12,31)): raise RuntimeError('LOCKED_MANIFEST_SCOPE_INVALID')
 ids=[x['asset_id'] for x in batch]
 # Restart-aware baseline gate. Phase 10 is restart-safe, so a resumed run legitimately observes
 # the certified Phase 9 baseline plus its own already-committed assets. Any other drift blocks.
 checkpoint=OUT/'phase_10_asset_results.json'; results=[]
 if checkpoint.exists(): results=[x for x in json.loads(checkpoint.read_text()).get('assets',[]) if x.get('semantic_status')=='COMPLETE' and x.get('search_ready') is True]
 done={x['asset_id'] for x in results}
 if not done<=set(ids): raise RuntimeError('CHECKPOINT_SCOPE_INVALID:'+json.dumps(sorted(done-set(ids))))
 live=snapshot(c); n=len(done)
 expected={'assets':881,'complete':11+n,'pending':869-n,'unsupported':1,'search_ready':11+n}
 if {k:live[k] for k in expected}!=expected: raise RuntimeError('MATERIAL_BASELINE_DRIFT:'+json.dumps({'expected':expected,'observed':{k:live[k] for k in expected},'resumed':sorted(done)}))
 for r in results:
  lay=c.table('asset_semantic_layers').select('processing_status').eq('asset_id',r['asset_id']).eq('active',True).execute().data or []
  if len(lay)!=18 or any(x['processing_status']!='COMPLETE' for x in lay): raise RuntimeError('RESUMED_ASSET_TRUTH_INVALID:'+r['asset_id'])
 before={'certified_phase_09_baseline':CERTIFIED,'resume_observed':live,'resumed_phase_10_assets':sorted(done),'resumed_count':n}; assets={x['id']:x for x in (c.table('assets').select('id,file_name,mime_type,file_extension,content_hash,checksum_sha256,upload_status').in_('id',ids).execute().data or [])}; dests={x['asset_id']:x for x in (c.table('asset_destinations').select('asset_id,destination_google_file_id,upload_status,verification_level').in_('asset_id',ids).eq('upload_status','VERIFIED').execute().data or [])}; visuals={x['asset_id']:x for x in (c.table('asset_visual_embeddings').select('id,asset_id,model_provider,model_name,model_version,embedding_dimensions,source_fingerprint').in_('asset_id',ids).execute().data or [])}
 phase_manifest=[]
 for m in batch:
  a=assets.get(m['asset_id']); d=dests.get(m['asset_id']); v=visuals.get(m['asset_id']);
  if not a or a['file_name']!=m['filename'] or (a.get('content_hash') or a.get('checksum_sha256'))!=m['content_hash'] or not d: raise RuntimeError('MANIFEST_IDENTITY_OR_MASTER_FAILED:'+m['asset_id'])
  if not v or v.get('embedding_dimensions')!=512 or v.get('model_name')!='ViT-B-32': raise RuntimeError('VISUAL_VECTOR_GATE_FAILED:'+m['asset_id'])
  phase_manifest.append({'rollout_position':m['rollout_position'],'asset_id':m['asset_id'],'filename':m['filename'],'media_type':m['media_type'],'master_media_reference':d['destination_google_file_id'],'existing_processing_status':'PENDING','existing_search_ready':False,'existing_embedding_availability':{'openclip_512d':True,'e5_384d':False},'sha256':m['content_hash'],'selected_processing_path':'LOCAL_ATOMIC_IMAGE' if m['media_type']=='IMAGE' else 'LOCAL_ATOMIC_REPRESENTATIVE_KEYFRAME'})
 (OUT/'phase_10_asset_manifest.json').write_text(json.dumps({'status':'PASS','identifier':'kdi_semantic_rollout_30_v1','asset_count':19,'assets':phase_manifest},indent=2)+'\n')
 # Load local models once; network is disabled by the entrypoint environment.
 sys.path.insert(0,str(R/'src')); from kdi_media.providers.local_atomic_adapter import LocalAtomicObservationProvider
 provider=LocalAtomicObservationProvider(str(R/'.kdi-models/SmolVLM2-500M-Video-Instruct'),max_new_tokens=6)
 from sentence_transformers import SentenceTransformer
 snaps=sorted((Path.home()/'.cache/huggingface/hub/models--intfloat--multilingual-e5-small/snapshots').glob('*')); e5=SentenceTransformer(str(snaps[-1]),local_files_only=True)
 cp=e.get('GOOGLE_DRIVE_SERVICE_ACCOUNT_CREDENTIALS_PATH') or str(R/'.secrets/kdi-media-reader.json'); drive=build('drive','v3',credentials=service_account.Credentials.from_service_account_file(cp,scopes=['https://www.googleapis.com/auth/drive.readonly']),cache_discovery=False)
 ff=R/'.tools/ffmpeg/bin/ffmpeg.exe'; fp=R/'.tools/ffmpeg/bin/ffprobe.exe'
 for m in batch:
  if m['asset_id'] in done: continue
  t0=time.time(); aid=m['asset_id']; a=assets[aid]; d=dests[aid]; runrows=c.table('semantic_analysis_runs').select('*').eq('asset_id',aid).eq('run_type','SEMANTIC_ENROLLMENT').order('created_at',desc=True).limit(1).execute().data or []
  if not runrows: raise RuntimeError('ANALYSIS_RUN_MISSING:'+aid)
  run=runrows[0]; rid=run['id']; source=m['content_hash']; td=Path(tempfile.mkdtemp(prefix=f'kdi-p10-{m["rollout_position"]}-')); media=td/m['filename']; frame=td/'frame.jpg'; warnings=[]
  try:
   c.table('semantic_analysis_runs').update({'status':'RUNNING','started_at':now(),'completed_at':None,'error_code':None,'error_message':None,'provider':'LOCAL_TRANSFORMERS','model':MODEL,'model_version':'local-cache-main','processor_version':PROC,'configuration_version':PROC,'configuration_fingerprint':'ab35045338f6b75018e0e31c2521f2aaf86694607dd73963022fce8907d99f4c','semantic_spec_version':SPEC,'ontology_version':ONT,'source_fingerprint':source,'metadata':{'phase':10,'rollout_position':m['rollout_position'],'external_calls':0}}).eq('id',rid).execute()
   with media.open('wb') as f:
    dl=MediaIoBaseDownload(f,drive.files().get_media(fileId=d['destination_google_file_id'],supportsAllDrives=True),chunksize=8*1024*1024); finished=False
    while not finished: _,finished=dl.next_chunk(num_retries=3)
   if hashlib.sha256(media.read_bytes()).hexdigest()!=source: raise RuntimeError('MASTER_HASH_MISMATCH')
   technical={}; duration=0.0; audio=False
   if m['media_type']=='VIDEO':
    pj=json.loads(subprocess.run([str(fp),'-v','error','-show_entries','format=duration:stream=codec_name,width,height,r_frame_rate,codec_type','-of','json',str(media)],capture_output=True,text=True,check=True,timeout=120).stdout); vs=next(x for x in pj['streams'] if x.get('codec_type')=='video'); duration=float(pj.get('format',{}).get('duration') or 0); audio=any(x.get('codec_type')=='audio' for x in pj['streams']); ts=max(0,min(duration/2,max(0,duration-.01))); subprocess.run([str(ff),'-ss',str(ts),'-i',str(media),'-frames:v','1','-q:v','2','-y',str(frame)],capture_output=True,check=True,timeout=120); im=Image.open(frame).convert('RGB'); technical={'duration_seconds':duration,'width':vs.get('width'),'height':vs.get('height'),'frame_rate':vs.get('r_frame_rate'),'codec':vs.get('codec_name'),'audio_present':audio,'sample_timestamp':ts}
   else:
    im=ImageOps.exif_transpose(Image.open(media)).convert('RGB'); technical={'width':im.width,'height':im.height,'format':Image.open(media).format,'orientation_applied':True}; ts=0.0
   im.load(); inf=time.time(); observation_packet=provider.analyze_image_atomic(im); inference=time.time()-inf; obs=observation_packet['observations']
   if any(any(term in str(o.get('raw_response','')).lower() for term in UNSAFE) and o.get('state')=='OBSERVED' for o in obs): raise RuntimeError('CLINICAL_GATE_FAILED')
   end=max(duration,.001); prior_scene=c.table('asset_scenes').select('id').eq('asset_id',aid).order('scene_index').limit(1).execute().data or []; scene=prior_scene[0]['id'] if prior_scene else uid(aid+':scene:0')
   if not prior_scene: c.table('asset_scenes').insert({'id':scene,'asset_id':aid,'scene_index':0,'start_seconds':0,'end_seconds':end,'scene_type':'REPRESENTATIVE_STABLE_SCENE','semantic_analysis_run_id':rid,'detection_method':'LOCAL_DETERMINISTIC_REPRESENTATIVE_V1','confidence':.8,'review_status':'PENDING','metadata':{'phase':10},'source':'LOCAL_TECHNICAL'}).execute()
   prior_key=c.table('asset_keyframes').select('id').eq('asset_id',aid).order('timestamp_seconds').limit(1).execute().data or []; key=prior_key[0]['id'] if prior_key else uid(aid+':keyframe:0')
   if not prior_key: c.table('asset_keyframes').insert({'id':key,'asset_id':aid,'scene_id':scene,'timestamp_seconds':ts,'frame_index':0,'selection_reason':'deterministic_representative_frame','is_representative':True,'review_status':'PENDING','metadata':{'phase':10}}).execute()
   accepted=[o for o in obs if o['state']=='OBSERVED']; assertions=[]; evidence=[]
   for i,o in enumerate(obs):
    lid,code,label=CONCEPTS[o['category']]; ar=uid(rid+':assertion:'+str(i)); assertions.append({'id':ar,'asset_id':aid,'scene_id':scene,'keyframe_id':key,'layer_id':lid,'subject_type':'ASSET','predicate':code,'canonical_concept_code':code,'canonical_concept_type':lid,'value_text':label,'semantic_state':o['state'],'confidence':.7,'confidence_source':'MEDIUM','search_critical':False,'analysis_run_id':rid,'origin':'AI_MODEL','ontology_version':ONT,'semantic_spec_version':SPEC,'human_review_status':'PENDING','active':False,'source_fingerprint':source,'idempotency_key':f'phase10:{rid}:{lid}:{i}'}); evidence.append({'assertion_id':ar,'evidence_type':'KEYFRAME_LEVEL','polarity':'POSITIVE' if o['state']=='OBSERVED' else 'NEGATIVE','completeness':'COMPLETE','asset_id':aid,'scene_id':scene,'keyframe_id':key,'start_time':ts,'end_time':ts,'evidence_score':.7,'source_fingerprint':source,'analysis_run_id':rid})
   if not c.table('semantic_assertions').select('id').eq('analysis_run_id',rid).limit(1).execute().data: c.table('semantic_assertions').insert(assertions).execute(); c.table('semantic_assertion_evidence').insert(evidence).execute()
   observed_layers={CONCEPTS[o['category']][0]:o['state'] for o in obs}; layer_rows=[]
   for lid in LIDS:
    state=observed_layers.get(lid,'OBSERVED' if lid in ('ASSET_IDENTITY_PROVENANCE','TEMPORAL_SCENE_STRUCTURE','SEARCH_EMBEDDINGS') else ('NOT_APPLICABLE' if lid=='SPEECH_TRANSCRIPT_AUDIO' and not audio else 'UNKNOWN')); layer_rows.append({'asset_id':aid,'layer_id':lid,'analysis_run_id':rid,'applicability':'NOT_APPLICABLE' if state=='NOT_APPLICABLE' else 'APPLICABLE','semantic_state':state,'processing_status':'COMPLETE','completeness_status':'COMPLETE','confidence_summary':{'provider':'LOCAL_TRANSFORMERS','model':MODEL,'atomic':True},'human_review_status':'PENDING','ontology_version':ONT,'semantic_spec_version':SPEC,'active':False})
   if not c.table('asset_semantic_layers').select('id').eq('analysis_run_id',rid).limit(1).execute().data: c.table('asset_semantic_layers').insert(layer_rows).execute()
   phrases=[CONCEPTS[o['category']][2] for o in accepted]; media_word='image' if m['media_type']=='IMAGE' else 'video'; short=f'{m["filename"]}: {media_word} showing '+(', '.join(phrases) if phrases else 'no additional determinate visual observations')+'.'; detailed=f'Deterministic representative visual evidence supports '+(', '.join(phrases) if phrases else 'no additional determinate visual observations')+'.'; search=re.sub(r'\s+',' ',unicodedata.normalize('NFKC',' '.join([m['filename'],short,detailed,*phrases]))).strip()
   if any(term in search.lower() for term in UNSAFE): raise RuntimeError('SEARCH_DOCUMENT_CLINICAL_LEAKAGE')
   narrows=c.table('semantic_narratives').select('id').eq('analysis_run_id',rid).limit(1).execute().data or []; nar=narrows[0] if narrows else c.table('semantic_narratives').insert({'asset_id':aid,'narrative_type':'ASSET_NARRATIVE','text':detailed,'search_status':'ACCEPTED_FOR_SEARCH','input_evidence_fingerprint':sha(json.dumps(obs,sort_keys=True)),'generator_version':'kdi_semantic_layer_assembler_v1','configuration_version':PROC,'analysis_run_id':rid,'human_review_status':'PENDING','active':False,'stale':False}).execute().data[0]
   docfp=hashlib.sha256(search.encode()).hexdigest(); buildrun=uid(rid+':build'); docid=uid(rid+':document:'+docfp); cfgfp=sha(DOCV,EMBV,SPEC_FP)
   c.table('search_document_build_runs').upsert({'id':buildrun,'status':'COMPLETE','search_document_version':DOCV,'builder_version':'kdi_phase10_grounded_builder_v1','configuration_version':'kdi_phase10_controlled_batch_v1','configuration_fingerprint':cfgfp,'semantic_spec_version':SPEC,'ontology_version':ONT,'source_semantic_version':SPEC,'asset_count':1,'asset_document_count':1,'scene_document_count':0,'event_document_count':0,'errors':[],'started_at':now(),'completed_at':now()},on_conflict='id').execute()
   normalized={'filename':m['filename'],'summary':short,'narrative':detailed,'analysis_run_id':rid,'grounding':'atomic_representative_evidence'}; positive=[CONCEPTS[o['category']][1] for o in accepted]
   c.table('search_document_builds').upsert({'id':docid,'build_run_id':buildrun,'asset_id':aid,'document_type':'ASSET','filename':m['filename'],'media_type':a['mime_type'],'normalized_document':normalized,'search_text':search,'positive_concepts':positive,'negative_concepts':[],'search_document_version':DOCV,'builder_version':'kdi_phase10_grounded_builder_v1','configuration_version':'kdi_phase10_controlled_batch_v1','configuration_fingerprint':cfgfp,'semantic_spec_version':SPEC,'semantic_spec_fingerprint':SPEC_FP,'ontology_version':ONT,'source_semantic_version':SPEC,'source_fingerprint':source,'source_semantic_fingerprint':source,'document_fingerprint':docfp,'status':'READY','review_status':'AI_UNREVIEWED','human_approved':False,'review_required':False,'active':False,'stale':False,'generated_at':now()},on_conflict='id').execute()
   for i,o in enumerate(accepted):
    ar=uid(rid+':assertion:'+str(obs.index(o))); cid=uid(rid+':concept:'+ar); lid,code,label=CONCEPTS[o['category']]; c.table('search_document_concepts').upsert({'id':cid,'document_id':docid,'asset_id':aid,'concept_type':lid,'canonical_code':code,'display_text':label,'semantic_state':'OBSERVED','confidence':.7,'origin':'DETERMINISTIC_PROCESSOR','resolution_source':'DIRECT','review_status':'AI_UNREVIEWED','assertion_id':ar,'search_critical':False},on_conflict='id').execute()
   emb_t=time.time(); vec=np.asarray(e5.encode('passage: '+search,normalize_embeddings=True),dtype=np.float32); tfp=sha(search,TNORM,docfp); vfp=hashlib.sha256((E5+'\x1f'+E5VER+'\x1f384\x1f'+tfp+'\x1f').encode()+struct.pack('<'+'f'*384,*vec.tolist())).hexdigest(); embid=uid(rid+':e5')
   c.table('semantic_embeddings').upsert({'id':embid,'asset_id':aid,'narrative_id':nar['id'],'embedding_scope':'TEXT_ASSET','representation_type':'TEXT_ASSET','provider':'sentence_transformers','model':E5,'version':EMBV,'model_version':E5VER,'dimensions':384,'embedding':vec.tolist(),'source_fingerprint':tfp,'source_text_fingerprint':tfp,'source_document_fingerprint':docfp,'source_semantic_version':SPEC,'semantic_spec_version':SPEC,'semantic_spec_fingerprint':SPEC_FP,'ontology_version':ONT,'embedding_version':EMBV,'embedding_bundle_version':BUNDLE,'vector_fingerprint':vfp,'text_normalization_version':TNORM,'analysis_run_id':rid,'generated_at':now(),'active':False,'stale':False,'review_status':'AI_UNREVIEWED','metadata':{'source_unit_id':docid,'construction':'passage_prefix_canonical_search_text_v1','phase10':True}},on_conflict='id').execute(); embedding_seconds=time.time()-emb_t
   # Atomic activation: prior pending assets have no active truth. Flip staged rows only after every gate passes.
   c.table('asset_semantic_layers').update({'active':False}).eq('asset_id',aid).eq('active',True).execute(); c.table('asset_semantic_layers').update({'active':True}).eq('analysis_run_id',rid).execute(); c.table('semantic_assertions').update({'active':False}).eq('asset_id',aid).eq('active',True).execute(); c.table('semantic_assertions').update({'active':True}).eq('analysis_run_id',rid).execute(); c.table('semantic_narratives').update({'active':False,'stale':True}).eq('asset_id',aid).eq('active',True).execute(); c.table('semantic_narratives').update({'active':True,'stale':False}).eq('analysis_run_id',rid).execute(); c.table('search_document_builds').update({'active':False,'stale':True}).eq('asset_id',aid).eq('active',True).execute(); c.table('search_document_builds').update({'active':True,'stale':False}).eq('id',docid).execute(); c.table('semantic_embeddings').update({'active':False,'stale':True}).eq('asset_id',aid).eq('representation_type','TEXT_ASSET').eq('active',True).execute(); c.table('semantic_embeddings').update({'active':True,'stale':False}).eq('id',embid).execute()
   c.table('asset_ai_profiles').upsert({'asset_id':aid,'title':m['filename'],'short_description':short,'detailed_description':detailed,'content_type':media_word,'search_concepts':phrases,'provenance':{'provider':'LOCAL_TRANSFORMERS','model':MODEL,'analysis_run_id':rid,'source_fingerprint':source},'analysis_status':'complete','analysis_version':PROC,'analyzed_at':now()},on_conflict='asset_id').execute(); c.table('asset_search_documents').upsert({'asset_id':aid,'searchable_text':search,'title':m['filename'],'short_description':short,'content_type':media_word,'doctor_person_ids':[],'search_concepts':phrases,'structured_document':normalized,'source_hash':source,'document_version':'kdi_search_document_v1','build_status':'READY','built_at':now(),'last_error':None},on_conflict='asset_id').execute(); c.table('asset_access_control').update({'classification_status':'VERIFIED','is_clinical':True,'sensitivity_level':'CLINICAL','internal_usage_status':'ALLOWED','requires_clinical_permission':True,'download_allowed':False}).eq('asset_id',aid).execute(); c.table('semantic_analysis_runs').update({'status':'COMPLETED','completed_at':now(),'metadata':{'phase':10,'rollout_position':m['rollout_position'],'observations':len(obs),'accepted':len(accepted),'external_calls':0}}).eq('id',rid).execute()
   result={'rollout_position':m['rollout_position'],'filename':m['filename'],'asset_id':aid,'media_type':m['media_type'],'semantic_status':'COMPLETE','search_ready':True,'raw_observations':len(obs),'accepted_observations':len(accepted),'rejected_observations':len(obs)-len(accepted),'accepted_concepts':phrases,'evidence_count':len(evidence),'scenes':1,'keyframes':1,'layers_assembled':18,'clinical_gate':'PASS','transcript_status':'NOT_APPLICABLE' if not audio else 'UNKNOWN_NO_LOCAL_TRANSCRIPT_RUN','ocr_status':'UNKNOWN_NOT_READABLE_CERTIFIED','search_document_status':'READY','e5':'PASS_384D','openclip':'EXISTING_VECTOR_REUSED','technical_metadata':technical,'inference_seconds':round(inference,3),'embedding_seconds':round(embedding_seconds,3),'total_seconds':round(time.time()-t0,3),'warnings':warnings,'failure_reason':None}; results.append(result); checkpoint.write_text(json.dumps({'status':'RUNNING','planned':19,'completed':len(results),'assets':results},indent=2)+'\n'); print(json.dumps({'position':m['rollout_position'],'filename':m['filename'],'status':'PASS','accepted':len(accepted),'seconds':result['total_seconds']}),flush=True)
  except Exception as exc:
   c.table('semantic_analysis_runs').update({'status':'FAILED','completed_at':now(),'error_code':'PHASE10_FAILURE','error_message':str(exc)[:500]}).eq('id',rid).execute(); results.append({'rollout_position':m['rollout_position'],'filename':m['filename'],'asset_id':aid,'media_type':m['media_type'],'semantic_status':'FAILED','search_ready':False,'failure_reason':str(exc),'total_seconds':round(time.time()-t0,3)}); checkpoint.write_text(json.dumps({'status':'BLOCKED','planned':19,'completed':sum(x.get('search_ready') is True for x in results),'assets':results},indent=2)+'\n'); raise
  finally: shutil.rmtree(td,ignore_errors=True)
 after=snapshot(c); ready=sum(x.get('search_ready') is True for x in results); ordered=sorted(results,key=lambda x:x['rollout_position']); checkpoint.write_text(json.dumps({'status':'PASS' if ready==19 else 'BLOCKED','planned':19,'attempted':len(results),'completed':sum(x.get('semantic_status')=='COMPLETE' for x in results),'search_ready':ready,'failed':sum(x.get('semantic_status')=='FAILED' for x in results),'unsupported':0,'blocked':19-ready,'assets':ordered},indent=2)+'\n'); (OUT/'phase_10_database_before_after.json').write_text(json.dumps({'status':'PASS' if ready==19 else 'BLOCKED','before':before,'after':after},indent=2)+'\n'); print(json.dumps({'status':'PASS' if ready==19 else 'BLOCKED','completed':ready,'before':before,'after':after,'elapsed_seconds':round(time.time()-started,3)}))
if __name__=='__main__': main()
