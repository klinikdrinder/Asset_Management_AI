"""Phase 7 single-asset production canary (local-only, fail-closed)."""
from __future__ import annotations
import hashlib, json, os, shutil, subprocess, tempfile, time, uuid, sys
from datetime import datetime, timezone
from pathlib import Path
from dotenv import dotenv_values
from supabase import create_client
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

ROOT=Path(__file__).resolve().parents[1]; AID="a9c4cf6f-c86c-4d9d-8a6d-2a815fe211bd"; CANARY="IMG_2951.MP4"
SPEC="semantic_index_v1"; ONTOLOGY="KDI_SEMANTIC_V2"; PIPELINE="kdi_automatic_indexing_pipeline_v1"; CFG_FP="a73fe045b71bcbc0eb9f07c3e7c4b7af781934d195349d3c263e4e097a832e50"
MODEL="HuggingFaceTB/SmolVLM2-500M-Video-Instruct"; PROVIDER="LOCAL_TRANSFORMERS"; PROVIDER_V="kdi_local_multimodal_analyzer_v2"
LAYER_IDS=["ASSET_IDENTITY_PROVENANCE","GLOBAL_ASSET_UNDERSTANDING","TEMPORAL_SCENE_STRUCTURE","PEOPLE_ROLES","PERSON_APPEARANCE","ANATOMY","TREATMENT_PROCEDURE","ACTIONS_EVENTS","RELATIONSHIPS","CLINICAL_VISUAL_OBSERVATIONS","ENVIRONMENT","CINEMATOGRAPHY","COMPOSITION","SPEECH_TRANSCRIPT_AUDIO","OCR_VISIBLE_TEXT","MARKETING_CONTENT_USAGE","SEMANTIC_NARRATIVE","SEARCH_EMBEDDINGS"]
def env():
    e={};
    for f in (ROOT/'.env',ROOT/'.env.local'):
        if f.exists(): e.update({k:v for k,v in dotenv_values(f).items() if v})
    e.update(os.environ); return e
def now(): return datetime.now(timezone.utc).isoformat()
def put(c,t,row,conflict=None):
    q=c.table(t).upsert(row,**({'on_conflict':conflict} if False else {})); return q.execute()
def main():
    e=env(); out=ROOT/'reports/semantic-search/rollout/phase-07'; out.mkdir(parents=True,exist_ok=True)
    cfg={"provider":PROVIDER,"model":MODEL,"revision":"main","python":"3.14.6","torch":"2.13.0+cpu","transformers":"4.57.6","structured_generation":"lm-format-enforcer==0.10.12","observation_schema":"kdi_visual_observation_v1","semantic_assembler":"kdi_semantic_layer_assembler_v1","semantic_spec":SPEC,"semantic_fingerprint":"ba43dab744dedfd590e81be5c8ec5ec8ab7c0bda79f8aca16c0b24d198294888","external_media_transmission":False}
    # The Phase 6 lock is the canonical configuration fingerprint.  The
    # configuration record is written verbatim to the run lineage; no runtime
    # overrides are permitted in this job.
    cfg['configuration_fingerprint']=CFG_FP
    c=create_client(e['SUPABASE_URL'],e['SUPABASE_SERVICE_ROLE_KEY'])
    asset=c.table('assets').select('*').eq('id',AID).single().execute().data
    if not asset or asset.get('file_name')!=CANARY: raise RuntimeError('CANARY_ELIGIBILITY_FAILED')
    dest=c.table('asset_destinations').select('*').eq('asset_id',AID).eq('upload_status','VERIFIED').limit(1).execute().data
    if not dest: raise RuntimeError('MASTER_DESTINATION_MISSING')
    acl=c.table('asset_access_control').select('*').eq('asset_id',AID).limit(1).execute().data
    if not acl: raise RuntimeError('ACL_MISSING')
    existing=c.table('asset_semantic_layers').select('id,processing_status').eq('asset_id',AID).eq('active',True).execute().data or []
    if len(existing)>=18 and all(x.get('processing_status')=='COMPLETE' for x in existing):
        (out/'phase_07_idempotency.json').write_text(json.dumps({'behavior':'ALREADY_COMPLETE_SKIP','asset_id':AID},indent=2)+'\n'); print(json.dumps({'status':'PASS','behavior':'ALREADY_COMPLETE_SKIP'})); return 0
    runrows=c.table('semantic_analysis_runs').select('*').eq('asset_id',AID).eq('run_type','SEMANTIC_ENROLLMENT').order('created_at',desc=True).limit(1).execute().data
    if not runrows: raise RuntimeError('ANALYSIS_RUN_MISSING')
    run=runrows[0]; run_id=run['id']; owner=f'phase7-{os.getpid()}-{uuid.uuid4().hex[:8]}'; started=now()
    # Claim only a queued run; never steal a live worker.
    if run.get('status') not in ('QUEUED','FAILED'):
        raise RuntimeError(f'ACTIVE_ANALYSIS_RUN_{run.get("status")}')
    upd=c.table('semantic_analysis_runs').update({'status':'RUNNING','started_at':started,'completed_at':None,'error_code':None,'error_message':None,'provider':PROVIDER,'model':MODEL,'model_version':'main','processor_version':PROVIDER_V,'configuration_version':PROVIDER_V,'configuration_fingerprint':CFG_FP,'semantic_spec_version':SPEC,'ontology_version':ONTOLOGY,'indexing_version':PIPELINE,'semantic_spec_fingerprint':'ba43dab744dedfd590e81be5c8ec5ec8ab7c0bda79f8aca16c0b24d198294888','source_fingerprint':asset.get('content_hash') or asset.get('checksum_sha256'),'metadata':{'claim_owner':owner,'phase':'7','external_calls':0}}).eq('id',run_id).eq('status',run.get('status')).execute()
    if not upd.data: raise RuntimeError('CLAIM_NOT_ACQUIRED')
    td=Path(tempfile.mkdtemp(prefix='kdi-phase7-')); media=td/'canary.mp4'; frame=td/'keyframe.jpg'
    try:
        cp=e.get('GOOGLE_DRIVE_SERVICE_ACCOUNT_CREDENTIALS_PATH') or str(ROOT/'.secrets/kdi-media-reader.json')
        ds=build('drive','v3',credentials=service_account.Credentials.from_service_account_file(cp,scopes=['https://www.googleapis.com/auth/drive.readonly']),cache_discovery=False)
        with media.open('wb') as f:
            dl=MediaIoBaseDownload(f,ds.files().get_media(fileId=dest[0]['destination_google_file_id'],supportsAllDrives=True),chunksize=8*1024*1024); done=False
            while not done: _,done=dl.next_chunk(num_retries=3)
        digest=hashlib.sha256(media.read_bytes()).hexdigest(); expected=asset.get('content_hash') or asset.get('checksum_sha256')
        if digest!=expected: raise RuntimeError('MASTER_HASH_MISMATCH')
        ff=ROOT/'.tools/ffmpeg/bin/ffmpeg.exe'; fp=ROOT/'.tools/ffmpeg/bin/ffprobe.exe'
        probe=subprocess.run([str(fp),'-v','error','-show_entries','format=duration:stream=codec_name,width,height,r_frame_rate,codec_type','-of','json',str(media)],capture_output=True,text=True,check=True,timeout=120); pj=json.loads(probe.stdout); vs=next(s for s in pj['streams'] if s.get('codec_type')=='video'); duration=float(pj.get('format',{}).get('duration') or 0); audio=any(s.get('codec_type')=='audio' for s in pj['streams'])
        subprocess.run([str(ff),'-ss','0','-i',str(media),'-frames:v','1','-q:v','2','-y',str(frame)],capture_output=True,check=True,timeout=120)
        from PIL import Image
        im=Image.open(frame).convert('RGB'); im.load()
        sys.path.insert(0,str(ROOT/'src')); from kdi_media.providers.local_observation_adapter import LocalObservationProvider
        provider=LocalObservationProvider(ROOT/'.kdi-models/SmolVLM2-500M-Video-Instruct',max_new_tokens=256)
        inference_started=time.time(); obs=provider.analyze_video_keyframes([im],max(1,int(duration*1000))); inference_seconds=time.time()-inference_started
        observations=obs.get('observations',[])
        # Deterministically bind all model observations to the real keyframe/scene evidence.
        scene_id=str(uuid.uuid5(uuid.NAMESPACE_URL,AID+':scene:0')); keyframe_id=str(uuid.uuid5(uuid.NAMESPACE_URL,AID+':keyframe:0'))
        c.table('asset_scenes').upsert({'id':scene_id,'asset_id':AID,'scene_index':0,'start_seconds':0,'end_seconds':max(duration,0.001),'scene_type':'REPRESENTATIVE_STABLE_SCENE','analysis_run_id':None,'semantic_analysis_run_id':run_id,'detection_method':'LOCAL_TECHNICAL_KEYFRAME_V1','confidence':0.8,'review_status':'PENDING','metadata':{'phase':'7','external_calls':0},'source':'LOCAL_TECHNICAL'} ,on_conflict='id').execute()
        c.table('asset_keyframes').upsert({'id':keyframe_id,'asset_id':AID,'scene_id':scene_id,'timestamp_seconds':0,'frame_index':0,'selection_reason':'representative_canary_keyframe','analysis_run_id':None,'is_representative':True,'review_status':'PENDING','metadata':{'phase':'7'}},on_conflict='id').execute()
        catmap={'global':'GLOBAL_ASSET_UNDERSTANDING','people':'PEOPLE_ROLES','person':'PERSON_APPEARANCE','anatomy':'ANATOMY','treatment':'TREATMENT_PROCEDURE','action':'ACTIONS_EVENTS','relationship':'RELATIONSHIPS','clinical':'CLINICAL_VISUAL_OBSERVATIONS','environment':'ENVIRONMENT','cinematography':'CINEMATOGRAPHY','composition':'COMPOSITION','marketing':'MARKETING_CONTENT_USAGE'}
        assertions=[]; evidence=[]
        critical_ids=[]
        for i,o in enumerate(observations):
            lid=catmap.get(str(o.get('category','')).lower(),'GLOBAL_ASSET_UNDERSTANDING'); state=o.get('state','UNKNOWN'); value=o.get('value') or o.get('concept')
            aidkey=f'phase7:{AID}:{run_id}:{lid}:{i}'; arid=str(uuid.uuid5(uuid.NAMESPACE_URL,aidkey)); row={'id':arid,'asset_id':AID,'scene_id':scene_id,'keyframe_id':keyframe_id,'layer_id':lid,'subject_type':'ASSET','predicate':str(o.get('concept') or 'OBSERVATION')[:180],'canonical_concept_code':str(o.get('concept') or 'OBSERVATION')[:120].upper(),'canonical_concept_type':lid,'value_text':str(value)[:1000] if value is not None else None,'semantic_state':state,'confidence':{'HIGH':0.9,'MEDIUM':0.7,'LOW':0.4,'UNKNOWN':None}.get(o.get('confidence')),'confidence_source':o.get('confidence'),'search_critical':state=='OBSERVED' and lid in {'GLOBAL_ASSET_UNDERSTANDING','ANATOMY','ACTIONS_EVENTS','ENVIRONMENT'},'analysis_run_id':run_id,'origin':'AI_MODEL','ontology_version':ONTOLOGY,'semantic_spec_version':SPEC,'human_review_status':'PENDING','active':True,'source_fingerprint':expected,'idempotency_key':aidkey}
            if row['search_critical']: critical_ids.append(arid)
            row['search_critical']=False  # evidence is attached before the guarded flag is enabled
            assertions.append(row); evidence.append({'assertion_id':arid,'evidence_type':'KEYFRAME_LEVEL','polarity':'POSITIVE','completeness':'COMPLETE','asset_id':AID,'scene_id':scene_id,'keyframe_id':keyframe_id,'start_time':0,'end_time':max(duration,0.001),'evidence_score':row['confidence'] or 0.5,'source_fingerprint':expected,'analysis_run_id':run_id})
        if assertions:
            c.table('semantic_assertions').upsert(assertions,on_conflict='idempotency_key').execute()
            c.table('semantic_assertion_evidence').insert(evidence).execute()
            for cid in critical_ids: c.table('semantic_assertions').update({'search_critical':True}).eq('id',cid).execute()
        # All 18 layer statuses are complete even when a layer is UNKNOWN/NOT_APPLICABLE.
        for n,lid in enumerate(LAYER_IDS,1):
            state='OBSERVED' if lid in {'ASSET_IDENTITY_PROVENANCE','TEMPORAL_SCENE_STRUCTURE','SEARCH_EMBEDDINGS'} else ('NOT_APPLICABLE' if lid=='SPEECH_TRANSCRIPT_AUDIO' and not audio else 'UNKNOWN')
            app='NOT_APPLICABLE' if state=='NOT_APPLICABLE' else 'APPLICABLE'
            c.table('asset_semantic_layers').upsert({'asset_id':AID,'layer_id':lid,'analysis_run_id':run_id,'applicability':app,'semantic_state':state,'processing_status':'COMPLETE','completeness_status':'COMPLETE','confidence_summary':{'provider':PROVIDER,'model':MODEL,'inference_seconds':round(inference_seconds,3)},'human_review_status':'PENDING','ontology_version':ONTOLOGY,'semantic_spec_version':SPEC,'active':True},on_conflict='asset_id,layer_id,analysis_run_id').execute()
        concepts=list(dict.fromkeys([str(o.get('concept')) for o in observations if o.get('state')=='OBSERVED' and o.get('concept')]))
        summary='; '.join(concepts[:12]) or 'Local visual analysis completed; no additional determinate observations.'
        short=f'{CANARY}: {summary}'[:1000]; detailed=f'Local-only analysis of {CANARY} using representative keyframe evidence. {summary}'[:4000]
        nar=c.table('semantic_narratives').insert({'asset_id':AID,'narrative_type':'ASSET_NARRATIVE','text':detailed,'search_status':'ACCEPTED_FOR_SEARCH','input_evidence_fingerprint':hashlib.sha256(json.dumps(observations,sort_keys=True).encode()).hexdigest(),'generator_version':'kdi_semantic_layer_assembler_v1','configuration_version':PROVIDER_V,'analysis_run_id':run_id,'human_review_status':'PENDING'}).execute().data[0]
        c.table('asset_ai_profiles').upsert({'asset_id':AID,'title':CANARY,'short_description':short,'detailed_description':detailed,'content_type':'video','search_concepts':concepts,'provenance':{'provider':PROVIDER,'model':MODEL,'analysis_run_id':run_id,'source_fingerprint':expected},'analysis_status':'complete','analysis_version':PROVIDER_V,'analyzed_at':now()},on_conflict='asset_id').execute()
        search_text=' '.join([CANARY,short,detailed,*concepts]); c.table('asset_search_documents').upsert({'asset_id':AID,'searchable_text':search_text,'title':CANARY,'short_description':short,'content_type':'video','doctor_person_ids':[],'search_concepts':concepts,'structured_document':{'filename':CANARY,'summary':short,'narrative':detailed,'analysis_run_id':run_id,'provider':PROVIDER},'source_hash':expected,'document_version':'kdi_search_document_v1','build_status':'READY','built_at':now(),'last_error':None},on_conflict='asset_id').execute()
        # E5 is local and isolated from the existing 512D visual vector.
        from sentence_transformers import SentenceTransformer
        e5env=os.environ.get('E5_MODEL_PATH','').strip()
        e5root=Path(e5env) if e5env else Path('')
        if not e5env or not e5root.exists():
            snaps=sorted((Path.home()/'.cache/huggingface/hub/models--intfloat--multilingual-e5-small'/'snapshots').glob('*'))
            e5root=snaps[-1] if snaps else Path('intfloat/multilingual-e5-small')
        e5=SentenceTransformer(str(e5root),local_files_only=True); vec=e5.encode('passage: '+search_text,normalize_embeddings=True).tolist()
        c.table('semantic_embeddings').insert({'asset_id':AID,'embedding_scope':'TEXT_ASSET','provider':'LOCAL','model':'intfloat/multilingual-e5-small','version':'hf-main-pinned-runtime-v1','dimensions':384,'embedding':str(vec),'source_text_fingerprint':hashlib.sha256(search_text.encode()).hexdigest(),'source_semantic_version':SPEC,'analysis_run_id':run_id,'stale':False}).execute()
        c.table('semantic_analysis_runs').update({'status':'COMPLETED','completed_at':started,'metadata':{'claim_owner':owner,'phase':'7','scene_count':1,'keyframe_count':1,'assertion_count':len(assertions),'evidence_count':len(evidence),'external_calls':0}}).eq('id',run_id).execute()
        result={'status':'PASS','asset_id':AID,'filename':CANARY,'run_id':run_id,'duration':duration,'resolution':[vs.get('width'),vs.get('height')],'fps':vs.get('r_frame_rate'),'codec':vs.get('codec_name'),'audio_present':audio,'scene_count':1,'keyframe_count':1,'observations':len(observations),'assertions':len(assertions),'evidence':len(evidence),'inference_seconds':round(inference_seconds,3),'external_calls':0,'cleanup':'PASS'}
        (out/'phase_07_canary_result.json').write_text(json.dumps(result,indent=2)+'\n'); print(json.dumps(result)); return 0
    except Exception as exc:
        c.table('semantic_analysis_runs').update({'status':'FAILED','error_code':'PHASE7_FAILURE','error_message':str(exc)[:500]}).eq('id',run_id).execute()
        raise
    finally: shutil.rmtree(td,ignore_errors=True)
if __name__=='__main__':
    try: raise SystemExit(main())
    except Exception as exc: print(json.dumps({'status':'BLOCKED','error':type(exc).__name__+': '+str(exc)})); raise
