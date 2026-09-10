import hashlib
import json
from pathlib import Path

import pytest

from kdi_media.semantic_specification import (
    EXPECTED_SEMANTIC_SPEC_FINGERPRINT, EXPECTED_SEMANTIC_SPEC_VERSION,
    SemanticSpecificationMismatch, resolve_locked_semantic_specification,
)

ROOT = Path(__file__).resolve().parents[1]


class Query:
    def __init__(self, rows): self.rows = rows
    def select(self, *_): return self
    def eq(self, *_): return self
    def limit(self, *_): return self
    def execute(self): return type("Response", (), {"data": self.rows})()


class Client:
    def __init__(self, rows): self.rows = rows
    def table(self, name):
        assert name == "semantic_specifications"
        return Query(self.rows)


def test_repository_fingerprint_and_layer_contract():
    spec = json.loads((ROOT / "config/semantic-search/kdi_semantic_18_layer_v1.json").read_text(encoding="utf-8"))
    expected = spec.pop("spec_fingerprint")
    canonical = json.dumps(spec, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    assert hashlib.sha256(canonical).hexdigest() == expected == EXPECTED_SEMANTIC_SPEC_FINGERPRINT
    assert spec["spec_version"] == EXPECTED_SEMANTIC_SPEC_VERSION
    assert len(spec["layers"]) == 18
    required = {"description", "applicability_rules", "expected_information", "completeness_rules", "search_inclusion_rules", "prohibited_inferences"}
    assert all(required <= layer.keys() and all(layer[key] for key in required) for layer in spec["layers"])


def test_runtime_resolver_accepts_exact_locked_contract():
    result = resolve_locked_semantic_specification(Client([{"spec_version": EXPECTED_SEMANTIC_SPEC_VERSION,
        "spec_fingerprint": EXPECTED_SEMANTIC_SPEC_FINGERPRINT, "status": "LOCKED", "locked": True}]))
    assert result.spec_fingerprint == EXPECTED_SEMANTIC_SPEC_FINGERPRINT


def test_runtime_resolver_fails_closed_on_mismatch():
    with pytest.raises(SemanticSpecificationMismatch):
        resolve_locked_semantic_specification(Client([{"spec_version": EXPECTED_SEMANTIC_SPEC_VERSION,
            "spec_fingerprint": "0" * 64, "status": "LOCKED", "locked": True}]))
