import json
from pathlib import Path

import cv2
import easyocr
import numpy as np

from kdi_media.ocr_intelligence import (OCRConfig, box_from_points, detect_text_candidates,
    functional_output, group_frame_candidates, hash_distance, normalize_text,
    perceptual_hash, search_status, valid_box, visible_text_state)

ROOT=Path(__file__).resolve().parents[1]

def cfg():return OCRConfig.load(ROOT/"config/semantic-search/kdi_ocr_intelligence_v1.json")
def text_frame(text="KDI CLINIC",low=False):
    image=np.full((240,640,3),170 if low else 255,np.uint8); color=(145,145,145) if low else (0,0,0)
    cv2.putText(image,text,(45,140),cv2.FONT_HERSHEY_SIMPLEX,2,color,5,cv2.LINE_AA); return image

def test_config_shadow_safety_and_fingerprint():
    value=cfg(); assert value.fingerprint=="3749888c499007c0d77a4530ffa069549ba3ad216f3333247fc02c74318fd280"; assert value["shadow_mode"] and not value["production_database_writes"]

def test_clear_and_low_contrast_text_candidates():
    assert detect_text_candidates(text_frame(),cfg()["text_detector"]); assert detect_text_candidates(text_frame(low=True),cfg()["text_detector"])

def test_local_ocr_recognizes_clear_text():
    model_dir=ROOT/"tmp"/"phase7_easyocr_models"
    reader=easyocr.Reader(["en"],gpu=False,model_storage_directory=str(model_dir),user_network_directory=str(model_dir),download_enabled=False,verbose=False)
    recognized=" ".join(str(x[1]) for x in reader.readtext(text_frame(),detail=1,rotation_info=[90,180,270],canvas_size=1600))
    assert "KDI" in recognized.upper() and "CLINIC" in recognized.upper()

def test_no_text_and_failure_negative_safety():
    assert detect_text_candidates(np.full((240,640,3),127,np.uint8),cfg()["text_detector"])==[]
    assert visible_text_state(True,True,0)=="FALSE"; assert visible_text_state(False,True,0)=="UNKNOWN"; assert visible_text_state(True,False,0)=="UNKNOWN"; assert visible_text_state(False,False,3)=="OBSERVED"

def test_rotated_text_detection_and_box_validity():
    rotated=cv2.rotate(text_frame(),cv2.ROTATE_90_CLOCKWISE); candidates=detect_text_candidates(rotated,cfg()["text_detector"]); assert candidates
    height,width=rotated.shape[:2]; assert all(valid_box(x["bounding_box"],width,height) for x in candidates)

def test_brief_video_text_is_scanned_and_tracked():
    rows=[]; fps=20
    for number in range(60):
        frame=text_frame("BRIEF") if 20<=number<30 else np.full((240,640,3),255,np.uint8)
        for candidate in detect_text_candidates(frame,cfg()["text_detector"]):candidate.update(frame_number=number,quality=.8,content_hash=perceptual_hash(frame,candidate["bounding_box"])); rows.append(candidate)
    tracks=group_frame_candidates(rows,fps,8,.12,"fixture",18); assert tracks; assert any(x["start_time"]<=1.1 and x["end_time"]>=1.4 for x in tracks)

def test_persistent_caption_deduplicates_and_changing_screen_splits():
    box=box_from_points([[10,10],[300,70]],640,240); base={"bounding_box":box,"candidate_confidence":.9,"quality":.9}
    same=[{**base,"frame_number":n,"content_hash":"0000000000000000"} for n in range(20)]
    tracks=group_frame_candidates(same,20,8,.12,"same",18); assert len(tracks)==1
    changed=same[:10]+[{**base,"frame_number":n,"content_hash":"ffffffffffffffff"} for n in range(10,20)]
    tracks=group_frame_candidates(changed,20,8,.12,"changed",18); assert len(tracks)==2; assert hash_distance("0"*16,"f"*16)==64

def test_search_acceptance_and_normalization():
    acceptance=cfg()["acceptance"]; assert normalize_text(" KDI\n  CLINIC ")=="KDI CLINIC"
    assert search_status("KDI CLINIC",.95,acceptance)[0]=="ACCEPTED_FOR_SEARCH"; assert search_status("%%%%",.99,acceptance)[0]=="REJECTED_GIBBERISH"; assert search_status("possible text",.55,acceptance)[0]=="REVIEW_REQUIRED"

def test_idempotent_functional_output():
    value={"generated_at":"x","performance":{"seconds":2},"idempotency":{"verified":True},"facts":[1,2]}; assert functional_output(value)=={"facts":[1,2]}
