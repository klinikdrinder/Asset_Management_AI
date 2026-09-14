import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from kdi_media.semantic_consistency import ConsistencyConfig, compatibility, rule


def test_phase9_config_is_versioned_and_read_only():
    config = ConsistencyConfig.load(ROOT / "config/semantic-search/kdi_semantic_consistency_v1.json")
    assert config["validator_version"] == "kdi_semantic_consistency_v1"
    assert config["configuration_version"] == "kdi_semantic_consistency_config_v1"
    assert config["shadow_mode"] is True
    assert config["database_writes"] is False
    assert config["media_analysis"] is False
    assert len(config.fingerprint) == 64


def test_ontology_compatibility_accepts_supported_pairs():
    config = json.loads((ROOT / "config/semantic-search/kdi_semantic_consistency_v1.json").read_text())
    ok, bad = compatibility({"INJECTING"}, {"LOWER_FACE", "LIPS"}, config["action_anatomy_compatibility"])
    assert ok and bad == []


def test_ontology_compatibility_flags_incompatible_pair():
    config = json.loads((ROOT / "config/semantic-search/kdi_semantic_consistency_v1.json").read_text())
    ok, bad = compatibility({"IMPLANTING_GRAFTS"}, {"LIPS"}, config["action_anatomy_compatibility"])
    assert not ok and bad == ["IMPLANTING_GRAFTS"]


def test_rule_preserves_uncertainty_and_severity():
    result = rule("TREATMENT_ACTION", "PASS_WITH_UNCERTAINTY", "P2", "Treatment remains unknown.")
    assert result["state"] == "PASS_WITH_UNCERTAINTY"
    assert result["severity"] == "P2"
