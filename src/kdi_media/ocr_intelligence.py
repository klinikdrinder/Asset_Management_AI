"""Local Phase 7 OCR primitives with deterministic tracking and provenance."""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
import hashlib
import json
from pathlib import Path
import re
import unicodedata
import uuid
from typing import Any

import cv2
import numpy as np


NAMESPACE=uuid.UUID("67bc521d-20bb-4b57-bff8-4018c9e330ed")


def canonical_fingerprint(value: Any) -> str:
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()


def file_sha256(path: Path) -> str:
    digest=hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda:handle.read(1024*1024),b""): digest.update(block)
    return digest.hexdigest()


def text_fingerprint(text: str) -> str: return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class OCRConfig:
    values: dict[str,Any]
    fingerprint: str

    @classmethod
    def load(cls,path:Path)->"OCRConfig":
        values=json.loads(path.read_text(encoding="utf-8"))
        if values.get("processor_version")!="kdi_ocr_intelligence_v1": raise ValueError("OCR_VERSION_MISMATCH")
        if not values.get("shadow_mode") or values.get("production_database_writes") or values.get("external_media_transmission"): raise ValueError("OCR_SHADOW_SAFETY_MISMATCH")
        return cls(values,canonical_fingerprint(values))

    def __getitem__(self,key:str)->Any:return self.values[key]


def valid_box(box:dict[str,Any],width:int,height:int)->bool:
    return 0<=box["x1"]<box["x2"]<=width and 0<=box["y1"]<box["y2"]<=height and all(0<=box[key]<=1 for key in ("nx1","ny1","nx2","ny2"))


def box_from_points(points:Any,width:int,height:int)->dict[str,Any]:
    values=np.asarray(points,dtype=float).reshape(-1,2); x1=max(0,int(np.floor(values[:,0].min()))); y1=max(0,int(np.floor(values[:,1].min()))); x2=min(width,int(np.ceil(values[:,0].max()))); y2=min(height,int(np.ceil(values[:,1].max())))
    x2=max(x1+1,x2); y2=max(y1+1,y2)
    return {"x1":x1,"y1":y1,"x2":x2,"y2":y2,"nx1":round(x1/width,6),"ny1":round(y1/height,6),"nx2":round(x2/width,6),"ny2":round(y2/height,6)}


def iou(a:dict[str,Any],b:dict[str,Any])->float:
    left=max(a["x1"],b["x1"]); top=max(a["y1"],b["y1"]); right=min(a["x2"],b["x2"]); bottom=min(a["y2"],b["y2"]); intersection=max(0,right-left)*max(0,bottom-top)
    area_a=(a["x2"]-a["x1"])*(a["y2"]-a["y1"]); area_b=(b["x2"]-b["x1"])*(b["y2"]-b["y1"])
    return intersection/(area_a+area_b-intersection) if area_a+area_b-intersection else 0


def detect_text_candidates(frame:np.ndarray,config:dict[str,Any])->list[dict[str,Any]]:
    height,width=frame.shape[:2]; scale=min(1.0,float(config["scan_width"])/width); small=cv2.resize(frame,(max(1,round(width*scale)),max(1,round(height*scale)))) if scale<1 else frame
    gray=cv2.cvtColor(small,cv2.COLOR_BGR2GRAY); kernel=cv2.getStructuringElement(cv2.MORPH_RECT,(15,5)); blackhat=cv2.morphologyEx(gray,cv2.MORPH_BLACKHAT,kernel); tophat=cv2.morphologyEx(gray,cv2.MORPH_TOPHAT,kernel)
    gradient=np.maximum(np.absolute(cv2.Sobel(blackhat,cv2.CV_32F,1,0,ksize=3)),np.absolute(cv2.Sobel(tophat,cv2.CV_32F,1,0,ksize=3))); maximum=float(gradient.max()); normalized=np.uint8(255*gradient/maximum) if maximum>0 else np.zeros_like(gray)
    normalized=cv2.morphologyEx(normalized,cv2.MORPH_CLOSE,cv2.getStructuringElement(cv2.MORPH_RECT,(13,3))); threshold=cv2.threshold(normalized,0,255,cv2.THRESH_BINARY|cv2.THRESH_OTSU)[1]; threshold=cv2.dilate(threshold,np.ones((2,2),np.uint8),iterations=1)
    contours,_=cv2.findContours(threshold,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE); output=[]; frame_area=small.shape[0]*small.shape[1]
    for contour in contours:
        x,y,w,h=cv2.boundingRect(contour); ratio=w/h if h else 0; area_ratio=w*h/frame_area
        if area_ratio<config["minimum_region_area_ratio"] or area_ratio>config["maximum_region_area_ratio"] or ratio<config["minimum_aspect_ratio"] or w<10 or h<5: continue
        density=cv2.countNonZero(threshold[y:y+h,x:x+w])/(w*h); score=min(1.0,.45*density+.35*min(1,ratio/5)+.2*min(1,area_ratio/.03))
        if score<config["candidate_score_threshold"]: continue
        box=box_from_points([[x/scale,y/scale],[(x+w)/scale,(y+h)/scale]],width,height); output.append({"bounding_box":box,"candidate_confidence":round(score,3)})
    return sorted(output,key=lambda x:x["candidate_confidence"],reverse=True)[:12]


def perceptual_hash(frame:np.ndarray,box:dict[str,Any]|None=None)->str:
    region=frame if box is None else frame[box["y1"]:box["y2"],box["x1"]:box["x2"]]
    if region.size==0:return "0"*16
    gray=cv2.cvtColor(region,cv2.COLOR_BGR2GRAY); resized=cv2.resize(gray,(9,8),interpolation=cv2.INTER_AREA); bits=(resized[:,1:]>resized[:,:-1]).flatten()
    return f"{int(''.join('1' if bit else '0' for bit in bits),2):016x}"


def hash_distance(left:str,right:str)->int:return (int(left,16)^int(right,16)).bit_count()


def frame_quality(frame:np.ndarray,box:dict[str,Any]|None=None)->float:
    region=frame if box is None else frame[box["y1"]:box["y2"],box["x1"]:box["x2"]]
    if region.size==0:return 0
    gray=cv2.cvtColor(region,cv2.COLOR_BGR2GRAY); sharp=min(1,float(cv2.Laplacian(gray,cv2.CV_64F).var())/800); contrast=min(1,float(gray.std())/64)
    return round(.65*sharp+.35*contrast,4)


def group_frame_candidates(rows:list[dict[str,Any]],fps:float,merge_gap_frames:int,iou_threshold:float,asset_id:str,content_change_hash_threshold:int=18)->list[dict[str,Any]]:
    tracks=[]
    for row in sorted(rows,key=lambda x:x["frame_number"]):
        chosen=None
        for track in reversed(tracks):
            if row["frame_number"]-track["end_frame"]>merge_gap_frames: break
            content_changed=bool(row.get("content_hash") and track.get("last_hash") and hash_distance(row["content_hash"],track["last_hash"])>content_change_hash_threshold)
            if iou(row["bounding_box"],track["last_box"])>=iou_threshold and not content_changed: chosen=track; break
        if chosen is None:
            chosen={"members":[],"start_frame":row["frame_number"],"end_frame":row["frame_number"],"last_box":row["bounding_box"],"last_hash":row.get("content_hash")}; tracks.append(chosen)
        chosen["members"].append(row); chosen["end_frame"]=row["frame_number"]; chosen["last_box"]=row["bounding_box"]; chosen["last_hash"]=row.get("content_hash")
    output=[]
    for index,track in enumerate(tracks):
        best=max(track["members"],key=lambda x:(x.get("quality",0),x["candidate_confidence"])); track_id=str(uuid.uuid5(NAMESPACE,f"{asset_id}:track:{track['start_frame']}:{track['end_frame']}:{best['bounding_box']}"))
        output.append({"text_track_id":track_id,"track_index":index,"start_frame":track["start_frame"],"end_frame":track["end_frame"],"start_time":round(track["start_frame"]/fps,3),"end_time":round(track["end_frame"]/fps,3),"frame_count":len({x["frame_number"] for x in track["members"]}),"representative_frame":best["frame_number"],"best_quality_frame":best["frame_number"],"bounding_box":best["bounding_box"],"confidence":round(max(x["candidate_confidence"] for x in track["members"]),3),"recognized_text_state":"PENDING"})
    return output


def normalize_text(text:str)->str: return " ".join(unicodedata.normalize("NFKC",text).split())


def gibberish(text:str)->bool:
    compact="".join(text.split())
    if len(compact)<2:return True
    if len(compact)<=3 and compact.upper() not in {"FUE","PRP","RM"}:return True
    alnum=sum(ch.isalnum() for ch in compact)/len(compact)
    if alnum<.55:return True
    if re.fullmatch(r"(.)\1{4,}",compact,re.I):return True
    unique=len(set(compact.lower()))/len(compact)
    return len(compact)>8 and unique<.12


def language_state(text:str)->str:
    if len(text.strip())<=3:return "UNKNOWN_OR_TOKEN"
    if any("\u0b80"<=ch<="\u0bff" for ch in text):return "TAMIL"
    if any("\u4e00"<=ch<="\u9fff" for ch in text):return "CHINESE"
    if any(ch.isalpha() and ord(ch)<128 for ch in text):return "ENGLISH_OR_MALAY"
    return "UNKNOWN"


def visible_text_state(scan_complete:bool,engine_success:bool,credible_observations:int)->str:
    if credible_observations>0:return "OBSERVED"
    if scan_complete and engine_success:return "FALSE"
    return "UNKNOWN"


def search_status(text:str,confidence:float,acceptance:dict[str,Any])->tuple[str,str]:
    if gibberish(text):return "REJECTED_GIBBERISH","Character distribution or useful-length check failed"
    if text and not text[0].isalnum() and confidence>=acceptance["review_confidence"]:return "REVIEW_REQUIRED","Leading symbol makes normalization uncertain despite OCR confidence"
    if confidence>=acceptance["accepted_confidence"]:return "ACCEPTED_FOR_SEARCH",f"OCR confidence {confidence:.3f} meets acceptance threshold"
    if confidence>=acceptance["review_confidence"]:return "REVIEW_REQUIRED",f"OCR confidence {confidence:.3f} requires review"
    return "REJECTED_LOW_CONFIDENCE",f"OCR confidence {confidence:.3f} below review threshold"


def deduplicate_observations(rows:list[dict[str,Any]],threshold:float)->tuple[list[dict[str,Any]],int]:
    kept=[]; duplicates=0
    for row in sorted(rows,key=lambda x:(x.get("timestamp_start") or 0,-x["confidence"])):
        match=None
        for prior in kept:
            same_track=row.get("text_track_id") and row.get("text_track_id")==prior.get("text_track_id")
            similarity=SequenceMatcher(None,row["normalized_text"].lower(),prior["normalized_text"].lower()).ratio()
            if similarity>=threshold and (same_track or row.get("media_type")=="image" and prior.get("media_type")=="image"): match=prior; break
        if match:
            duplicates+=1; match["duplicate_evidence_count"]=match.get("duplicate_evidence_count",1)+1
            if row.get("timestamp_end") is not None: match["timestamp_end"]=max(match.get("timestamp_end") or 0,row["timestamp_end"])
        else: kept.append(row)
    return kept,duplicates


def temporal_links(timestamp:float,scenes:list[dict[str,Any]],events:list[dict[str,Any]])->dict[str,Any]:
    scene_ids=[s["scene_id"] for s in scenes if float(s["start_time"])<=timestamp<=float(s["end_time"])]; event_ids=[e["event_id"] for e in events if float(e["start_time"])<=timestamp<=float(e["end_time"])]
    return {"primary_scene_id":scene_ids[0] if scene_ids else None,"overlapping_scene_ids":scene_ids,"temporally_overlapping_event_ids":event_ids,"event_relationship":"TEMPORAL_OVERLAP_ONLY" if event_ids else None}


def functional_output(value:dict[str,Any])->dict[str,Any]:
    return {key:item for key,item in value.items() if key not in {"generated_at","performance","idempotency"}}
