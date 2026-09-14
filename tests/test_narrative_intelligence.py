import json
from pathlib import Path

from kdi_media.narrative_intelligence import NarrativeConfig,make_claim,render_search_sentence,validate_claims

ROOT=Path(__file__).resolve().parents[1]
def config():return NarrativeConfig.load(ROOT/"config/semantic-search/kdi_narrative_generator_v1.json")
def fact(fid,layer,concept,value=True,confidence=.9):return {"fact_id":fid,"layer_number":layer,"concept":concept,"value":value,"confidence":confidence}

def test_config_is_deterministic_shadow_only():
    cfg=config(); assert cfg["temperature"]==0 and cfg["template_fallback_enabled"] and not cfg["production_database_writes"] and not cfg["embedding_generation"]

def test_strong_evidence_fixture_retains_major_concepts():
    by={4:[fact("r1",4,"CLINICIAN"),fact("r2",4,"PATIENT")],8:[fact("a1",8,"DRAWING_HAIRLINE")],6:[fact("n1",6,"FRONTAL_HAIRLINE")],7:[fact("t1",7,"PRE_PROCEDURE")]}
    text,supports,_=render_search_sentence(by); lower=text.lower(); assert "clinician" in lower and "patient" in lower and "drawing hairline" in lower and "frontal hairline" in lower and "pre procedure" in lower; assert len(supports)==5

def test_unknown_treatment_fixture_does_not_invent_fue():
    by={4:[fact("r1",4,"CLINICIAN"),fact("r2",4,"PATIENT")],6:[fact("n1",6,"SCALP")]}; text,_,_=render_search_sentence(by); assert "fue" not in text.lower() and "hair transplant" not in text.lower()

def test_ocr_and_transcript_modalities_stay_explicit():
    ocr=make_claim("a","ocr","Visible text reads FUE.",["ocr1"],"OCR",.9); speech=make_claim("a","speech","The speaker mentions FUE.",["tx1"],"TRANSCRIPT",.9)
    assert ocr["assertion_type"]=="OCR" and speech["assertion_type"]=="TRANSCRIPT"
    assert validate_claims([ocr,speech],{"ocr1","tx1"},{"ocr1"},{"tx1"})["valid"]

def test_conflict_or_unapproved_modality_fails_validation():
    claim=make_claim("a","ocr","Visible text reads FUE.",["rejected"],"OCR",.9); result=validate_claims([claim],{"rejected"},set(),set()); assert not result["valid"] and result["unsupported_claims"]==1

def test_unknown_scene_is_not_accepted():
    claim=make_claim("a","scene","The exact procedure cannot be determined.",["scene:s1"],"VISUAL",.5,False); assert not claim["accepted"] and claim["status"]=="SUPPORTED"

