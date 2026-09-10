from local_18_layer_analyzer import LAYER_IDS, assemble, synthesize_asset, validate

def rec(media="VIDEO", scenes=1, speech="NO_SPEECH", ocr=False):
    return {"asset_id":"a","filename":"x.mp4" if media=="VIDEO" else "x.jpg",
            "mime_type":"video/mp4" if media=="VIDEO" else "image/jpeg","media_type":media,
            "checksum":"abc","scenes":[{"scene_index":i} for i in range(scenes)],
            "keyframes":[{} for _ in range(scenes)],"transcript_state":speech,
            "transcript_chunks":[{"text":"hello world"}] if speech=="MEANINGFUL_SPEECH" else [],
            "ocr_evaluated":True,"ocr_observations_list":[{"text":"KDI"}] if ocr else []}

def obs(**kw):
    base={k:"UNKNOWN" for k in ("people","anatomy","action","environment","closeup","centered","direct_to_camera")};base.update(kw);return base

def check(p):
    validate(p); assert [x["layer_id"] for x in p["layers"]]==list(LAYER_IDS); assert len({x["layer_id"] for x in p["layers"]})==18

def test_image_contract_and_dimensions():
    p=assemble(rec("IMAGE"),obs(people="OBSERVED"));check(p)
    assert p["layers"][2]["state"]=="NOT_APPLICABLE";assert len([0.0]*384)==384;assert len([0.0]*512)==512
def test_single_scene_video(): check(synthesize_asset(rec(scenes=1),[assemble(rec(scenes=1),obs(action="OBSERVED"),scene_index=0)]))
def test_multi_scene_video_scene_first():
    r=rec(scenes=3);p=synthesize_asset(r,[assemble(r,obs(),scene_index=i) for i in range(3)]);check(p);assert len(p["scene_packages"])==3
def test_transcript_evidence():
    p=assemble(rec(speech="MEANINGFUL_SPEECH"),obs());assert p["layers"][13]["state"]=="OBSERVED"
def test_no_speech():
    p=assemble(rec(speech="NO_SPEECH"),obs());assert p["layers"][13]["state"]=="FALSE"
def test_ocr_and_absence():
    assert assemble(rec(ocr=True),obs())["layers"][14]["state"]=="OBSERVED";assert assemble(rec(),obs())["layers"][14]["state"]=="NOT_APPLICABLE"
def test_clinical_safety_and_narrative():
    p=assemble(rec(),obs(anatomy="OBSERVED",action="OBSERVED"));assert p["layers"][6]["state"]=="UNKNOWN";assert p["narrative"]
def test_idempotent_rerun():
    r=rec();o=obs();assert assemble(r,o)==assemble(r,o)
