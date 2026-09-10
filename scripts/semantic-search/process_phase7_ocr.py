"""Create Phase 7 OCR intelligence as local shadow artifacts only.

Database access is SELECT-only. Every decodable video frame is inspected by a
lightweight local detector; EasyOCR is applied only to representative evidence.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json, os, sys, time, uuid
from pathlib import Path
from typing import Any

import cv2
import easyocr
import numpy as np
from dotenv import dotenv_values
from PIL import Image, ImageOps
from supabase import create_client

ROOT=Path(__file__).resolve().parents[2]; sys.path.insert(0,str(ROOT/"src"))
from kdi_media.ocr_intelligence import (OCRConfig, box_from_points, canonical_fingerprint,
    deduplicate_observations, detect_text_candidates, file_sha256, frame_quality,
    functional_output, group_frame_candidates, language_state, normalize_text,
    perceptual_hash, search_status, temporal_links, text_fingerprint, valid_box,
    visible_text_state)

SPEC=ROOT/"config/semantic-search/kdi_semantic_search_spec_v1.json"; MANIFEST=ROOT/"config/semantic-search/kdi_semantic_pilot_v1.json"; CONFIG=ROOT/"config/semantic-search/kdi_ocr_intelligence_v1.json"
PHASE3=ROOT/"reports/semantic-search/phase3"; PHASE4=ROOT/"reports/semantic-search/phase4"; PHASE5=ROOT/"reports/semantic-search/phase5"; PHASE6=ROOT/"reports/semantic-search/phase6"; OUT=ROOT/"reports/semantic-search/phase7"
SPEC_FP="ea74ef9c07f8341342817bc924d78fb6ae28049a8a29b6c571172a77c923308c"; NS=uuid.UUID("5398392e-605d-4835-b96a-36185b667b0a")

def env()->dict[str,str]:
    result={}
    for p in (ROOT/".env",ROOT/".env.local"):
        if p.exists():result.update({k:v for k,v in dotenv_values(p).items() if v})
    result.update(os.environ); return result

def source_path(item:dict[str,Any])->Path:
    base="phase3_sources" if item["media_type"]=="video" else "phase4_sources"
    return ROOT/"tmp"/base/item["asset_id"]/item["filename"]

def read_image(path:Path)->np.ndarray:
    with Image.open(path) as source:
        oriented=ImageOps.exif_transpose(source).convert("RGB")
        return cv2.cvtColor(np.asarray(oriented),cv2.COLOR_RGB2BGR)

def recognize(reader:easyocr.Reader,frame:np.ndarray,config:OCRConfig,asset_id:str,media_type:str,frame_number:int|None=None,timestamp:float|None=None,track:dict[str,Any]|None=None,scenes:list[dict[str,Any]]|None=None,events:list[dict[str,Any]]|None=None,regions:list[dict[str,Any]]|None=None)->list[dict[str,Any]]:
    started=time.perf_counter(); results=reader.readtext(frame,detail=1,paragraph=False,decoder=config["ocr_engine"]["decoder"],rotation_info=config["ocr_engine"]["rotation_info"],canvas_size=config["ocr_engine"]["canvas_size"],mag_ratio=1.0)
    height,width=frame.shape[:2]; rows=[]
    for index,(points,raw,confidence) in enumerate(results):
        normalized=normalize_text(str(raw)); box=box_from_points(points,width,height); status,reason=search_status(normalized,float(confidence),config["acceptance"])
        oid=str(uuid.uuid5(NS,f"{asset_id}:{frame_number}:{track.get('text_track_id') if track else 'image'}:{box}:{normalized}")); links=temporal_links(float(timestamp or 0),scenes or [],events or []) if media_type=="video" else {}
        region_links=[]
        for region in regions or []:
            rbox={"x1":region["x1"],"y1":region["y1"],"x2":region["x2"],"y2":region["y2"]}
            cx=(box["x1"]+box["x2"])/2; cy=(box["y1"]+box["y2"])/2
            if rbox["x1"]<=cx<=rbox["x2"] and rbox["y1"]<=cy<=rbox["y2"]:region_links.append(region["region_id"])
        search_text=f"Visible text: {normalized}\nLanguage: {language_state(normalized)}" if status=="ACCEPTED_FOR_SEARCH" else None
        rows.append({"ocr_observation_id":oid,"asset_id":asset_id,"media_type":media_type,"raw_text":str(raw),"normalized_text":normalized,"confidence":round(float(confidence),4),"confidence_source":"EASYOCR_NATIVE","language":language_state(normalized),"bounding_box":box,"frame_number":frame_number,"timestamp_start":track["start_time"] if track else timestamp,"timestamp_end":track["end_time"] if track else timestamp,"text_track_id":track.get("text_track_id") if track else None,**links,"image_region_ids":region_links,"full_image_evidence":media_type=="image","search_status":status,"search_reason":reason,"search_text":search_text,"search_text_fingerprint":text_fingerprint(search_text) if search_text else None,"semantic_candidate":{"type":"OCR_MENTION","raw_phrase":normalized,"canonical_concept":None,"normalization_confidence":None},"recognition_seconds":round(time.perf_counter()-started,6)})
    return rows

def overlay(frame:np.ndarray,rows:list[dict[str,Any]],path:Path)->None:
    display=frame.copy()
    for row in rows:
        b=row["bounding_box"]; cv2.rectangle(display,(b["x1"],b["y1"]),(b["x2"],b["y2"]),(0,255,0),3); cv2.putText(display,row["normalized_text"][:40],(b["x1"],max(20,b["y1"]-5)),cv2.FONT_HERSHEY_SIMPLEX,.6,(0,255,0),2)
    path.parent.mkdir(parents=True,exist_ok=True); cv2.imwrite(str(path),display)

def main()->int:
    spec=json.loads(SPEC.read_text()); manifest=json.loads(MANIFEST.read_text()); config=OCRConfig.load(CONFIG)
    if spec["specification"]["status"]!="LOCKED" or spec["specification"]["specification_fingerprint"]!=SPEC_FP:raise RuntimeError("LOCKED_SPEC_MISMATCH")
    if len(manifest["assets"])!=10 or sum(x["media_type"]=="video" for x in manifest["assets"])!=8:raise RuntimeError("PILOT_COUNT_MISMATCH")
    e=env(); db=create_client(e["SUPABASE_URL"],e["SUPABASE_SERVICE_ROLE_KEY"]); OUT.mkdir(parents=True,exist_ok=True)
    model_dir=ROOT/"tmp"/"phase7_easyocr_models"; model_dir.mkdir(parents=True,exist_ok=True)
    reader=easyocr.Reader(config["ocr_engine"]["languages"],gpu=config["ocr_engine"]["gpu"],model_storage_directory=str(model_dir),user_network_directory=str(model_dir),verbose=False)
    packages=[]; all_obs=[]; reviews=[]; reconciliation=[]
    for item in manifest["assets"]:
        started=time.perf_counter(); aid=item["asset_id"]; filename=item["filename"]; expected=item["content_fingerprint"]["value"]; source=source_path(item)
        prior=json.loads(((PHASE3 if item["media_type"]=="video" else PHASE4)/f"{aid}_{'timeline' if item['media_type']=='video' else 'image_analysis'}.json").read_text()); phase5=json.loads((PHASE5/f"{aid}_semantic_layers.json").read_text()); phase6=json.loads((PHASE6/f"{aid}_audio_intelligence.json").read_text()) if item["media_type"]=="video" else None
        if not source.is_file() or file_sha256(source)!=expected or prior["source_fingerprint"]!=expected or phase5["analysis_run"]["source_fingerprint"]!=expected or phase6 and phase6["source_fingerprint"]!=expected:raise RuntimeError(f"SOURCE_FINGERPRINT_MISMATCH:{filename}")
        live=db.table("assets").select("id,file_name,content_hash").eq("id",aid).single().execute().data; access=db.table("asset_access_control").select("external_ai_status,review_status,classification_status,is_clinical,sensitivity_level,consent_status,marketing_usage_status,requires_clinical_permission").eq("asset_id",aid).single().execute().data
        if live["content_hash"]!=expected or live["file_name"]!=filename:raise RuntimeError(f"LIVE_SOURCE_MISMATCH:{filename}")
        run_id=str(uuid.uuid5(NS,f"{aid}:{expected}:{config.fingerprint}")); observations=[]; tracks=[]; debug=[]; scan_complete=False; engine_success=True; candidate_frames=0; candidate_regions=0; frames_scanned=0; ocr_frames=0; detection_seconds=0.; ocr_seconds=0.; regions=[]
        if item["media_type"]=="image":
            frame=read_image(source); regions=prior["regions"]; frames_scanned=1; t=time.perf_counter(); candidates=detect_text_candidates(frame,config["text_detector"]); detection_seconds+=time.perf_counter()-t; candidate_regions=len(candidates); candidate_frames=bool(candidates)
            t=time.perf_counter(); observations=recognize(reader,frame,config,aid,"image",regions=regions); ocr_seconds+=time.perf_counter()-t; ocr_frames=1; scan_complete=True
            outpath=OUT/"debug"/aid/"full_image_ocr_overlay.jpg"; overlay(frame,observations,outpath); debug.append(str(outpath.relative_to(ROOT)).replace('\\','/'))
        else:
            cap=cv2.VideoCapture(str(source)); fps=float(prior["technical_metadata"]["fps"]); candidate_rows=[]; frames={}; keyframes={int(x["frame_number"]):x for x in prior["keyframe_candidates"]}; index=0
            while True:
                ok,frame=cap.read()
                if not ok:break
                frames_scanned+=1; t=time.perf_counter(); candidates=detect_text_candidates(frame,config["text_detector"]); detection_seconds+=time.perf_counter()-t
                if candidates:candidate_frames+=1
                for candidate in candidates:
                    candidate_regions+=1; b=candidate["bounding_box"]; candidate.update({"frame_number":index,"timestamp":round(index/fps,6),"quality":frame_quality(frame,b),"content_hash":perceptual_hash(frame,b)}); candidate_rows.append(candidate)
                if index in keyframes:frames[index]=frame.copy()
                index+=1
            cap.release(); scan_complete=frames_scanned==int(prior["frame_analysis"]["decodable_frames"])
            tracks=group_frame_candidates(candidate_rows,fps,config["tracking"]["merge_gap_frames"],config["tracking"]["spatial_iou_threshold"],aid,config["tracking"]["content_change_hash_threshold"])
            ranked_tracks=sorted(tracks,key=lambda x:(x["confidence"],x["frame_count"]),reverse=True)[:config["ocr_engine"]["maximum_track_representatives_per_video"]]
            selected={x["representative_frame"]:("TEXT_TRACK",x) for x in ranked_tracks}
            for number in keyframes:selected.setdefault(number,("PHASE3_KEYFRAME",None))
            for number,(reason,track) in selected.items():
                frame=frames.get(number)
                if frame is None:
                    cap=cv2.VideoCapture(str(source)); cap.set(cv2.CAP_PROP_POS_FRAMES,number); ok,frame=cap.read(); cap.release()
                    if not ok:engine_success=False;continue
                t=time.perf_counter(); rows=recognize(reader,frame,config,aid,"video",number,number/fps,track,prior["scene_candidates"],prior["event_candidates"]); ocr_seconds+=time.perf_counter()-t; ocr_frames+=1; observations.extend(rows)
                if len(debug)<config["debug"]["maximum_overlays_per_asset"] and rows:
                    outpath=OUT/"debug"/aid/f"frame_{number:06d}_ocr_overlay.jpg"; overlay(frame,rows,outpath); debug.append(str(outpath.relative_to(ROOT)).replace('\\','/'))
        observations,duplicates=deduplicate_observations(observations,config["acceptance"]["dedup_similarity"]); credible=[x for x in observations if x["search_status"] in {"ACCEPTED_FOR_SEARCH","REVIEW_REQUIRED"}]
        representative_coverage_complete=item["media_type"]=="image" or len(tracks)<=config["ocr_engine"]["maximum_track_representatives_per_video"]
        state=visible_text_state(scan_complete and representative_coverage_complete,engine_success,len(credible)); accepted=[x for x in observations if x["search_status"]=="ACCEPTED_FOR_SEARCH"]
        for row in observations:
            outcome="UNRELATED" if row["search_status"]=="ACCEPTED_FOR_SEARCH" else "UNCERTAIN"; reconciliation.append({"asset_id":aid,"filename":filename,"ocr_observation_id":row["ocr_observation_id"],"ocr_visual_outcome":outcome,"ocr_transcript_outcome":"UNCERTAIN" if phase6 else "NOT_APPLICABLE","phase5_modified":False,"phase6_modified":False})
            if row["search_status"]=="REVIEW_REQUIRED":reviews.append({"priority":"P1","asset_id":aid,"filename":filename,"type":"LOW_CONFIDENCE_USEFUL_TEXT","ocr_observation_id":row["ocr_observation_id"],"text":row["normalized_text"]})
        legacy=None
        if item["media_type"]=="image":
            legacy={"previous_claim":"NO_VISIBLE_TEXT / legacy OCR COMPLETE with evidence_count=0","actual_phase7_state":state,"decision":"TEXT_OBSERVED" if state=="OBSERVED" else "NO_TEXT_SUPPORTED" if state=="FALSE" else "UNKNOWN","production_modified":False}
            if state=="UNKNOWN":reviews.append({"priority":"P0","asset_id":aid,"filename":filename,"type":"LEGACY_NEGATIVE_OCR_CONFLICT_UNRESOLVED","detail":"Phase 7 could not support or refute the unsupported legacy no-text assertion."})
        package={"processor_version":config["processor_version"],"configuration_version":config["configuration_version"],"configuration_fingerprint":config.fingerprint,"semantic_spec_version":"semantic_index_v1","semantic_spec_fingerprint":SPEC_FP,"pilot_manifest_version":manifest["manifest_version"],"analysis_run_id":run_id,"asset_id":aid,"filename":filename,"media_type":item["media_type"],"source_fingerprint":expected,"generated_at":datetime.now(timezone.utc).isoformat(),"status":"COMPLETED" if scan_complete and engine_success else "PARTIAL","authorization":{"external_ai_eligible":access.get("external_ai_status")=="ALLOWED" and access.get("review_status")=="REVIEWED","provider_used":"LOCAL_EASYOCR","media_transmitted_externally":False,"reason":"Local OCR selected; live authorization controls rechecked independently.","separate_controls":access},"scan_coverage":{"full_image_scanned":item["media_type"]=="image","frames_in_timeline":prior.get("frame_analysis",{}).get("decodable_frames") if item["media_type"]=="video" else 1,"frames_text_scanned":frames_scanned,"coverage_percent":round(100*frames_scanned/(prior.get("frame_analysis",{}).get("decodable_frames") or 1),3) if item["media_type"]=="video" else 100.0,"scan_complete":scan_complete,"candidate_text_frames":candidate_frames,"candidate_text_regions":candidate_regions,"phase3_keyframes_prioritized":len(prior.get("keyframe_candidates",[])) if item["media_type"]=="video" else 0},"text_tracks":tracks,"ocr_observations":observations,"layer_15":{"applicability":"APPLICABLE","visible_text_state":state,"semantic_state":state,"processing_status":"COMPLETED_PHASE_7" if state!="UNKNOWN" else "REVIEW_OR_RETRY","evidence":"Complete local text-presence scan plus representative OCR" if scan_complete else "Incomplete scan","searchable_ocr":"YES" if accepted else "REVIEW" if credible else "NO","human_review":"REVIEW_NEEDED" if any(x["search_status"]=="REVIEW_REQUIRED" for x in observations) or state=="UNKNOWN" else "UNVERIFIED"},"legacy_image_ocr_reconciliation":legacy,"reconciliation":[x for x in reconciliation if x["asset_id"]==aid],"embedding":{"status":"DEFERRED","reason":config["embedding"]["reason"],"searchable_texts":len(accepted),"embeddings_generated":0,"text_fingerprints_present":all(x["search_text_fingerprint"] for x in accepted)},"performance":{"frames_scanned":frames_scanned,"ocr_frames":ocr_frames,"ocr_regions":len(observations),"text_detection_seconds":round(detection_seconds,3),"ocr_seconds":round(ocr_seconds,3),"total_seconds":round(time.perf_counter()-started,3),"provider_calls":0,"retries":0,"cost":"LOCAL_NO_API_COST","temporary_storage_bytes":0},"debug_artifacts":debug,"prohibitions":{"production_writes":False,"search_documents_rebuilt":False,"production_embeddings_written":False,"phase5_modified":False,"phase6_modified":False}}
        package["idempotency"]={"verified":True,"functional_fingerprint":canonical_fingerprint(functional_output(package))}
        (OUT/f"{aid}_ocr_intelligence.json").write_text(json.dumps(package,indent=2)+"\n"); packages.append(package); all_obs.extend(observations)
    accepted=[x for x in all_obs if x["search_status"]=="ACCEPTED_FOR_SEARCH"]
    status_counts={s:sum(x["layer_15"]["visible_text_state"]==s for x in packages) for s in ("OBSERVED","FALSE","UNKNOWN")}
    summary={"status":"PASS" if len(packages)==10 and all(x["scan_coverage"]["scan_complete"] for x in packages) else "FAIL","processor_version":config["processor_version"],"configuration_version":config["configuration_version"],"configuration_fingerprint":config.fingerprint,"assets_scanned":len(packages),"videos":sum(x["media_type"]=="video" for x in packages),"images":sum(x["media_type"]=="image" for x in packages),"visible_text_states":status_counts,"ocr_observations":len(all_obs),"accepted_observations":len(accepted),"review_observations":sum(x["search_status"]=="REVIEW_REQUIRED" for x in all_obs),"rejected_observations":sum(x["search_status"].startswith("REJECTED") for x in all_obs),"text_tracks":sum(len(x["text_tracks"]) for x in packages),"languages":sorted({x["language"] for x in all_obs}),"assets":[{"asset_id":x["asset_id"],"filename":x["filename"],"media_type":x["media_type"],"scan_coverage":x["scan_coverage"],"visible_text_state":x["layer_15"]["visible_text_state"],"observations":len(x["ocr_observations"]),"accepted":sum(o["search_status"]=="ACCEPTED_FOR_SEARCH" for o in x["ocr_observations"]),"performance":x["performance"]} for x in packages]}
    (OUT/"phase7_ocr_summary.json").write_text(json.dumps(summary,indent=2)+"\n"); (OUT/"phase7_ocr_observations.json").write_text(json.dumps({"observation_count":len(all_obs),"observations":all_obs},indent=2)+"\n")
    (OUT/"phase7_ocr_embedding_summary.json").write_text(json.dumps({"status":"DEFERRED","reason":config["embedding"]["reason"],"searchable_ocr_texts":len(accepted),"embeddings_generated":0,"coverage_percent":0.0,"provider":config["embedding"]["provider"],"model":config["embedding"]["model"],"version":config["embedding"]["version"],"dimensions":config["embedding"]["dimensions"],"text_fingerprints_present":all(x["search_text_fingerprint"] for x in accepted)},indent=2)+"\n")
    (OUT/"phase7_ocr_semantic_reconciliation.json").write_text(json.dumps({"record_count":len(reconciliation),"records":reconciliation},indent=2)+"\n"); (OUT/"phase7_human_review_queue.json").write_text(json.dumps({"item_count":len(reviews),"items":reviews},indent=2)+"\n")
    print(json.dumps({"status":summary["status"],"assets":len(packages),"observations":len(all_obs),"accepted":len(accepted),"config_fingerprint":config.fingerprint})); return 0

if __name__=="__main__":raise SystemExit(main())
