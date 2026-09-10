import pytest

from kdi_media.semantic_completeness import (
    LayerEvidence, SPEC_FINGERPRINT, SPEC_VERSION,
    evaluate_layer_completeness as evaluate, verify_spec,
)


def ev(layer, **kw):
    base=dict(asset_id="a",filename="x",layer_id=layer,media_kind="video",
              evaluation_marker=True,assertion_count=1,evidence_count=1)
    base.update(kw)
    return LayerEvidence(**base)


def test_locked_spec_gate():
    verify_spec(dict(spec_version=SPEC_VERSION,spec_fingerprint=SPEC_FINGERPRINT,
                     locked=True,status="LOCKED",definition_count=18,descriptions_populated=18))

def test_locked_spec_gate_fails_closed():
    with pytest.raises(RuntimeError): verify_spec({})

def test_no_audio_asset():
    d=evaluate(ev("SPEECH_TRANSCRIPT_AUDIO",modality_assessed=True,has_audio=False))
    assert (d.new_status,d.semantic_resolution)==("COMPLETE","NOT_APPLICABLE")

def test_audio_but_no_speech():
    assert evaluate(ev("SPEECH_TRANSCRIPT_AUDIO",modality_assessed=True,has_audio=True,has_speech=False)).new_status=="COMPLETE"

def test_unintelligible_speech():
    d=evaluate(ev("SPEECH_TRANSCRIPT_AUDIO",modality_assessed=True,has_audio=True,has_speech=True,speech_intelligible=False))
    assert d.new_status=="COMPLETE" and d.requirements_unknown_but_evaluated==1

def test_understandable_untranscribed_speech():
    assert evaluate(ev("SPEECH_TRANSCRIPT_AUDIO",modality_assessed=True,has_audio=True,has_speech=True,speech_intelligible=True)).new_status=="PARTIAL"

def test_no_visible_text():
    d=evaluate(ev("OCR_VISIBLE_TEXT",modality_assessed=True,ocr_processed=True,visible_text=False))
    assert (d.new_status,d.semantic_resolution)==("COMPLETE","NOT_APPLICABLE")

def test_visible_unreadable_text():
    d=evaluate(ev("OCR_VISIBLE_TEXT",modality_assessed=True,ocr_processed=True,visible_text=True,text_readable=False))
    assert d.new_status=="COMPLETE" and d.requirements_unknown_but_evaluated==1

def test_readable_ocr():
    assert evaluate(ev("OCR_VISIBLE_TEXT",modality_assessed=True,ocr_processed=True,visible_text=True,text_readable=True)).new_status=="COMPLETE"

@pytest.mark.parametrize("kind",["image","video"])
def test_blurry_media_is_complete_cinematography(kind):
    assert evaluate(ev("CINEMATOGRAPHY",media_kind=kind)).new_status=="COMPLETE"

def test_unknown_treatment():
    d=evaluate(ev("TREATMENT_PROCEDURE",semantic_state="UNKNOWN",evidence_count=0))
    assert d.new_status=="COMPLETE" and d.semantic_resolution=="UNKNOWN"

def test_observed_treatment():
    assert evaluate(ev("TREATMENT_PROCEDURE",semantic_state="OBSERVED")).new_status=="COMPLETE"

def test_no_person_evaluated():
    assert evaluate(ev("PEOPLE_ROLES",semantic_state="UNKNOWN")).new_status=="COMPLETE"

def test_person_unknown_role():
    assert evaluate(ev("PEOPLE_ROLES",semantic_state="UNKNOWN")).requirements_unknown_but_evaluated==1

def test_still_image_temporal():
    d=evaluate(ev("TEMPORAL_SCENE_STRUCTURE",media_kind="image",assertion_count=0,evidence_count=0))
    assert (d.new_status,d.semantic_resolution)==("COMPLETE","NOT_APPLICABLE")

def test_video_temporal_coverage():
    assert evaluate(ev("TEMPORAL_SCENE_STRUCTURE",temporal_coverage_percent=100)).new_status=="COMPLETE"

def test_video_temporal_review_gap():
    assert evaluate(ev("TEMPORAL_SCENE_STRUCTURE",temporal_coverage_percent=100,temporal_review_required=True)).new_status=="PARTIAL"

def test_grounded_narrative():
    assert evaluate(ev("SEMANTIC_NARRATIVE",short_description=True,master_description=True,narrative_grounded=True)).new_status=="COMPLETE"

def test_missing_master_description():
    d=evaluate(ev("SEMANTIC_NARRATIVE",short_description=True,narrative_grounded=True))
    assert "genuine detailed/master description" in d.missing_requirements

def test_fully_built_search_layer():
    d=evaluate(ev("SEARCH_EMBEDDINGS",search_document=True,normalized_search_text=True,concepts=True,
                  text_embedding=True,visual_embedding_applicable=True,visual_embedding=True,
                  scene_embedding_applicable=True,scene_embedding=True,representation_metadata=True,
                  evidence_lineage=True,representation_spec_version=SPEC_VERSION))
    assert d.new_status=="COMPLETE"

def test_missing_required_embedding():
    d=evaluate(ev("SEARCH_EMBEDDINGS",search_document=True,normalized_search_text=True,concepts=True,
                  representation_metadata=True,evidence_lineage=True,representation_spec_version=SPEC_VERSION))
    assert "text embedding" in d.missing_requirements

def test_unknown_not_false():
    d=evaluate(ev("ANATOMY",semantic_state="UNKNOWN"))
    assert d.semantic_resolution=="UNKNOWN"

def test_processing_complete_completeness_partial():
    assert evaluate(ev("GLOBAL_ASSET_UNDERSTANDING",short_description=True)).new_status=="PARTIAL"

def test_processing_complete_unknown_complete():
    assert evaluate(ev("ENVIRONMENT",semantic_state="UNKNOWN")).new_status=="COMPLETE"

def test_zero_positive_assertions_with_explicit_modality_evaluation():
    d=evaluate(ev("OCR_VISIBLE_TEXT",assertion_count=0,evidence_count=0,modality_assessed=True,ocr_processed=True,visible_text=False))
    assert d.new_status=="COMPLETE"

def test_deterministic_fingerprint():
    d=evaluate(ev("ANATOMY"))
    assert d.fingerprint()==d.fingerprint()
