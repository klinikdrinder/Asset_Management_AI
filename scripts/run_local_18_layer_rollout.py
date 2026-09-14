"""Resumable LOCAL production rollout for the prepared 848-asset cohort."""
from __future__ import annotations
import argparse, hashlib, json, os, sys, time, uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT/'scripts')]
FULL=ROOT/'reports/semantic-search/rollout/full';PREP=FULL/'local-preparation-checkpoint.json'
MANIFEST=FULL/'local-18-layer-production-manifest.json';CP=FULL/'local-18-layer-production-checkpoint.json'
MODEL_PATH=ROOT/'.kdi-models/SmolVLM2-500M-Video-Instruct'
PROCESSOR='kdi_local_18_layer_scene_analyzer_v4';RUN_NS=uuid.UUID('a916dfac-1818-4c74-865f-f981d780b37e')

def now():return datetime.now(timezone.utc).isoformat()
def save(path,payload):path.write_text(json.dumps(payload,indent=2,default=str)+'\n',encoding='utf-8')
def chunks(v,n=40):
    for i in range(0,len(v),n):yield v[i:i+n]
def fetch(db,table,cols,ids,key='asset_id'):
    out=[]
    for part in chunks(ids):out+=(db.table(table).select(cols).in_(key,part).execute().data or [])
    return out
def prepared():
    raw=json.loads(PREP.read_text(encoding='utf-8'))['assets']
    rows=[dict(v) for v in raw.values() if v.get('local_evidence_complete') is True]
    rows.sort(key=lambda x:(int(x.get('ordinal') or 10**9),x['asset_id']))
    if len(rows)!=848:raise RuntimeError(f'PREPARED_TARGET_NOT_848:{len(rows)}')
    return rows
def frozen_manifest(rows):
    ids=[x['asset_id'] for x in rows];digest=hashlib.sha256(('\n'.join(ids)+'\n').encode()).hexdigest()
    payload={'manifest_id':'kdi_local_18_layer_848_v1','processor_version':PROCESSOR,
             'created_at':now(),'asset_count':len(ids),'sha256':digest,'batch_size':100,
             'batches':[ids[i:i+100] for i in range(0,len(ids),100)],'assets':ids}
    if MANIFEST.exists():
        old=json.loads(MANIFEST.read_text());
        if old['sha256']!=digest or old['assets']!=ids:raise RuntimeError('FROZEN_MANIFEST_DRIFT')
        return old
    save(MANIFEST,payload);return payload
def canary_records(rows):
    image=next(x for x in rows if x['media_type']=='IMAGE')
    normal=next(x for x in rows if x['media_type']=='VIDEO' and len(x.get('scenes') or [])==1)
    multi=sorted((x for x in rows if x['media_type']=='VIDEO' and len(x.get('scenes') or [])>1),
                 key=lambda x:(len(x.get('scenes') or []),int(x.get('ordinal') or 10**9)))[0]
    return [image,normal,multi]
def image_path(r):
    if r['media_type']=='IMAGE':return FULL/'local-work'/r['asset_id']/r['filename']
    raise ValueError('not image')
def scene_obs(provider,r,scene):
    from PIL import Image
    frames=[x for x in r.get('keyframes',[]) if int(x['scene_index'])==int(scene['scene_index'])]
    if not frames:raise RuntimeError(f"NO_KEYFRAME_SCENE_{scene['scene_index']}")
    with Image.open(frames[0]['path']) as im:return provider.analyze(im.convert('RGB'))
def package(provider,r):
    from PIL import Image
    from local_18_layer_analyzer import assemble,synthesize_asset
    if r['media_type']=='IMAGE':
        p=image_path(r)
        if not p.is_file():raise RuntimeError('LOCAL_IMAGE_MISSING')
        with Image.open(p) as im:obs=provider.analyze(im.convert('RGB'))
        return assemble(r,obs),[]
    scenes=[]
    for s in r.get('scenes',[]):scenes.append(assemble(r,scene_obs(provider,r,s),scene_index=int(s['scene_index'])))
    return synthesize_asset(r,scenes),scenes
def evidence(r):
    from kdi_media.production_indexer import SceneEvidence,VideoEvidence
    by={}
    for f in r.get('keyframes',[]):by.setdefault(int(f['scene_index']),[]).append(f['path'])
    tb={}
    for c in r.get('transcript_chunks',[]):
        for s in r.get('scenes',[]):
            if float(s['start_seconds'])-1e-6<=float(c['start']) and float(c['end'])<=float(s['end_seconds'])+1e-6:
                tb.setdefault(int(s['scene_index']),[]).append(c['text']);break
    ob=r.get('ocr_texts_by_scene') or {}
    scenes=[SceneEvidence(int(s['scene_index']),float(s['start_seconds']),float(s['end_seconds']),
             by.get(int(s['scene_index']),[]),list(ob.get(str(s['scene_index']),[])),tb.get(int(s['scene_index']),[])) for s in r.get('scenes',[])]
    return VideoEvidence(r['asset_id'],r['filename'],r.get('technical_probe',{}),scenes,
        bool(r.get('audio_stream')),'AUDIO_PRESENT' if r.get('audio_stream') else 'NO_AUDIO',
        str(r.get('transcript_state')),bool(r.get('ocr_evaluated')),int(r.get('ocr_observations') or 0))
def upsert(db,table,rows,conflict='id'):
    if rows:db.table(table).upsert(rows,on_conflict=conflict).execute()
def persist(db,embed,r,semantic,locked):
    from kdi_media import canonical_rows as cr
    from kdi_media.supabase_production_adapter import CanonicalSemanticPersistenceAdapter,ManifestScope
    aid=r['asset_id'];run_id=str(uuid.uuid5(RUN_NS,f"{aid}:{r['checksum']}:{PROCESSOR}"))
    if aid in locked:raise RuntimeError('CERTIFIED_BASELINE_PROTECTED')
    run={'id':run_id,'asset_id':aid,'run_type':'PRODUCTION_SEMANTIC_INDEXING','status':'RUNNING',
      'semantic_spec_version':'kdi_semantic_18_layer_v1','ontology_version':'KDI_SEMANTIC_V2',
      'processor_version':PROCESSOR,'configuration_version':PROCESSOR,
      'configuration_fingerprint':hashlib.sha256(PROCESSOR.encode()).hexdigest(),'source_fingerprint':r['checksum'],
      'embedding_version':'kdi_embedding_bundle_v1','provider':'LOCAL_TRANSFORMERS',
      'model':'HuggingFaceTB/SmolVLM2-500M-Video-Instruct','model_version':'local-repository-v1',
      'started_at':now(),'metadata':{'local_only':True,'external_ai_calls':0,'ordinal':r.get('ordinal')}}
    upsert(db,'semantic_analysis_runs',[run])
    adapter=CanonicalSemanticPersistenceAdapter(db,ManifestScope(frozenset([aid]),frozenset()),text_embedder=embed)
    adapter.current_run_id=run_id
    ev=evidence(r) if r['media_type']=='VIDEO' else None
    rows=adapter.build_rows(aid,{'semantic':semantic,'evidence':ev,'metadata':{**r,'source_fingerprint':r['checksum']}})
    for vals in rows.values():
        for row in vals:
            if 'semantic_spec_version' in row:row['semantic_spec_version']='kdi_semantic_18_layer_v1'
            if 'source_semantic_version' in row:row['source_semantic_version']='kdi_semantic_18_layer_v1'
            if 'processor_version' in row:row['processor_version']=PROCESSOR
            if 'builder_version' in row:row['builder_version']=PROCESSOR
            if 'configuration_version' in row:row['configuration_version']=PROCESSOR
            if 'generator_version' in row:row['generator_version']=PROCESSOR
    for row in rows['search_document_builds']:
        row.pop('analysis_run_id',None)  # canonical table is fingerprint/version keyed
    # Deterministic evidence ids are required for idempotent reruns.
    for e in rows['semantic_assertion_evidence']:e['id']=cr.uid(f"{run_id}:evidence:{e['assertion_id']}:{e['evidence_type']}")
    # Three required asset narratives plus one per scene.
    base=semantic['narrative'] or 'No determinate content beyond canonical metadata was supported.'
    rows['semantic_narratives']=[]
    for typ,text in [('ASSET_NARRATIVE',base),('SHORT_SEMANTIC_SUMMARY',base[:500]),('SEARCH_SAFE_NARRATIVE',base)]:
        rows['semantic_narratives'].append({'id':cr.uid(f'{run_id}:narrative:{typ}'),'asset_id':aid,'narrative_type':typ,
          'text':text,'search_status':'ACCEPTED_FOR_SEARCH','input_evidence_fingerprint':cr.fingerprint(run_id,base),
          'generator_version':PROCESSOR,'configuration_version':PROCESSOR,'analysis_run_id':run_id,'human_review_status':'PENDING','active':False,'stale':False})
    for i,sp in enumerate(semantic.get('scene_packages',[])):
        sid=cr.unit_uid(aid,r['checksum'],'scene',i);txt=sp['narrative'] or f'Scene {i+1} has limited determinate visual evidence.'
        rows['semantic_narratives'].append({'id':cr.uid(f'{run_id}:scene:{i}:narrative'),'asset_id':aid,'scene_id':sid,'narrative_type':'SCENE_NARRATIVE','text':txt,
          'search_status':'ACCEPTED_FOR_SEARCH','input_evidence_fingerprint':cr.fingerprint(run_id,i,txt),'generator_version':PROCESSOR,
          'configuration_version':PROCESSOR,'analysis_run_id':run_id,'human_review_status':'PENDING','active':False,'stale':False})
    # Embed grounded transcript and OCR rows in their separate 384D family.
    tr=fetch(db,'asset_transcript_chunks','id,asset_id,scene_id,transcript_text,source_text_fingerprint',[aid])
    oc=fetch(db,'ocr_observations','id,asset_id,scene_id,raw_text,source_text_fingerprint',[aid])
    for x in tr:
        text='passage: '+str(x.get('transcript_text') or '');rows['semantic_embeddings'].append(cr.text_embedding_row(cr.uid(f"{run_id}:transcript:{x['id']}"),run_id,aid,embed(text),text,str(x.get('source_text_fingerprint') or r['checksum']),scope='TEXT_TRANSCRIPT',scene_id=x.get('scene_id'),source_unit_id=str(x['id'])))
        rows['semantic_embeddings'][-1]['transcript_chunk_id']=x['id']
    for x in oc:
        text='passage: '+str(x.get('raw_text') or '');rows['semantic_embeddings'].append(cr.text_embedding_row(cr.uid(f"{run_id}:ocr:{x['id']}"),run_id,aid,embed(text),text,str(x.get('source_text_fingerprint') or r['checksum']),scope='TEXT_OCR',scene_id=x.get('scene_id'),source_unit_id=str(x['id'])))
        rows['semantic_embeddings'][-1]['ocr_observation_id']=x['id']
    critical=[x['id'] for x in rows['semantic_assertions'] if x.get('search_critical')]
    for x in rows['semantic_assertions']:x['search_critical']=False
    conflicts={'asset_semantic_layers':'asset_id,layer_id,analysis_run_id','semantic_assertions':'idempotency_key'}
    for table in ('asset_scenes','asset_keyframes','asset_semantic_layers','semantic_assertions','semantic_assertion_evidence','semantic_narratives','search_document_builds','semantic_embeddings'):
        upsert(db,table,rows.get(table,[]),conflicts.get(table,'id'))
    for i in critical:db.table('semantic_assertions').update({'search_critical':True}).eq('id',i).execute()
    # Normalize document concepts/evidence into the existing canonical link tables.
    for doc in rows['search_document_builds']:
        scene_id=doc.get('scene_id');assertions=[x for x in rows['semantic_assertions'] if x.get('scene_id')==scene_id and x['semantic_state']=='OBSERVED']
        concepts=[];links=[]
        ev_by={x['assertion_id']:x for x in rows['semantic_assertion_evidence']}
        for a in assertions:
            cid=cr.uid(f"{doc['id']}:concept:{a['id']}");concepts.append({'id':cid,'document_id':doc['id'],'asset_id':aid,'scene_id':scene_id,'concept_type':a['canonical_concept_type'],'canonical_code':a['canonical_concept_code'],'display_text':a['value_text'],'semantic_state':'OBSERVED','confidence':a['confidence'],'origin':a['origin'],'resolution_source':'LOCAL_GROUNDED','review_status':'AI_UNREVIEWED','assertion_id':a['id'],'search_critical':a['search_critical']})
            e=ev_by.get(a['id']);links.append({'id':cr.uid(f"{doc['id']}:evidence:{a['id']}"),'document_id':doc['id'],'concept_id':cid,'assertion_id':a['id'],'assertion_evidence_id':e['id'] if e else None,'asset_id':aid,'scene_id':scene_id,'evidence_type':e['evidence_type'] if e else 'DATABASE_METADATA'})
        upsert(db,'search_document_concepts',concepts);upsert(db,'search_document_evidence',links)
    # Atomic publication: deactivate only target asset canonical semantic/search rows.
    for table in ('asset_semantic_layers','semantic_assertions','semantic_narratives','search_document_builds'):
        db.table(table).update({'active':False}).eq('asset_id',aid).eq('active',True).execute()
    db.table('semantic_embeddings').update({'active':False}).eq('asset_id',aid).like('representation_type','TEXT_%').eq('active',True).execute()
    for table in ('asset_semantic_layers','semantic_assertions'):
        db.table(table).update({'active':True}).eq('asset_id',aid).eq('analysis_run_id',run_id).execute()
    for table in ('semantic_narratives','semantic_embeddings'):
        db.table(table).update({'active':True,'stale':False}).eq('asset_id',aid).eq('analysis_run_id',run_id).execute()
    document_ids=[x['id'] for x in rows['search_document_builds']]
    if document_ids:db.table('search_document_builds').update({'active':True,'stale':False}).in_('id',document_ids).execute()
    # Reuse (never recompute) prepared OpenCLIP representations.
    db.table('semantic_embeddings').update({'active':True,'stale':False}).eq('asset_id',aid).like('representation_type','VISUAL_%').execute()
    if r['media_type']=='VIDEO':
        db.table('asset_scenes').update({'canonical_active':False}).eq('asset_id',aid).execute()
        db.table('asset_scenes').update({'canonical_active':True}).eq('asset_id',aid).eq('semantic_analysis_run_id',run_id).execute()
    db.table('semantic_analysis_runs').update({'status':'COMPLETED','completed_at':now(),'metadata':{**run['metadata'],'search_ready_candidate':True}}).eq('id',run_id).execute()
    ready=(db.table('kdi_search_ready_assets_v1').select('*').eq('asset_id',aid).single().execute().data)
    if not ready.get('search_ready'):raise RuntimeError(f'SEARCH_READY_GATE_FAILED:{ready}')
    return {'asset_id':aid,'analysis_run_id':run_id,'status':'SEARCH_READY','scene_count':len(r.get('scenes') or []),'layer_count':18}
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--canary',action='store_true');ap.add_argument('--bulk',action='store_true');ap.add_argument('--limit',type=int);args=ap.parse_args()
    load_dotenv(ROOT/'.env');load_dotenv(ROOT/'.env.local',override=False)
    from supabase import create_client
    from sentence_transformers import SentenceTransformer
    from local_vlm_contract_provider import LocalContractVisualProvider
    rows=prepared();manifest=frozen_manifest(rows);selected=canary_records(rows) if args.canary else rows
    db=create_client(os.environ['SUPABASE_URL'],os.environ['SUPABASE_SERVICE_ROLE_KEY'])
    active=db.table('asset_semantic_layers').select('asset_id').eq('active',True).execute().data or [];counts=Counter(x['asset_id'] for x in active);locked={a for a,n in counts.items() if n==18}
    overlap=locked&set(manifest['assets'])
    if overlap:raise RuntimeError(f'TARGET_OVERLAPS_CERTIFIED:{len(overlap)}')
    state=json.loads(CP.read_text()) if CP.exists() else {'status':'RUNNING','manifest_sha256':manifest['sha256'],'assets':{}}
    if state['manifest_sha256']!=manifest['sha256']:raise RuntimeError('CHECKPOINT_MANIFEST_DRIFT')
    done={a for a,x in state['assets'].items() if x.get('status')=='SEARCH_READY'};selected=[x for x in selected if x['asset_id'] not in done]
    if args.limit:selected=selected[:args.limit]
    snapshots=sorted((Path.home()/'.cache/huggingface/hub/models--intfloat--multilingual-e5-small/snapshots').glob('*'))
    if not snapshots:raise RuntimeError('LOCAL_E5_MODEL_MISSING')
    e5=SentenceTransformer(str(snapshots[-1]),local_files_only=True)
    embed=lambda text:[float(x) for x in e5.encode(text,normalize_embeddings=True)]
    vlm=LocalContractVisualProvider(str(MODEL_PATH));started=time.perf_counter()
    for idx,r in enumerate(selected,1):
        sem=None
        try:
            cached=state['assets'].get(r['asset_id'],{}).get('semantic_cache')
            sem=cached if cached else package(vlm,r)[0]
            state['assets'][r['asset_id']]={'asset_id':r['asset_id'],'ordinal':r.get('ordinal'),'filename':r['filename'],'status':'SEMANTIC_EVALUATED','semantic_cache':sem,'external_ai_calls':0}
            save(CP,state)
            out=persist(db,embed,r,sem,locked);out.update({'ordinal':r.get('ordinal'),'filename':r['filename'],'elapsed_seconds':round(time.perf_counter()-started,2),'external_ai_calls':0,'semantic_cache':sem})
        except Exception as exc:
            out={'asset_id':r['asset_id'],'ordinal':r.get('ordinal'),'filename':r['filename'],'status':'FAILED','error':f'{type(exc).__name__}: {exc}','external_ai_calls':0}
            if sem is not None:out['semantic_cache']=sem
        state['assets'][r['asset_id']]=out;state['updated_at']=now();save(CP,state);print(json.dumps(out),flush=True)
    state['status']='PASS' if len([x for x in state['assets'].values() if x.get('status')=='SEARCH_READY'])==848 else 'IN_PROGRESS';save(CP,state)
    print(json.dumps({'status':state['status'],'processed':len(state['assets']),'ready':sum(x.get('status')=='SEARCH_READY' for x in state['assets'].values()),'failed':sum(x.get('status')=='FAILED' for x in state['assets'].values()),'external_ai_calls':0}))
if __name__=='__main__':main()
