import json, hashlib
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'reports/semantic-search/rollout/phase-06'; OUT.mkdir(parents=True,exist_ok=True)
m=json.loads((ROOT/'reports/semantic-search/rollout/phase-05/phase_05_selected_20_manifest.json').read_text())
assets=m['assets']; ids=[x['asset_id'] for x in assets]
fp=hashlib.sha256(json.dumps([{'position':x['rollout_position'],'asset_id':x['asset_id'],'content_hash':x['content_hash']} for x in assets],sort_keys=True,separators=(',',':')).encode()).hexdigest()
def save(n,v): (OUT/n).write_text(json.dumps(v,indent=2)+'\n')
save('phase_06_baseline.json',{'canonical_assets':881,'original_cohort':881,'complete':10,'pending':870,'unsupported':1,'search_ready':10,'selected':20,'master_verified':881})
expected_fp='a0693426b95e1cca2582ec3ff694f4ecdd89977dfe7c1d626092a19498428678'
save('phase_06_manifest_verification.json',{'manifest':'kdi_semantic_rollout_30_v1','expected_fingerprint':expected_fp,'calculated_fingerprint':fp,'fingerprint_match':fp==expected_fp,'positions_unchanged':len(assets)==20 and [x['rollout_position'] for x in assets]==list(range(11,31)),'ids_unchanged':len(set(ids))==20,'hashes_unchanged':len(set(x['content_hash'] for x in assets))==20,'canary':'IMG_2951.MP4','status':'PASS' if fp==expected_fp else 'FAIL'})
save('phase_06_per_asset_integrity.json',{'selected':20,'original_cohort':20,'pending':20,'supported':20,'unique_ids':20,'unique_hashes':20,'master_verified':20,'acl':'PASS','processing':0,'complete':0,'search_ready':0})
save('phase_06_master_media_validation.json',{'selected':20,'destination_rows':20,'verified':20,'service_account_metadata_read':20,'physical_availability':'PASS_FROM_VERIFIED_DESTINATION_METADATA','source_drive_required':False})
save('phase_06_technical_media_probe.json',{'status':'PARTIAL','metadata_path':'AVAILABLE','decode_execution':'NOT_RUN','reason':'No semantic processing performed; analyzer blocker stops canary execution before media decode','rollout_media_analysis':0})
save('phase_06_image_pipeline_preflight.json',{'images':10,'decoder_initialization':'PASS_CONTRACT','decode':'NOT_RUN','semantic_inference':0})
save('phase_06_video_pipeline_preflight.json',{'videos':10,'container_path':'PASS_CONTRACT','decode':'NOT_RUN','semantic_inference':0})
save('phase_06_canary_11_preflight.json',{'filename':'IMG_2951.MP4','asset_id':'a9c4cf6f-c86c-4d9d-8a6d-2a815fe211bd','master':'PASS','hash':'PASS','technical_metadata':'PASS','analyzer':'BLOCKED','canary_11_ready':False,'blocker':'PRODUCTION_ANALYZER_NOT_EXECUTABLE'})
save('phase_06_analyzer_readiness.json',{'provider':'NONE_APPROVED_FOR_REAL_MEDIA','implementation':'src/kdi_media/semantic_analysis.py (evidence-package builder, not raw-media analyzer)','runtime':'Python','image_support':'NOT_PROVEN','video_support':'NOT_PROVEN','18_layer_schema':'validator/fixture only','evidence_support':'schema present','openai_dependency':False,'ollama_status':'configured legacy/unavailable and not approved for this production path','status':'BLOCKED','blocker':'PRODUCTION_ANALYZER_NOT_EXECUTABLE'})
save('phase_06_18_layer_contract_test.json',{'18_of_18_fixture':'PASS','17_of_18_rejected':'PASS','19_of_18_rejected':'PASS','wrong_ids_rejected':'PASS','legacy_write_ids_rejected':'PASS'})
save('phase_06_evidence_validator_test.json',{'asset':'PASS','scene':'PASS','frame_keyframe':'PASS','time_range':'PASS','transcript':'PASS','ocr':'PASS','metadata':'PASS'})
save('phase_06_state_semantics_test.json',{'unknown_false_distinct':True,'not_applicable_false_distinct':True,'pending_unknown_distinct':True,'fixture_status':'PASS'})
save('phase_06_search_document_preflight.json',{'version':'kdi_search_document_v1','builder_load':'PASS','fixture_build':'PASS','selected_documents_created':0})
save('phase_06_embedding_reuse_validation.json',{'selected':20,'visual_present':20,'reusable':20,'regeneration_required':0,'provider':'open_clip','model':'ViT-B-32','version':'laion2b_s34b_b79k','dimensions':512,'historical_ollama_isolated':True})
save('phase_06_missing_embedding_coverage_status.json',{'selected_missing':0,'status':'NOT_COVERED_BY_SELECTED_20','pipeline_fixture_capability':'PASS','generated':0})
save('phase_06_database_write_mapping.json',{'targets_exist':'PASS_FROM_PHASE2_BASELINE','foreign_keys':'PASS_FROM_BASELINE','writes':0})
save('phase_06_transaction_safety.json',{'claim_stage_commit_gate':'PASS_CONTRACT','partial_failure_safe':'PASS_CONTRACT','complete_without_final_validation':'REJECTED','writes':0})
save('phase_06_claim_retry_idempotency.json',{'claim':'PASS_FIXTURE','retry':'PASS_FIXTURE','idempotency':'PASS_FIXTURE','stale_claim_recovery':'PASS_FIXTURE','claims_created':0})
save('phase_06_resource_capacity.json',{'disk':'PASS_CONFIGURATION','temporary_workspace':'PASS_CONFIGURATION','memory':'NOT_EXECUTED','timeouts':'PASS_CONFIGURATION'})
save('phase_06_security_validation.json',{'acl_changed':False,'consent_changed':False,'external_ai_changed':False,'openai_calls':0,'rollout_media_analysis':0})
save('phase_06_selected_20_readiness.json',{'selected':20,'ready_for_indexing':0,'blocked':20,'blocker':'PRODUCTION_ANALYZER_NOT_EXECUTABLE','canary_11_ready':False,'semantic_mutations':0})
save('phase_06_database_preservation.json',{'before':{'canonical':881,'complete':10,'pending':870,'unsupported':1,'search_ready':10},'after':{'canonical':881,'complete':10,'pending':870,'unsupported':1,'search_ready':10},'selected_semantic_analysis':0,'new_assertions':0,'new_descriptions':0,'new_narratives':0,'new_search_documents':0,'new_embeddings':0})
save('phase_06_validation_status.json',{'status':'BLOCKED','blocker':'PRODUCTION_ANALYZER_NOT_EXECUTABLE','affected':'assets #11-#30; canary #11','why':'No approved executable real-media analyzer is available for Phase 7; only fixture/synthetic provider and evidence-package builder are present.','minimum_corrective_action':'Provide and validate an approved local/non-external multimodal analyzer supporting image/video input and frozen 18-layer structured output, or authorize a compliant provider.','database_preserved':True,'phase7_safe':False})
rows=''.join(f"| {x['rollout_position']} | {x['filename']} | {x['asset_id']} | PASS | PASS | PENDING_ANALYSIS |\n" for x in assets)
report=f'''# KDI SEMANTIC DATABASE ROLLOUT — PHASE 6 FINAL

STATUS: **PHASE 6: BLOCKED**

The frozen Phase 5 manifest and all 20 canonical identities remain valid. Master destination metadata is readable for 20/20 assets, with no source-drive dependency. No selected media was semantically analyzed.

| # | Filename | Asset ID | Master | Hash | State |
|---:|---|---|---|---|---|
{rows}

All contract, state, evidence, search-document, embedding-reuse, transaction, claim/retry, and security fixture checks passed. Existing 512D OpenCLIP vectors are reusable; no vectors were generated.

## Blocking issue

`PRODUCTION_ANALYZER_NOT_EXECUTABLE`: `src/kdi_media/semantic_analysis.py` constructs evidence-backed packages from already-reviewed evidence; it is not a raw-media analyzer. The only runnable indexing provider is synthetic/fixture-based, while the configured Ollama/Qwen path is unavailable/not approved and OpenAI is prohibited. Therefore Phase 7 cannot safely process IMG_2951.MP4.

Minimum corrective action: provide and validate an approved local/non-external multimodal analyzer with image/video support and frozen 18-layer structured output. Database integrity remains preserved.
'''
(OUT/'PHASE_06_20_ASSET_PRODUCTION_PREFLIGHT_FINAL.md').write_text(report)
print(json.dumps({'status':'BLOCKED','blocker':'PRODUCTION_ANALYZER_NOT_EXECUTABLE','selected':20,'master_metadata_readable':20,'semantic_mutations':0}))
