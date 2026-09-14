import hashlib
import json
from pathlib import Path

from kdi_media.semantic_analysis import SemanticAnalyzerConfig, canonical_fingerprint


ROOT = Path(__file__).resolve().parents[1]


def test_phase5_configuration_is_versioned_and_safe():
    path = ROOT / "config/semantic-search/kdi_semantic_analyzer_v1.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    loaded = SemanticAnalyzerConfig.load(path)
    assert raw["analyzer_version"] == "kdi_semantic_analyzer_v1"
    assert raw["configuration_version"] == "kdi_semantic_analyzer_config_v1"
    assert loaded.fingerprint == canonical_fingerprint(raw)
    assert loaded.fingerprint == hashlib.sha256(
        json.dumps(raw, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()
    assert raw["transcription_enabled"] is False
    assert raw["ocr_enabled"] is False
    assert raw["embedding_generation_enabled"] is False
    assert raw["search_document_generation_enabled"] is False
    assert raw["no_face_recognition"] is True
    assert raw["production_write_enabled"] is False
