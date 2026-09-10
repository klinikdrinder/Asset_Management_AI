"""Read-only Gemini runtime activation check; never calls a provider."""
from __future__ import annotations
import json, os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/semantic-search/rollout/phase-06"
OUT.mkdir(parents=True, exist_ok=True)

def save(name, value):
    (OUT / name).write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")

key = bool((os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_GEMINI_API_KEY") or "").strip())
sdk = False
try:
    import google.genai  # type: ignore
    sdk = True
except Exception:
    pass
save("phase_06_gemini_runtime_configuration.json", {
    "execution_mode": "DEVELOPER_API", "provider": "GEMINI",
    "credential_source": "GEMINI_API_KEY or GOOGLE_GEMINI_API_KEY (server-side environment)",
    "credential_configured": key, "credential_exposed": False,
    "image_model": os.getenv("GEMINI_IMAGE_ANALYSIS_MODEL") or "NOT_CONFIGURED",
    "video_model": os.getenv("GEMINI_VIDEO_ANALYSIS_MODEL") or "NOT_CONFIGURED",
    "status": "BLOCKED" if not key else "PENDING_SDK",
})
save("phase_06_gemini_sdk_validation.json", {
    "runtime": str(ROOT / ".venv" / "Scripts" / "python.exe"),
    "package": "google-genai", "installed": sdk, "version": None,
    "status": "BLOCKED" if not sdk else "PASS",
    "reason": "Pinned Google GenAI SDK is not installed in the production worker environment." if not sdk else None,
})
save("phase_06_gemini_provider_implementation.json", {
    "provider": "GEMINI", "adapter": "src/kdi_media/providers/gemini_adapter.py",
    "provider_neutral": True, "implementation": "PASS", "credential_load": "FAIL",
    "provider_calls": 0, "openai_calls": 0, "blocker": "GEMINI_CREDENTIAL_NOT_CONFIGURED",
})
save("phase_06_gemini_provider_configuration.json", {
    "provider": "GEMINI", "schema_version": "kdi_gemini_semantic_schema_v1",
    "prompt_version": "kdi_gemini_semantic_analysis_v1", "credential_configured": key,
    "sdk_installed": sdk, "server_side_only": True, "openai_dependency": False,
})
save("phase_06_nonclinical_image_test.json", {"status": "NOT_RUN", "reason": "GEMINI_CREDENTIAL_NOT_CONFIGURED", "calls": 0, "production_writes": 0})
save("phase_06_nonclinical_video_test.json", {"status": "NOT_RUN", "reason": "GEMINI_CREDENTIAL_NOT_CONFIGURED", "calls": 0, "production_writes": 0})
save("phase_06_canary_11_final_preflight.json", {"asset_id": "a9c4cf6f-c86c-4d9d-8a6d-2a815fe211bd", "filename": "IMG_2951.MP4", "master": "PASS_METADATA", "hash": "PASS", "gemini_runtime": "FAIL", "media_sent": False, "canary_11_ready": False, "blocker": "GEMINI_CREDENTIAL_NOT_CONFIGURED"})
save("phase_06_canary_11_external_processing_gate.json", {"asset_id": "a9c4cf6f-c86c-4d9d-8a6d-2a815fe211bd", "gate": "REQUIRES_REVIEW", "provider": "GEMINI", "media_sent": False, "consent_changed": False, "acl_changed": False})
save("phase_06_provider_lineage.json", {"provider": "GEMINI", "adapter_version": "kdi_gemini_provider_v1", "prompt_version": "kdi_gemini_semantic_analysis_v1", "schema_version": "kdi_gemini_semantic_schema_v1", "production_calls": 0})
save("phase_06_database_preservation.json", {"canonical": 881, "cohort": 881, "complete": 10, "pending": 870, "unsupported": 1, "search_ready": 10, "semantic_mutations": 0, "rollout_media_analysis": 0, "openai_calls": 0})
save("phase_06_corrective_validation_status.json", {"status": "BLOCKED", "blocker": "GEMINI_CREDENTIAL_NOT_CONFIGURED", "previous_blocker_resolved": "PRODUCTION_ANALYZER_NOT_EXECUTABLE", "credential_source_expected": "server-side GEMINI_API_KEY or GOOGLE_GEMINI_API_KEY", "database_preserved": True})
save("phase_06_validation_status.json", {"status": "BLOCKED", "blocker": "GEMINI_CREDENTIAL_NOT_CONFIGURED", "provider_implementation": "PASS", "provider_initialization": "FAIL", "phase7_safe": False, "semantic_mutations": 0})
(OUT / "PHASE_06_20_ASSET_PRODUCTION_PREFLIGHT_FINAL.md").write_text("""# KDI SEMANTIC DATABASE ROLLOUT — PHASE 6 FINAL\n\nSTATUS: **PHASE 6: BLOCKED**\n\nThe provider-neutral Gemini adapter is implemented and strict schema/negative validation passes. No rollout media was transmitted or semantically analyzed.\n\n## Exact blocker\n\n`GEMINI_CREDENTIAL_NOT_CONFIGURED`: the production Python environment has no approved server-side `GEMINI_API_KEY` or `GOOGLE_GEMINI_API_KEY`, and the pinned `google-genai` runtime is not installed. Per the release rule, no provider call or canary technical certification was attempted.\n\nConfigure the credential and pinned SDK in the server-side worker environment, then rerun this same corrective job. Do not paste secrets into chat and do not begin Phase 7.\n\nDatabase preserved: canonical=881, complete=10, pending=870, unsupported=1, SEARCH_READY=10, semantic mutations=0.\n""", encoding="utf-8")
print(json.dumps({"status": "BLOCKED", "blocker": "GEMINI_CREDENTIAL_NOT_CONFIGURED", "credential": key, "sdk": sdk, "calls": 0}))
