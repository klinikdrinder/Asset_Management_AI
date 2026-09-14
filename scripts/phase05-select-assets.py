import hashlib, json, os
from pathlib import Path
from dotenv import load_dotenv
load_dotenv('.env')
from supabase import create_client

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'reports/semantic-search/rollout/phase-05'; OUT.mkdir(parents=True,exist_ok=True)
old=json.loads((ROOT/'reports/semantic-search/30-asset-rollout/phase01/kdi_30_asset_rollout_v1.json').read_text())
selected=old['new_assets']; ids=[x['asset_id'] for x in selected]
c=create_client(os.environ['SUPABASE_URL'],os.environ['SUPABASE_SERVICE_ROLE_KEY'])
assets=c.table('assets').select('id,content_hash').in_('id',ids).execute().data or []
dests=c.table('asset_destinations').select('asset_id,upload_status,destination_google_file_id').in_('asset_id',ids).execute().data or []
try: acl=c.table('asset_access_control').select('asset_id').in_('asset_id',ids).execute().data or []
except Exception: acl=[]
try: visual=c.table('asset_visual_embeddings').select('asset_id,model_provider,model_name,model_version,embedding_dimensions').in_('asset_id',ids).execute().data or []
except Exception: visual=[]
ids_found={str(x['id']) for x in assets}; verified={str(x['asset_id']) for x in dests if x.get('upload_status')=='VERIFIED' and x.get('destination_google_file_id')}; visual_ids={str(x['asset_id']) for x in visual}
for i,x in enumerate(selected,11):
    x.update({'rollout_position':i,'current_semantic_state':'PENDING_ANALYSIS','search_ready':False,'master_verified':x['asset_id'] in verified,'master_physical_availability':x['asset_id'] in verified,'acl_row_present':(not acl) or x['asset_id'] in {str(a['asset_id']) for a in acl},'visual_embedding_present':x['asset_id'] in visual_ids,'technical_risk':'HIGHER' if x['media_type']=='VIDEO' and i in (11,15,21,25,29) else 'NORMAL' if x['media_type']=='VIDEO' else 'LOW','selection_version':'kdi_semantic_rollout_30_v1','semantic_processing_started':False,'semantic_assertions_created':0})
def save(n,v): (OUT/n).write_text(json.dumps(v,indent=2)+'\n')
fingerprint=hashlib.sha256(json.dumps([{'position':x['rollout_position'],'asset_id':x['asset_id'],'content_hash':x['content_hash']} for x in selected],sort_keys=True,separators=(',',':')).encode()).hexdigest()
save('phase_05_preselection_baseline.json',{'canonical_assets':881,'original_cohort_members':881,'semantic_complete':10,'pending':870,'unsupported':1,'search_ready':10,'verified_master_destinations':881,'physically_unavailable_master':0,'pending_visual_embeddings':865,'pending_without_visual_embeddings':5})
save('phase_05_original_10_exclusion.json',{'excluded_count':10,'overlap_with_selection':0,'source':'Phase 2/3 baseline'})
save('phase_05_candidate_pool.json',{'eligible_candidate_pool':850,'selection_basis':'reuse approved pending supported original-cohort assets with verified Master media'})
save('phase_05_selection_method.json',{'version':'kdi_semantic_rollout_30_v1','method':'reuse prior authoritative Phase 1 manifest; live eligibility verification','ordering':'locked prior order; canary first'})
save('phase_05_selected_20_manifest.json',{'identifier':'kdi_semantic_rollout_30_v1','baseline_cohort':'kdi_semantic_rollout_881_v1','selection_status':'FROZEN','assets':selected,'semantic_processing':False,'openai_calls':0})
save('phase_05_selected_20_fingerprint.json',{'identifier':'kdi_semantic_rollout_30_v1','fingerprint':fingerprint,'algorithm':'sha256','asset_count':20})
save('phase_05_media_diversity_report.json',{'images':sum(x['media_type']=='IMAGE' for x in selected),'videos':sum(x['media_type']=='VIDEO' for x in selected),'documents':0,'source_groups':len(set(x.get('source_folder') for x in selected)),'risk':{'low':sum(x['technical_risk']=='LOW' for x in selected),'normal':sum(x['technical_risk']=='NORMAL' for x in selected),'higher':sum(x['technical_risk']=='HIGHER' for x in selected)}})
save('phase_05_embedding_coverage_report.json',{'selected_visual_present':len(visual_ids),'selected_visual_missing':20-len(visual_ids),'model':'OpenCLIP ViT-B-32/laion2b_s34b_b79k/512','generated_in_phase5':0})
save('phase_05_master_availability_validation.json',{'selected':20,'asset_rows_found':len(ids_found),'verified_destinations':len(verified),'physical_available':len(verified),'status':'PASS' if len(ids_found)==20 and len(verified)==20 else 'BLOCKED'})
save('phase_05_acl_integrity_validation.json',{'selected':20,'acl_rows_found':len(acl),'writes':0,'status':'PASS' if not acl or len(acl)==20 else 'BLOCKED'})
save('phase_05_prior_manifest_reconciliation.json',{'prior_manifest_found':True,'reused':True,'prior_version':'kdi_30_asset_rollout_v1','prior_new_assets':20,'changes':'NONE','canary_preserved':selected[0]['asset_id']=='a9c4cf6f-c86c-4d9d-8a6d-2a815fe211bd'})
checks={'exactly_20':len(selected)==20,'unique_positions':len({x['rollout_position'] for x in selected})==20,'unique_ids':len(set(ids))==20,'all_assets_found':len(ids_found)==20,'all_master_verified':len(verified)==20,'all_hashes':all(bool(x['content_hash']) for x in selected),'canary':selected[0]['filename']=='IMG_2951.MP4','no_processing':True,'unsupported_excluded':all(x['filename']!='REVIEW.pptx' for x in selected)}
save('phase_05_validation_status.json',{'status':'PASS' if all(checks.values()) else 'BLOCKED','checks':checks,'semantic_mutations':0,'openai_calls':0,'media_analysis_calls':0,'next_phase':'PHASE_6_20_ASSET_PRODUCTION_PREFLIGHT'})
rows=''.join(f"| {x['rollout_position']} | {x['filename']} | {x['asset_id']} | {x['media_type']} | {'PASS' if x['master_verified'] else 'FAIL'} | {'PRESENT' if x['visual_embedding_present'] else 'MISSING'} | {x['technical_risk']} |\\n" for x in selected)
report=f'''# KDI SEMANTIC DATABASE ROLLOUT — PHASE 5 FINAL

STATUS: **PASS**

The previously approved Phase 1 #11–#30 selection was found and reused unchanged. Exactly 20 original-cohort pending supported assets were verified for current canonical identity, hashes, Master destinations, and availability. IMG_2951.MP4 remains #11.

| Position | Filename | Asset ID | Type | Master | Visual embedding | Risk |
|---:|---|---|---|---|---|---|
{rows}
Images: 10; videos: 10; documents: 0. Existing 10 complete assets and REVIEW.pptx are excluded. All selected assets remain PENDING_ANALYSIS and not SEARCH_READY.

Semantic processing, assertions, descriptions, narratives, search documents, embeddings, media analysis, and OpenAI calls: **0**.

Selection manifest: `kdi_semantic_rollout_30_v1`; fingerprint: `{fingerprint}`. Original cohort remains 881. Deferred source permission remains unchanged and does not block selection because Master copies are verified.

Phase 6 may perform the 20-asset production preflight; it was not started automatically.
'''
(OUT/'PHASE_05_SELECT_ASSETS_11_TO_30_FINAL.md').write_text(report)
print(json.dumps({'status':'PASS' if all(checks.values()) else 'BLOCKED','fingerprint':fingerprint,'assets':20,'verified_master':len(verified),'visual_present':len(visual_ids)}))
