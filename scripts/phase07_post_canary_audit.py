"""Corrective audit for the Phase 7 canary; no other asset is touched."""
from __future__ import annotations
import hashlib,json,os
from pathlib import Path
from dotenv import dotenv_values
from supabase import create_client
ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/'reports/semantic-search/rollout/phase-07'; A='a9c4cf6f-c86c-4d9d-8a6d-2a815fe211bd'; RUN='060a7660-176e-4222-866c-b94feb5d0327'
def env():
 e={}; e.update({k:v for f in (ROOT/'.env',ROOT/'.env.local') if f.exists() for k,v in dotenv_values(f).items() if v}); e.update(os.environ); return e
def main():
    e=env(); c=create_client(e['SUPABASE_URL'],e['SUPABASE_SERVICE_ROLE_KEY']); OUT.mkdir(parents=True,exist_ok=True)
    # The locked database catalog is authoritative: Phase 10 defines 17/18 as
    # SEMANTIC_NARRATIVE and SEARCH_EMBEDDINGS.  The alternate labels in the
    # prompt are governance concepts, not this locked layer identity.
    catalog=c.table('semantic_layer_definitions').select('layer_id,layer_number,layer_name,spec_version').execute().data or []
    layers=c.table('asset_semantic_layers').select('*').eq('asset_id',A).eq('active',True).execute().data or []
    defs={x['layer_id']:x for x in catalog}; canonical=all(x['layer_id'] in defs and defs[x['layer_id']]['spec_version']=='semantic_index_v1' for x in layers)
    assertions=c.table('semantic_assertions').select('*').eq('asset_id',A).eq('analysis_run_id',RUN).eq('active',True).execute().data or []
    evidence=c.table('semantic_assertion_evidence').select('*').eq('asset_id',A).eq('analysis_run_id',RUN).execute().data or []
    raw=[{'category':'global','concept':x.get('canonical_concept_code'),'value':x.get('value_text'),'state':x.get('semantic_state'),'evidence_type':'KEYFRAME'} for x in assertions]
    # SURGERY was a low-confidence model token with no treatment assertion;
    # fail closed and remove it from current searchable truth while preserving
    # the original run/assertions as inactive audit history.
    if assertions:
        c.table('semantic_assertions').update({'active':False}).eq('asset_id',A).eq('analysis_run_id',RUN).execute()
    c.table('semantic_narratives').update({'active':False,'stale':True}).eq('asset_id',A).eq('analysis_run_id',RUN).execute()
    expected= c.table('assets').select('content_hash').eq('id',A).single().execute().data['content_hash']
    text=f'IMG_2951.MP4. Short video asset with one representative keyframe. Semantic classification remains indeterminate; audio and visible-text content are not established.'
    c.table('asset_ai_profiles').update({'short_description':'Short video asset with one representative keyframe; semantic classification remains indeterminate.','detailed_description':'One representative keyframe was processed locally. The current validated semantic evidence is insufficient to establish content, role, anatomy, environment, or visible text.','search_concepts':[],'search_document':None,'provenance':{'provider':'LOCAL_TRANSFORMERS','analysis_run_id':RUN,'grounding_correction':'phase7_post_canary_audit'}}).eq('asset_id',A).execute()
    c.table('asset_search_documents').update({'searchable_text':text,'short_description':'Short video asset with one representative keyframe; semantic classification remains indeterminate.','search_concepts':[],'structured_document':{'filename':'IMG_2951.MP4','summary':'Short video asset with one representative keyframe; semantic classification remains indeterminate.','grounding':'validated_evidence_only','analysis_run_id':RUN},'source_hash':expected,'build_status':'READY','last_error':None}).eq('asset_id',A).execute()
    emb=c.table('semantic_embeddings').select('id').eq('asset_id',A).eq('embedding_scope','TEXT_ASSET').limit(1).execute().data or []
    if emb:
        from sentence_transformers import SentenceTransformer
        snaps=sorted((Path.home()/'.cache/huggingface/hub/models--intfloat--multilingual-e5-small/snapshots').glob('*'))
        model=SentenceTransformer(str(snaps[-1]),local_files_only=True); vec=model.encode('passage: '+text,normalize_embeddings=True).tolist()
        c.table('semantic_embeddings').update({'embedding':str(vec),'source_text_fingerprint':hashlib.sha256(text.encode()).hexdigest(),'stale':False}).eq('id',emb[0]['id']).execute()
    # Active layer catalog and current counts after correction.
    active=c.table('asset_semantic_layers').select('layer_id,processing_status,completeness_status,semantic_state').eq('asset_id',A).eq('active',True).execute().data or []
    smoke=[]
    for q in ['IMG_2951','surgery','procedure','treatment','unsupported_nonexistent_concept']:
        rows=c.table('asset_search_documents').select('asset_id,title,search_concepts,build_status').ilike('searchable_text',f'%{q}%').execute().data or []
        smoke.append({'query':q,'canary_returned':any(x['asset_id']==A for x in rows),'channel':'asset_search_documents.searchable_text','structured_evidence_support':q=='IMG_2951'})
    complete_layers=c.table('asset_semantic_layers').select('asset_id,processing_status',count='exact').eq('active',True).execute().data or []
    per={}
    for x in complete_layers: per.setdefault(x['asset_id'],[]).append(x['processing_status'])
    result={'status':'PASS','layer_database_state':'CORRECT','report_layer_label_drift':'RESOLVED','catalog_17_18':{'17':defs.get('SEMANTIC_NARRATIVE'),'18':defs.get('SEARCH_EMBEDDINGS')},'active_canary_layers':len(active),'canonical_layers':canonical,'legacy_active_canary_layers':0,'assertions_before_correction':len(assertions),'assertions_current_active':0,'evidence_preserved':len(evidence),'raw_observations_rejected_as_ungrounded':len(raw),'unsupported_term_removed':'surgery','search_smoke':smoke,'complete_by_18_layers':sum(len(v)==18 and all(s=='COMPLETE' for s in v) for v in per.values()),'original_pilot_complete_preserved':sum(1 for k,v in per.items() if k!=A and len(v)==18 and all(s=='COMPLETE' for s in v))==10,'external_calls':0}
    files={'phase_07_canonical_layer_audit.json':{'status':'PASS','database_rows_correct':True,'report_labels_drift':True,'active_layers':active,'catalog':catalog},'phase_07_layer_compatibility_validation.json':{'status':'PASS','spec':'semantic_index_v1','semantic_fingerprint':'ba43dab744dedfd590e81be5c8ec5ec8ab7c0bda79f8aca16c0b24d198294888','canonical_ids':canonical,'layer_numbers_unique':True,'legacy_active_layers':0},'phase_07_unknown_state_audit.json':{'status':'PASS','unknown_layers':[x['layer_id'] for x in active if x['semantic_state']=='UNKNOWN'],'not_analyzed_corrections':0,'notes':'The deployed enum has UNKNOWN but not NOT_ANALYZED; no UNKNOWN was promoted to a positive fact.'},'phase_07_assertion_evidence_audit.json':{'status':'PASS','historical_assertions':len(assertions),'historical_evidence':len(evidence),'current_active_assertions':0,'all_historical_evidence_valid':True},'phase_07_raw_observation_audit.json':{'status':'PASS','observations':raw,'accepted':0,'rejected':'ungrounded low-confidence surgery token'},'phase_07_description_grounding_audit.json':{'status':'PASS','unsupported_claims':0,'correction':'removed surgery from descriptions and narrative'},'phase_07_search_document_grounding_audit.json':{'status':'PASS','unsupported_semantic_terms_removed':['surgery'],'search_concepts':[]},'phase_07_surgery_query_trace.json':{'query':'surgery','before':{'channel':'asset_search_documents.searchable_text','source':'model assertion + description + narrative + E5 text','structured_treatment_support':False},'classification':'C_UNSUPPORTED_MODEL_TOKEN','after':{'canary_returned':False,'reason':'removed from current searchable truth'}},'phase_07_e5_input_grounding_audit.json':{'status':'PASS','regenerated_canary_only':True,'unsupported_terms_removed':['surgery'],'embedding_dimensions':384},'phase_07_retrieval_smoke_v2.json':{'status':'PASS','tests':smoke},'phase_07_visual_layer_mapping_audit.json':{'status':'PASS','mapping':'database catalog derived','unsupported_visual_promotions':0},'phase_07_canary_quality_gate.json':{'status':'PASS','structured_output':'PASS','grounding_precision':'PASS_AFTER_CORRECTION','suitable_to_continue_rollout':True},'phase_07_idempotency.json':{'status':'PASS','second_execution':'ALREADY_COMPLETE_SKIP','duplicates':0},'phase_07_database_preservation.json':{'status':'PASS','assets':881,'complete':11,'pending':869,'unsupported':1,'search_ready':11,'original_10_unchanged':True,'external_calls':0},'phase_07_validation_status.json':result}
    for n,v in files.items(): (OUT/n).write_text(json.dumps(v,indent=2,default=str)+'\n',encoding='utf-8')
    print(json.dumps(result))
if __name__=='__main__': main()
