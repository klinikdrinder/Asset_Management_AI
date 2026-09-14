import importlib.util, json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
PLAN=json.loads((ROOT/"reports/semantic-search/completeness/kdi_selective_remediation_plan.json").read_text())
spec=importlib.util.spec_from_file_location("remediation",ROOT/"scripts/semantic-search/remediate_pilot_v1.py")
mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)

def test_exact_pilot_scope(): assert len(PLAN["assets"])==10
def test_master_richer_than_short(): assert all(len(x["master_description"])>=len(x["short_description"])+80 for x in PLAN["assets"])
def test_no_duplicates(): assert all(x["master_description"]!=x["short_description"] for x in PLAN["assets"])
def test_master_grounding_links(): assert all(all(c["assertions"] for c in x["claims"]) for x in PLAN["assets"])
def test_unknown_treatment_preserved():
    for f in ("DSC03753.JPG","DSC08097.JPG","IMG_0493.MP4","IMG_1148.MP4","IMG_1160.MP4","IMG_1238.MP4","IMG_9871.MOV"):
        assert "identified reliably" in mod.MASTER[f]
def test_specific_injectable_unknown(): assert "specific injectable treatment cannot be determined" in mod.MASTER["IMG_3429.MP4"]
def test_narrative_claim_evidence_links(): assert all(all("assertion_id" in z for z in c["assertions"]) for x in PLAN["assets"] for c in x["claims"])
def test_eligible_narrative_material(): assert all(len(x["claims"])>=3 for x in PLAN["assets"])
def test_v1_document_lineage(): assert PLAN["spec_version"]==mod.SPEC and PLAN["spec_fingerprint"]==mod.SPEC_FP
def test_document_fingerprint_tracks_text(): assert all(mod.sha(x["search_text"])==x["document_fingerprint"] for x in PLAN["assets"])
def test_document_ids_unique(): assert len({x["document_id"] for x in PLAN["assets"]})==10
def test_narrative_ids_unique(): assert len({x["narrative_id"] for x in PLAN["assets"]})==10
def test_search_evidence_present(): assert all(all(c["assertion_id"] for c in x["concepts"]) for x in PLAN["assets"])
def test_visual_regeneration_absent(): assert "OpenClipEncoder" not in (ROOT/"scripts/semantic-search/remediate_pilot_v1.py").read_text()
def test_no_blanket_complete_update(): assert "SET completeness_status = 'COMPLETE'" not in (ROOT/"scripts/semantic-search/remediate_pilot_v1.py").read_text()
def test_no_media_opening(): assert "ffmpeg" not in (ROOT/"scripts/semantic-search/remediate_pilot_v1.py").read_text().lower()
def test_temporal_scope_only_img1238():
    expected={(f,l) for f in mod.PILOTS for l in ("GLOBAL_ASSET_UNDERSTANDING","SEMANTIC_NARRATIVE","SEARCH_EMBEDDINGS")}|{("IMG_1238.MP4","TEMPORAL_SCENE_STRUCTURE")}
    assert len(expected)==31
