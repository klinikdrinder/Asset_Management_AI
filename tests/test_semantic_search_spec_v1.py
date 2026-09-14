import hashlib
import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC_PATH = ROOT / "config" / "semantic-search" / "kdi_semantic_search_spec_v1.json"
PILOT_PATH = ROOT / "config" / "semantic-search" / "kdi_semantic_pilot_v1.json"
DOC_PATH = ROOT / "docs" / "semantic-search" / "KDI_SEMANTIC_SEARCH_SPEC_V1.md"

EXPECTED_LAYERS = [
    (1, "ASSET_IDENTITY_PROVENANCE", "Asset Identity & Provenance"),
    (2, "GLOBAL_ASSET_UNDERSTANDING", "Global Asset Understanding"),
    (3, "TEMPORAL_SCENE_STRUCTURE", "Temporal / Scene Structure"),
    (4, "PEOPLE_ROLES", "People & Roles"),
    (5, "PERSON_APPEARANCE", "Person Appearance"),
    (6, "ANATOMY", "Anatomy"),
    (7, "TREATMENT_PROCEDURE", "Treatment / Procedure"),
    (8, "ACTIONS_EVENTS", "Actions & Events"),
    (9, "RELATIONSHIPS", "Relationships"),
    (10, "CLINICAL_VISUAL_OBSERVATIONS", "Clinical Visual Observations"),
    (11, "ENVIRONMENT", "Environment"),
    (12, "CINEMATOGRAPHY", "Cinematography"),
    (13, "COMPOSITION", "Composition"),
    (14, "SPEECH_TRANSCRIPT_AUDIO", "Speech / Transcript / Audio"),
    (15, "OCR_VISIBLE_TEXT", "OCR / Visible Text"),
    (16, "MARKETING_CONTENT_USAGE", "Marketing & Content Usage"),
    (17, "SEMANTIC_NARRATIVE", "Semantic Narrative"),
    (18, "SEARCH_EMBEDDINGS", "Search & Embeddings"),
]


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def fingerprint(spec):
    payload = json.loads(json.dumps(spec))
    del payload["specification"]["specification_fingerprint"]
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


class SemanticSearchSpecV1Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = load(SPEC_PATH)
        cls.pilot = load(PILOT_PATH)
        cls.doc = DOC_PATH.read_text(encoding="utf-8")

    def test_configuration_parses_and_versions_exist(self):
        meta = self.spec["specification"]
        self.assertEqual(meta["version_id"], "semantic_index_v1")
        self.assertEqual(meta["status"], "LOCKED")
        self.assertTrue(meta["ontology_version"])
        self.assertEqual(meta["pilot_manifest_version"], "kdi_semantic_pilot_v1")

    def test_exact_layer_count_order_and_unique_ids(self):
        actual = [(x["number"], x["id"], x["name"]) for x in self.spec["layers"]]
        self.assertEqual(actual, EXPECTED_LAYERS)
        self.assertEqual(self.spec["specification"]["layer_count"], 18)
        self.assertEqual(len({x["id"] for x in self.spec["layers"]}), 18)

    def test_information_states(self):
        self.assertEqual([x["id"] for x in self.spec["information_states"]], ["OBSERVED", "FALSE", "UNKNOWN", "NOT_APPLICABLE"])
        self.assertFalse(self.spec["state_rules"]["null_is_semantic_state"])

    def test_evidence_and_provenance_contract(self):
        self.assertEqual(self.spec["evidence_types"], ["ASSET_LEVEL", "SCENE_LEVEL", "EVENT_LEVEL", "KEYFRAME_LEVEL", "TRANSCRIPT", "OCR", "HUMAN_REVIEW"])
        self.assertEqual(self.spec["provenance_origins"], ["AI_MODEL", "DETERMINISTIC_PROCESSOR", "DATABASE_METADATA", "HUMAN_REVIEW"])

    def test_relevance_grades(self):
        self.assertEqual([(x["score"], x["id"]) for x in self.spec["relevance_grades"]], [(3, "EXACT"), (2, "STRONG"), (1, "PARTIAL"), (0, "IRRELEVANT"), (-1, "CONTRADICTORY")])

    def test_component_version_keys(self):
        self.assertEqual(set(self.spec["component_versions"]), {"ontology_version", "indexing_version", "embedding_version", "query_parser_version", "retrieval_version", "ranking_version", "llm_reranker_version", "benchmark_version", "pilot_manifest_version"})

    def test_pilot_manifest_count_identity_and_traceability(self):
        assets = self.pilot["assets"]
        self.assertEqual(self.pilot["manifest_version"], "kdi_semantic_pilot_v1")
        self.assertEqual(self.pilot["status"], "LOCKED")
        self.assertEqual(self.pilot["pilot_size"], 10)
        self.assertEqual(len(assets), 10)
        self.assertEqual([x["ordinal"] for x in assets], list(range(1, 11)))
        self.assertEqual(len({x["asset_id"] for x in assets}), 10)
        for asset in assets:
            self.assertIn(asset["media_type"], {"image", "video"})
            self.assertEqual(asset["pilot_status"], "ALLOWED")
            self.assertEqual(asset["filename"], asset["current_source"]["filename"])
            self.assertRegex(asset["asset_id"], r"^[0-9a-f-]{36}$")
            self.assertRegex(asset["content_fingerprint"]["value"], r"^[0-9a-f]{64}$")

    def test_fingerprint_is_reproducible(self):
        expected = self.spec["specification"]["specification_fingerprint"]
        self.assertRegex(expected, r"^[0-9a-f]{64}$")
        self.assertEqual(fingerprint(self.spec), expected)

    def test_human_and_machine_specs_materially_agree(self):
        meta = self.spec["specification"]
        for value in [meta["version_id"], meta["ontology_version"], meta["pilot_manifest_version"], meta["specification_fingerprint"]]:
            self.assertIn(value, self.doc)
        layer_section = self.doc.split("## Locked 18 layers", 1)[1].split("## Information states", 1)[0]
        rows = re.findall(r"^\| (\d+) \| `([A-Z_]+)` \| ([^|]+?) \|$", layer_section, re.MULTILINE)
        self.assertEqual([(int(n), code, name.strip()) for n, code, name in rows], EXPECTED_LAYERS)
        for state in self.spec["information_states"]:
            self.assertIn(f"`{state['id']}`", self.doc)
        for evidence in self.spec["evidence_types"]:
            self.assertIn(f"`{evidence}`", self.doc)


if __name__ == "__main__":
    unittest.main()
