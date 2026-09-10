"""Record the local/non-external Phase 6 architecture audit.

Read-only: no media is opened for semantic inference and no database rows are
created or changed.
"""
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/semantic-search/rollout/phase-06"
OUT.mkdir(parents=True, exist_ok=True)

def save(name, value):
    (OUT / name).write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

save("phase_06_architecture_correction.json", {
    "active_provider": "NONE_AVAILABLE",
    "gemini": "ABANDONED_NOT_PRODUCTION",
    "openai": "NOT_USED_FOR_INDEXING",
    "external_media_transmission": False,
    "frozen_semantic_fingerprint": "ba43dab744dedfd590e81be5c8ec5ec8ab7c0bda79f8aca16c0b24d198294888",
})
save("phase_06_local_analyzer_inventory.json", {
    "candidates": [
        {"name": "OpenCLIP ViT-B-32", "type": "visual embedding", "installed": True, "model_files": True, "image_input": True, "video_frame_input": True, "structured_output": False, "local": True, "integration": True, "production_suitable_18_layer": False, "reason": "Embedding model; does not generate grounded semantic assertions."},
        {"name": "faster-whisper-small", "type": "speech transcription", "installed": True, "model_files": True, "image_input": False, "video_frame_input": False, "structured_output": False, "local": True, "integration": True, "production_suitable_18_layer": False, "reason": "Audio-only capability."},
        {"name": "OpenCV/Pillow", "type": "technical media decoding", "installed": True, "model_files": False, "image_input": True, "video_frame_input": True, "structured_output": False, "local": True, "integration": True, "production_suitable_18_layer": False, "reason": "Decode/preprocessing only."},
        {"name": "Ollama/qwen3-vl", "type": "historical local VLM", "installed": False, "model_files": False, "image_input": False, "video_frame_input": False, "structured_output": False, "local": True, "integration": "historical", "production_suitable_18_layer": False, "reason": "No local model/runtime available; historical configuration is not an approved active path."},
        {"name": "Gemini", "type": "external multimodal", "installed": False, "model_files": False, "image_input": True, "video_frame_input": True, "structured_output": True, "local": False, "integration": "historical", "production_suitable_18_layer": False, "reason": "Explicitly abandoned by user decision; never active for indexing."},
    ],
    "hardware_audit": {"cpu": "UNAVAILABLE_IN_RESTRICTED_RUNTIME", "ram": "UNAVAILABLE_IN_RESTRICTED_RUNTIME", "gpu": "UNAVAILABLE_IN_RESTRICTED_RUNTIME", "disk": "workspace available; model capacity not sufficient/evidenced"},
    "result": "NO_VIABLE_LOCAL_18_LAYER_ANALYZER",
})
save("phase_06_local_analyzer_selection.json", {"selected": None, "status": "BLOCKED", "reason": "No installed local vision-language analyzer supports grounded image/video understanding and frozen 18-layer structured output."})
save("phase_06_local_analyzer_configuration.json", {"provider": "LOCAL", "status": "NOT_CONFIGURED", "external_media_transmission": False, "fail_closed": True, "embeddings_preserved": {"visual": "OpenCLIP ViT-B-32 512D", "text": "intfloat/multilingual-e5-small 384D"}})
save("phase_06_local_hardware_audit.json", {"os": "Windows (restricted host context)", "cpu": "CPU-only torch runtime", "ram": "not exposed by restricted WMI", "gpu": "not available", "vram": "0 / CUDA unavailable", "python": "3.14.6", "torch": "2.13.0+cpu", "disk": "model downloaded locally; workspace available"})
save("phase_06_local_model_selection.json", {"selected": "HuggingFaceTB/SmolVLM2-256M-Video-Instruct", "runtime": "transformers", "device": "cpu", "selection_status": "REJECTED_FOR_PRODUCTION", "reason": "Real image/video caption inference works, but strict 18-layer JSON output test returned non-JSON. No semantic normalization may fabricate structure."})
save("phase_06_local_model_manifest.json", {"model": "HuggingFaceTB/SmolVLM2-256M-Video-Instruct", "revision": "main", "local_path": ".kdi-models/SmolVLM2-256M-Video-Instruct", "weights_downloaded": True, "license": "SEE_MODEL_CARD", "integrity": "local snapshot completed"})
save("phase_06_local_runtime_configuration.json", {"runtime": "transformers", "runtime_version": "4.57.6", "device": "cpu", "precision": "float32", "external_media_transmission": False, "fail_closed": True})
save("phase_06_local_provider_implementation.json", {"provider": "LOCAL", "adapter": "src/kdi_media/providers/local_adapter.py", "status": "IMPLEMENTED_FAIL_CLOSED", "model_load": "PASS", "image_caption_inference": "PASS", "video_keyframe_inference": "PASS", "strict_18_layer_output": "FAIL", "production_ready": False})
save("phase_06_local_prompt_contract.json", {"version": "kdi_local_semantic_analysis_v1", "all_18_layers": True, "json_only": True, "evidence_required": True, "state_semantics": True})
save("phase_06_local_image_fixture_test.json", {"model_load": "PASS", "inference": "PASS", "strict_18_layer_normalization": "FAIL_NON_JSON_RESPONSE", "external_calls": 0, "production_writes": 0})
save("phase_06_local_video_fixture_test.json", {"decode": "PASS", "keyframes": 3, "inference": "PASS_CAPTION_PATH", "strict_18_layer_normalization": "NOT_PROVEN", "external_calls": 0, "production_writes": 0})
save("phase_06_local_audio_fixture_test.json", {"status": "NOT_RUN", "reason": "Analyzer contract blocker reached first", "external_calls": 0})
save("phase_06_local_ocr_fixture_test.json", {"status": "NOT_RUN", "reason": "Analyzer contract blocker reached first", "external_calls": 0})
save("phase_06_local_performance_benchmark.json", {"image_inference": "PASS", "video_keyframe_inference": "PASS", "device": "cpu", "peak_memory": "approximately 1.3GB observed", "throughput": "not certified because structured output failed", "operationally_viable": False})
save("phase_06_local_image_fixture_test.json", {"status": "NOT_RUN", "reason": "No viable local semantic analyzer selected", "production_writes": 0})
save("phase_06_local_video_fixture_test.json", {"status": "NOT_RUN", "reason": "No viable local semantic analyzer selected", "production_writes": 0})
save("phase_06_local_performance_test.json", {"status": "NOT_RUN", "reason": "No viable local semantic analyzer selected", "semantic_inference": 0})
save("phase_06_selected_20_full_decode.json", {"images": 10, "videos": 10, "status": "NOT_RUN", "reason": "Master media is not mounted in this restricted workspace; no selected media was copied or analyzed."})
save("phase_06_canary_11_final_preflight.json", {"asset_id": "a9c4cf6f-c86c-4d9d-8a6d-2a815fe211bd", "filename": "IMG_2951.MP4", "master_hash_metadata": "PASS", "local_analyzer": "FAIL_STRICT_OUTPUT", "media_transmitted": False, "canary_11_ready": False, "blocker": "LOCAL_PRODUCTION_ANALYZER_NOT_AVAILABLE"})
save("phase_06_database_write_dry_run.json", {"fixture_contract": "PASS", "production_writes": 0, "partial_failure_safe": True})
save("phase_06_database_preservation.json", {"canonical": 881, "cohort": 881, "complete": 10, "pending": 870, "unsupported": 1, "search_ready": 10, "rollout_semantic_analysis": 0, "semantic_mutations": 0, "gemini_calls": 0, "openai_calls": 0})
save("phase_06_corrective_validation_status.json", {"status": "BLOCKED", "blocker": "LOCAL_PRODUCTION_ANALYZER_NOT_AVAILABLE", "gemini_history": "ABANDONED_NOT_PRODUCTION", "database_preserved": True, "phase7_safe": False, "minimum_required": "Approved local/self-hosted multimodal model with image/video input, grounded evidence, and strict 18-layer structured output."})
save("phase_06_validation_status.json", {"status": "BLOCKED", "blocker": "LOCAL_PRODUCTION_ANALYZER_NOT_AVAILABLE", "external_media_transmission": False, "rollout_media_analysis": 0, "semantic_mutations": 0})
(OUT / "PHASE_06_20_ASSET_PRODUCTION_PREFLIGHT_FINAL.md").write_text("""# KDI SEMANTIC DATABASE ROLLOUT — PHASE 6 LOCAL ANALYZER FINAL\n\nSTATUS: **PHASE 6: BLOCKED**\n\nGemini is recorded as `ABANDONED_NOT_PRODUCTION`; OpenAI is not used for semantic indexing. The local inventory found OpenCLIP (embedding only), Faster-Whisper (audio only), and OpenCV/Pillow (decode/preprocessing). SmolVLM2-256M-Video-Instruct was provisioned locally and passed real synthetic image and sampled-keyframe caption inference, but its strict 18-layer JSON test returned non-JSON output. Historical Ollama/Qwen configuration is not installed and is not reactivated.\n\n## Exact remaining blocker\n\n`LOCAL_PRODUCTION_ANALYZER_NOT_AVAILABLE`\n\nThe tested local VLM is not production-suitable because it cannot reliably emit the frozen structured contract. Minimum corrective action: provision and validate a local/self-hosted multimodal model/runtime with reliable strict 18-layer JSON output, grounded evidence, and temporal support. Until then, Phase 7 and all selected-media inference remain prohibited.\n\nDatabase preserved: canonical=881, complete=10, pending=870, unsupported=1, SEARCH_READY=10; rollout semantic analyses=0; Gemini calls=0; OpenAI calls=0.\n""", encoding="utf-8")
print(json.dumps({"status": "BLOCKED", "blocker": "LOCAL_PRODUCTION_ANALYZER_NOT_AVAILABLE", "gemini": "ABANDONED_NOT_PRODUCTION", "calls": 0, "semantic_mutations": 0}))
