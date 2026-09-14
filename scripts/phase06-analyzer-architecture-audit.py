"""Record Phase 6 analyzer architecture decision without media or DB writes."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'reports/semantic-search/rollout/phase-06'
OUT.mkdir(parents=True, exist_ok=True)

def save(name, value):
    (OUT / name).write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')

save('phase_06_analyzer_architecture_audit.json', {
    'database': 'Supabase/PostgreSQL', 'vectors': 'pgvector', 'active_media_analyzer': None,
    'decision': 'PRODUCTION_MEDIA_ANALYZER_NOT_SELECTED', 'external_media_transmission': False,
    'gemini': 'ABANDONED_NOT_PRODUCTION', 'ollama': 'NOT_APPROVED_NOT_USED', 'openai_indexing': 'NOT_ALLOWED'
})
save('phase_06_existing_analyzer_inventory.json', {'candidates': [
    {'name': 'OpenCLIP ViT-B-32', 'runtime': 'PyTorch/open_clip', 'installed': True, 'raw_media_inference': False, '18_layer_integration': False, 'status': 'EMBEDDING_ONLY'},
    {'name': 'Faster-Whisper small', 'runtime': 'faster-whisper', 'installed': True, 'raw_media_inference': False, '18_layer_integration': False, 'status': 'AUDIO_ONLY'},
    {'name': 'OpenCV/Pillow/FFmpeg', 'runtime': 'native media tooling', 'installed': True, 'raw_media_inference': False, '18_layer_integration': False, 'status': 'PREPROCESSING_ONLY'},
    {'name': 'SmolVLM2-256M-Video-Instruct', 'runtime': 'Transformers', 'installed': True, 'raw_media_inference': True, '18_layer_integration': False, 'status': 'REJECTED_TESTED', 'reason': 'caption inference passed; strict 18-layer JSON failed'},
    {'name': 'Ollama/Qwen', 'runtime': 'Ollama', 'installed': False, 'raw_media_inference': 'unverified', '18_layer_integration': False, 'status': 'HISTORICAL_NOT_APPROVED'},
    {'name': 'Gemini', 'runtime': 'external API', 'installed': False, 'raw_media_inference': True, '18_layer_integration': 'historical', 'status': 'ABANDONED_NOT_PRODUCTION'},
    {'name': 'OpenAI', 'runtime': 'external API', 'installed': 'adapter only', 'raw_media_inference': True, '18_layer_integration': 'historical', 'status': 'NOT_ALLOWED_FOR_INDEXING'}
], 'approved_existing_analyzer': False})
save('phase_06_historical_analyzer_decisions.json', {'implemented': ['schema', 'validators', 'deterministic timeline', 'evidence package builder', 'fixture providers'], 'planned': ['provider-neutral media analyzer boundary'], 'abandoned': ['Gemini branch'], 'not_approved': ['Ollama/Qwen', 'OpenAI indexing'], 'conclusion': 'No concrete approved production raw-media analyzer was specified or operationally validated.'})
save('phase_06_master_media_retrieval_audit.json', {'authoritative': 'asset_destinations provider/file ID', 'backend_metadata_read': 'PASS_FROM_PHASE5', 'temporary_retrieval_path': 'defined but not executed in restricted runtime', 'source_drive_dependency': False, 'selected_media_semantic_access': False})
save('phase_06_architecture_correction.json', {'gemini': 'ABANDONED_NOT_PRODUCTION', 'ollama': 'NOT_APPROVED_NOT_USED', 'openai_indexing': 'NOT_ALLOWED', 'active_provider': None, 'only_blocker': 'PRODUCTION_MEDIA_ANALYZER_NOT_SELECTED'})
save('phase_06_validation_status.json', {'status': 'BLOCKED', 'blocker': 'PRODUCTION_MEDIA_ANALYZER_NOT_SELECTED', 'database_preserved': True, 'canonical': 881, 'complete': 10, 'pending': 870, 'unsupported': 1, 'search_ready': 10, 'semantic_mutations': 0, 'gemini_calls': 0, 'openai_calls': 0, 'ollama_calls': 0})
(OUT / 'PHASE_06_20_ASSET_PRODUCTION_PREFLIGHT_FINAL.md').write_text('''# KDI SEMANTIC DATABASE ROLLOUT — PHASE 6 ARCHITECTURE AUDIT FINAL\n\nSTATUS: **BLOCKED**\n\nGemini is `ABANDONED_NOT_PRODUCTION`; Ollama/Qwen is `NOT_APPROVED / NOT_USED`; OpenAI indexing is `NOT_ALLOWED`. The audit found OpenCLIP (embeddings), Faster-Whisper (audio), OpenCV/Pillow/FFmpeg (preprocessing), deterministic timeline/evidence code, and fixture providers, but no approved executable raw-media analyzer producing grounded frozen 18-layer output.\n\n## ONLY REMAINING BLOCKER\n\n`PRODUCTION_MEDIA_ANALYZER_NOT_SELECTED`\n\nThe semantic database, evidence model, embeddings, search-document path, and persistence contracts are ready. A production analyzer must still be explicitly selected and approved with image understanding, bounded video/keyframe understanding, structured observations, evidence/temporal grounding, uncertainty handling, and provider-neutral integration. No provider was installed or activated by this audit.\n\nDatabase preserved: canonical=881, complete=10, pending=870, unsupported=1, SEARCH_READY=10; semantic mutations=0; Gemini/OpenAI/Ollama calls=0.\n''', encoding='utf-8')
print(json.dumps({'status': 'BLOCKED', 'blocker': 'PRODUCTION_MEDIA_ANALYZER_NOT_SELECTED', 'semantic_mutations': 0}))
