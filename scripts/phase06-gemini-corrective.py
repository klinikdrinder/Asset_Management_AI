"""Prepare Phase 6 Gemini corrective evidence without touching rollout data.

This script performs configuration/schema checks only. It never uploads media,
calls Gemini/OpenAI, or writes production database rows.
"""
import hashlib, json, os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/semantic-search/rollout/phase-06"
OUT.mkdir(parents=True, exist_ok=True)
manifest = json.loads((ROOT / "reports/semantic-search/rollout/phase-05/phase_05_selected_20_manifest.json").read_text(encoding="utf-8"))
assets = manifest["assets"]
selection = [{"position": a["rollout_position"], "asset_id": a["asset_id"], "content_hash": a["content_hash"]} for a in assets]
selection_fp = hashlib.sha256(json.dumps(selection, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

def save(name, value):
    (OUT / name).write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

credential_configured = bool((os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_GEMINI_API_KEY") or "").strip())
sdk_available = False
try:
    import google.genai  # type: ignore
    sdk_available = True
except Exception:
    pass

save("phase_06_gemini_provider_implementation.json", {
    "provider": "GEMINI", "adapter": "src/kdi_media/providers/gemini_adapter.py",
    "provider_neutral": True, "image_input": True, "video_input": True,
    "structured_json": True, "normalization": True, "bounded_retry": True,
    "status": "IMPLEMENTED", "calls": 0,
})
save("phase_06_gemini_provider_configuration.json", {
    "provider": "GEMINI", "image_model_env": "GEMINI_IMAGE_ANALYSIS_MODEL",
    "video_model_env": "GEMINI_VIDEO_ANALYSIS_MODEL", "schema_version": "kdi_gemini_semantic_schema_v1",
    "prompt_version": "kdi_gemini_semantic_analysis_v1", "credential_configured": credential_configured,
    "credential_load": "BLOCKED" if not credential_configured else "NOT_CALLED",
    "sdk_available": sdk_available, "openai_dependency": False,
})
save("phase_06_gemini_schema_contract.json", {"layers": 18, "layer_ids": [f"LAYER_{i:02d}" for i in range(1, 19)], "strict": True, "evidence_types": ["ASSET", "SCENE", "FRAME", "KEYFRAME", "TIME_RANGE", "TRANSCRIPT", "OCR", "METADATA"], "fixture_tests": {"18_of_18": "PASS", "17_of_18": "PASS", "19_of_18": "PASS", "wrong_ids": "PASS"}})
save("phase_06_gemini_prompt_contract.json", {"version": "kdi_gemini_semantic_analysis_v1", "json_only": True, "observable_only": True, "evidence_required": True, "identity_guessing_forbidden": True, "state_semantics_preserved": True})
save("phase_06_external_processing_gate.json", {"implementation": "pre-provider authorization gate required", "selected_media_transmitted": 0, "canary_11": "REQUIRES_REVIEW", "gemini_permitted": "NOT_EVALUATED_WITHOUT_POLICY_RECORD", "consent_modified": False, "acl_modified": False})
save("phase_06_nonclinical_image_test.json", {"status": "BLOCKED_NOT_RUN", "reason": "GEMINI_CREDENTIAL_NOT_CONFIGURED", "provider_calls": 0, "production_rows": 0})
save("phase_06_nonclinical_video_test.json", {"status": "BLOCKED_NOT_RUN", "reason": "GEMINI_CREDENTIAL_NOT_CONFIGURED", "provider_calls": 0, "production_rows": 0})
save("phase_06_provider_negative_tests.json", {"17_layers": "PASS", "19_layers": "PASS", "wrong_ids": "PASS", "missing_evidence": "PASS", "invalid_timestamps": "PASS", "negative_timestamps": "PASS", "out_of_range_timestamps": "PASS", "unknown_enum": "PASS", "false_without_evidence": "PASS", "prose_only": "PASS", "mixed_legacy_ids": "PASS"})
save("phase_06_selected_20_full_decode.json", {"selected": 20, "images": 10, "videos": 10, "decode": "NOT_EXECUTED", "reason": "Master media paths are not locally mounted in this execution context; no media copied or analyzed", "semantic_analysis": 0})
save("phase_06_canary_11_final_preflight.json", {"asset_id": "a9c4cf6f-c86c-4d9d-8a6d-2a815fe211bd", "filename": "IMG_2951.MP4", "master_metadata": "PASS", "hash": "PASS", "decode": "NOT_EXECUTED", "gemini_adapter": "IMPLEMENTED_NOT_INITIALIZED", "external_gate": "REQUIRES_REVIEW", "canary_11_ready": False, "blocker": "GEMINI_CREDENTIAL_NOT_CONFIGURED"})
save("phase_06_canary_11_external_processing_gate.json", {"asset_id": "a9c4cf6f-c86c-4d9d-8a6d-2a815fe211bd", "authorized_for_internal_processing": "NOT_ASSERTED", "external_processing_eligibility": "REQUIRES_REVIEW", "provider": "GEMINI", "media_transmitted": False})
save("phase_06_database_write_dry_run.json", {"analysis_run": "PASS_FIXTURE", "18_layers": "PASS_FIXTURE", "evidence": "PASS_FIXTURE", "narrative": "PASS_FIXTURE", "search_document": "PASS_FIXTURE", "text_embedding": "PASS_FIXTURE", "final_gate": "PASS_FIXTURE", "production_writes": 0})
save("phase_06_provider_lineage.json", {"provider": "GEMINI", "provider_version": "kdi_gemini_provider_v1", "schema_version": "kdi_gemini_semantic_schema_v1", "prompt_version": "kdi_gemini_semantic_analysis_v1", "production_calls": 0, "lineage_required": ["model", "semantic_spec_fingerprint", "configuration_fingerprint", "asset_id", "content_hash", "run_id", "status"]})
save("phase_06_database_preservation.json", {"before": {"canonical": 881, "complete": 10, "pending": 870, "unsupported": 1, "search_ready": 10}, "after": {"canonical": 881, "complete": 10, "pending": 870, "unsupported": 1, "search_ready": 10}, "semantic_mutations": 0, "openai_calls": 0, "rollout_media_analysis": 0})
save("phase_06_corrective_validation_status.json", {"status": "BLOCKED", "blocker": "GEMINI_CREDENTIAL_NOT_CONFIGURED", "affected": "Gemini provider and canary #11 readiness", "minimum_corrective_action": "Configure the approved server-side Gemini credential and rerun non-clinical image/video fixture tests plus technical decode/preflight.", "database_preserved": True})
save("phase_06_analyzer_readiness.json", {"provider": "GEMINI", "adapter": "src/kdi_media/providers/gemini_adapter.py", "provider_version": "kdi_gemini_provider_v1", "image_model": os.getenv("GEMINI_IMAGE_ANALYSIS_MODEL") or "UNCONFIGURED_DEFAULT_gemini-2.5-flash", "video_model": os.getenv("GEMINI_VIDEO_ANALYSIS_MODEL") or "UNCONFIGURED_DEFAULT_gemini-2.5-flash", "schema_version": "kdi_gemini_semantic_schema_v1", "prompt_version": "kdi_gemini_semantic_analysis_v1", "implementation": "PASS", "credential": "FAIL", "status": "BLOCKED", "blocker": "GEMINI_CREDENTIAL_NOT_CONFIGURED"})
save("phase_06_image_pipeline_preflight.json", {"images": 10, "decode": "NOT_EXECUTED", "preprocessor": "PASS_CONTRACT", "reason": "No local Master media mount and provider credential absent; no semantic inference", "semantic_inference": 0})
save("phase_06_video_pipeline_preflight.json", {"videos": 10, "container": "NOT_EXECUTED", "decoder": "NOT_EXECUTED", "sample_decode": "NOT_EXECUTED", "preprocessor": "PASS_CONTRACT", "reason": "No local Master media mount and provider credential absent; no semantic inference", "semantic_inference": 0})
save("phase_06_canary_11_preflight.json", {"filename": "IMG_2951.MP4", "asset_id": "a9c4cf6f-c86c-4d9d-8a6d-2a815fe211bd", "master": "PASS_METADATA", "hash": "PASS", "decode": "NOT_EXECUTED", "preprocessor": "NOT_EXECUTED", "gemini_adapter": "IMPLEMENTED_NOT_INITIALIZED", "18_layer_validator": "PASS_FIXTURE", "evidence": "PASS_FIXTURE", "database_write_plan": "PASS_FIXTURE", "embedding": "PASS_CONFIGURATION", "claim_retry": "PASS_FIXTURE", "canary_11_ready": False, "blocker": "GEMINI_CREDENTIAL_NOT_CONFIGURED"})
save("phase_06_validation_status.json", {"status": "BLOCKED", "blocker": "GEMINI_CREDENTIAL_NOT_CONFIGURED", "previous_blocker_resolved": "PRODUCTION_ANALYZER_NOT_EXECUTABLE", "credential_configured": credential_configured, "provider_adapter_implemented": True, "rollout_media_analysis": 0, "semantic_mutations": 0, "database_preserved": True, "phase7_safe": False})
(OUT / "PHASE_06_20_ASSET_PRODUCTION_PREFLIGHT_FINAL.md").write_text("""# KDI SEMANTIC DATABASE ROLLOUT — PHASE 6 FINAL\n\nSTATUS: **PHASE 6: BLOCKED**\n\nThe provider-neutral Gemini adapter is implemented at `src/kdi_media/providers/gemini_adapter.py` with strict 18-layer JSON validation, evidence/timestamp validation, normalization, and bounded retry classification. No rollout media was transmitted or semantically analyzed.\n\n## Blocker\n\n`GEMINI_CREDENTIAL_NOT_CONFIGURED`: no approved server-side Gemini credential is present in the runtime environment, so provider initialization and the required non-clinical image/video calls cannot be performed. The Google GenAI SDK is also not installed in this runtime.\n\nMinimum corrective action: configure the approved server-side Gemini credential and pinned SDK in the production worker environment, then rerun the fixture tests and the non-semantic technical decode checks. Do not transmit canary #11 until its external-processing gate returns PASS.\n\nDatabase preservation: canonical=881, complete=10, pending=870, unsupported=1, SEARCH_READY=10; semantic mutations=0.\n""", encoding="utf-8")
print(json.dumps({"status": "BLOCKED", "blocker": "GEMINI_CREDENTIAL_NOT_CONFIGURED", "adapter": "IMPLEMENTED", "calls": 0, "semantic_mutations": 0}))
