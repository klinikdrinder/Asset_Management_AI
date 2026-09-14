import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/semantic-search/phase9"
MANIFEST = json.loads((ROOT / "config/semantic-search/kdi_semantic_pilot_v1.json").read_text())


def packages():
    return [json.loads((OUT / f"{a['asset_id']}_consistency_validation.json").read_text()) for a in MANIFEST["assets"]]


def test_exact_assets_and_rule_coverage():
    values = packages()
    assert len(values) == 10
    assert all(len(value["rule_results"]) == 20 for value in values)
    assert sum(len(value["rule_results"]) for value in values) == 200


def test_source_identity_and_versions_match():
    for artifact, asset in zip(packages(), MANIFEST["assets"]):
        assert artifact["asset_id"] == asset["asset_id"]
        assert artifact["filename"] == asset["filename"]
        assert artifact["source_fingerprint"] == asset["content_fingerprint"]["value"]
        assert artifact["semantic_spec_version"] == "semantic_index_v1"
        assert artifact["pilot_manifest_version"] == "kdi_semantic_pilot_v1"


def test_known_review_and_conflicts_are_preserved():
    values = {value["filename"]: value for value in packages()}
    assert values["IMG_1238.MP4"]["overall_consistency_state"] == "REVIEW_REQUIRED"
    assert values["DSC03753.JPG"]["overall_consistency_state"] == "CONFLICT"
    assert values["DSC08097.JPG"]["overall_consistency_state"] == "CONFLICT"
    for name in ("DSC03753.JPG", "DSC08097.JPG"):
        kinds = {issue["issue_type"] for issue in values[name]["issues"]}
        assert "LEGACY_SEARCH_ACTION_MISMATCH" in kinds
        assert "LEGACY_TREATMENT_COMPLETENESS_UNSUPPORTED" in kinds
        assert values[name]["resolved_findings"][0]["resolution"] == "RESOLVED_BY_PHASE7_FALSE_WITH_COMPLETE_SCAN"


def test_no_p0_and_no_forbidden_operations():
    for artifact in packages():
        assert not any(issue["priority"] == "P0" for issue in artifact["issues"])
        assert artifact["prohibitions"] == {
            "media_reprocessed": False,
            "production_writes": False,
            "migrations": False,
            "search_documents_rebuilt": False,
            "embeddings_generated": False,
            "source_artifacts_modified": False,
        }


def test_graph_and_idempotency_provenance():
    for artifact in packages():
        graph = artifact["canonical_graph"]
        assert graph["node_count"] == len(graph["nodes"])
        assert graph["edge_count"] == len(graph["edges"])
        assert artifact["idempotency"]["verified"] is True
        assert len(artifact["idempotency"]["functional_fingerprint"]) == 64

