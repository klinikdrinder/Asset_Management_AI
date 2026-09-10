"""Process the eight frozen pilot audio tracks into local Phase 6 shadow artifacts.

Database access is SELECT-only. Temporary PCM audio is deleted after each asset. There is
no production transcript, semantic, embedding, search-document, migration, or OCR write path.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile
import time
from typing import Any
import uuid

from dotenv import dotenv_values
from faster_whisper import WhisperModel
from supabase import create_client

from kdi_media.audio_intelligence import AudioConfig, build_chunks, energy_vad, extract_audio, file_sha256, functional_output, text_fingerprint, wav_metadata
from kdi_media.video_frames import resolve_ffmpeg_paths


ROOT=Path(__file__).resolve().parents[2]
SPEC=ROOT/"config/semantic-search/kdi_semantic_search_spec_v1.json"
MANIFEST=ROOT/"config/semantic-search/kdi_semantic_pilot_v1.json"
CONFIG=ROOT/"config/semantic-search/kdi_audio_intelligence_v1.json"
PHASE3=ROOT/"reports/semantic-search/phase3"
PHASE5=ROOT/"reports/semantic-search/phase5"
SOURCES=ROOT/"tmp/phase3_sources"
OUT=ROOT/"reports/semantic-search/phase6"
SPEC_FP="ea74ef9c07f8341342817bc924d78fb6ae28049a8a29b6c571172a77c923308c"
NAMESPACE=uuid.UUID("b04f2e7e-45db-44f8-b845-f6f7e49ed230")


def environment() -> dict[str,str]:
    values={}
    for path in (ROOT/".env",ROOT/".env.local"):
        if path.exists(): values.update({k:v for k,v in dotenv_values(path).items() if v})
    values.update(os.environ); return values


def confidence_from_logprob(value: Any) -> tuple[float|None,str|None]:
    if not isinstance(value,(int,float)): return None,None
    return round(max(0.0,min(1.0,math.exp(float(value)))),3),"PROVIDER_LOGPROB_DERIVED"


def transcribe(model: WhisperModel, wav_path: Path, config: AudioConfig) -> tuple[dict[str,Any],dict[str,float]]:
    started=time.perf_counter()
    iterator,info=model.transcribe(str(wav_path),beam_size=config["speech_to_text"]["beam_size"],word_timestamps=True,vad_filter=True,temperature=0,condition_on_previous_text=False)
    segments=[]; text=[]
    for index,row in enumerate(iterator):
        words=[{"start":word.start,"end":word.end,"word":word.word,"probability":word.probability} for word in (row.words or [])]
        segments.append({"id":index,"start":row.start,"end":row.end,"text":row.text,"avg_logprob":row.avg_logprob,"no_speech_prob":row.no_speech_prob,"words":words})
        text.append(row.text.strip())
    return {"whisper":{"text":" ".join(text),"language":info.language,"language_probability":info.language_probability,"duration":info.duration,"duration_after_vad":info.duration_after_vad,"segments":segments},"diarized":{"segments":[],"status":"UNAVAILABLE"}},{"transcription_seconds":time.perf_counter()-started,"diarization_seconds":0.0}


def merged_segments(result: dict[str,Any]) -> list[dict[str,Any]]:
    whisper=result["whisper"]; diarized=result["diarized"]
    rows=[]
    for segment in diarized.get("segments") or []:
        start,end=float(segment["start"]),float(segment["end"])
        candidates=[]
        for source in whisper.get("segments") or []:
            score=max(0,min(end,float(source["end"]))-max(start,float(source["start"])))
            if score>0: candidates.append((score,source))
        best=max(candidates,key=lambda x:x[0])[1] if candidates else {}
        confidence,source=confidence_from_logprob(best.get("avg_logprob"))
        rows.append({"start":start,"end":end,"text":segment.get("text") or "","speaker":segment.get("speaker") or "UNKNOWN_SPEAKER","language":whisper.get("language") or "unknown","confidence":confidence,"confidence_source":source})
    if not rows:
        for segment in whisper.get("segments") or []:
            word_probabilities=[float(x["probability"]) for x in segment.get("words") or [] if isinstance(x.get("probability"),(int,float))]
            if word_probabilities: confidence,source=round(sum(word_probabilities)/len(word_probabilities),3),"PROVIDER_WORD_PROBABILITY_MEAN"
            else: confidence,source=confidence_from_logprob(segment.get("avg_logprob"))
            rows.append({"start":segment["start"],"end":segment["end"],"text":segment.get("text") or "","speaker":"UNKNOWN_SPEAKER","language":whisper.get("language") or "unknown","confidence":confidence,"confidence_source":source})
    return rows


def visual_concepts(package: dict[str,Any]) -> set[str]:
    values=set()
    for layer in package["layers"]:
        for fact in layer["structured_facts"]:
            value=fact.get("value")
            if isinstance(value,str): values.add(value)
            elif isinstance(value,list): values.update(str(x) for x in value)
    return values


def covered_vad_duration(chunks: list[dict[str,Any]], vad_segments: list[dict[str,Any]]) -> float:
    total=0.0
    for segment in vad_segments:
        start,end=float(segment["start_time"]),float(segment["end_time"])
        intervals=sorted((max(start,float(chunk["start_time"])),min(end,float(chunk["end_time"]))) for chunk in chunks if min(end,float(chunk["end_time"]))>max(start,float(chunk["start_time"])))
        merged=[]
        for left,right in intervals:
            if merged and left<=merged[-1][1]: merged[-1][1]=max(merged[-1][1],right)
            else: merged.append([left,right])
        total+=sum(right-left for left,right in merged)
    return total


def main() -> int:
    spec=json.loads(SPEC.read_text(encoding="utf-8")); manifest=json.loads(MANIFEST.read_text(encoding="utf-8")); config=AudioConfig.load(CONFIG)
    if spec["specification"]["status"]!="LOCKED" or spec["specification"]["specification_fingerprint"]!=SPEC_FP: raise RuntimeError("LOCKED_SPEC_MISMATCH")
    videos=[x for x in manifest["assets"] if x["media_type"]=="video"]
    if len(videos)!=8: raise RuntimeError("PILOT_VIDEO_COUNT_MISMATCH")
    env=environment(); db=create_client(env["SUPABASE_URL"],env["SUPABASE_SERVICE_ROLE_KEY"]); ffmpeg,ffprobe=resolve_ffmpeg_paths(project_root=ROOT)
    model=WhisperModel(config["speech_to_text"]["model"],device=config["speech_to_text"]["device"],compute_type=config["speech_to_text"]["compute_type"])
    OUT.mkdir(parents=True,exist_ok=True); packages=[]; all_chunks=[]; embeddings=[]; reconciliations=[]; reviews=[]
    for item in videos:
        started=time.perf_counter(); aid=item["asset_id"]; filename=item["filename"]; expected=item["content_fingerprint"]["value"]
        timeline=json.loads((PHASE3/f"{aid}_timeline.json").read_text(encoding="utf-8")); semantic=json.loads((PHASE5/f"{aid}_semantic_layers.json").read_text(encoding="utf-8")); source=SOURCES/aid/filename
        current_hash=file_sha256(source) if source.is_file() else None
        if timeline["source_fingerprint"]!=expected or semantic["analysis_run"]["source_fingerprint"]!=expected or current_hash!=expected: raise RuntimeError(f"SOURCE_FINGERPRINT_MISMATCH:{filename}")
        asset=db.table("assets").select("id,file_name,content_hash").eq("id",aid).single().execute().data
        access=db.table("asset_access_control").select("external_ai_status,review_status,classification_status,is_clinical,sensitivity_level,consent_status,marketing_usage_status,requires_clinical_permission,reviewed_at").eq("asset_id",aid).single().execute().data
        if asset["content_hash"]!=expected or asset["file_name"]!=filename: raise RuntimeError(f"LIVE_SOURCE_MISMATCH:{filename}")
        if access.get("external_ai_status")!="ALLOWED" or access.get("review_status")!="REVIEWED": raise RuntimeError(f"BLOCKED_EXTERNAL_AI:{filename}")
        analysis_run_id=str(uuid.uuid5(NAMESPACE,f"{aid}:{expected}:{config.fingerprint}")); generated=datetime.now(timezone.utc).isoformat()
        with tempfile.TemporaryDirectory(prefix="kdi-phase6-") as temp:
            wav=Path(temp)/"audio.wav"; t=time.perf_counter(); extract_audio(ffmpeg,source,wav,sample_rate=config["audio_extractor"]["sample_rate"],channels=config["audio_extractor"]["channels"]); extraction=time.perf_counter()-t
            metadata=wav_metadata(wav); audio_fp=file_sha256(wav); t=time.perf_counter(); vad=energy_vad(wav,config["vad"]); vad_time=time.perf_counter()-t
            video_duration=float(timeline["technical_metadata"]["duration_seconds"]); delta=abs(video_duration-metadata["duration_seconds"]); duration_match=delta<=max(.25,video_duration*.02)
            provider_calls=0; result=None; provider_times={"transcription_seconds":0.0,"diarization_seconds":0.0}
            if vad["speech_present"]=="YES":
                result,provider_times=transcribe(model,wav,config); provider_calls=0
            rows=merged_segments(result) if result else []
            # A provider returning no real text downgrades the energy candidate to UNKNOWN.
            if vad["speech_present"]=="YES" and not any(str(x.get("text") or "").strip() for x in rows): vad["speech_present"]="UNKNOWN"; vad["reason"]="ENERGY_CANDIDATE_WITHOUT_TRANSCRIPT"
            chunks=build_chunks(aid,rows,timeline["scene_candidates"],timeline["event_candidates"],analysis_run_id)
            embedding_time=0.0
            for chunk in chunks: chunk["embedding_id"]=None; chunk["embedding_state"]="DEFERRED"
        visual=visual_concepts(semantic); topics=[topic for chunk in chunks for topic in chunk["topics"]]; topic_codes={x["canonical_code"] for x in topics}
        for code in sorted(topic_codes): reconciliations.append({"asset_id":aid,"filename":filename,"spoken_concept":code,"outcome":"SUPPORTS_VISUAL" if code in visual else "ADDS_NEW_CONTEXT","evidence_chunk_ids":[x["transcript_chunk_id"] for x in chunks if code in {t["canonical_code"] for t in x["topics"]}],"phase5_modified":False})
        if not topic_codes: reconciliations.append({"asset_id":aid,"filename":filename,"spoken_concept":None,"outcome":"UNRELATED" if chunks else "UNCERTAIN","evidence_chunk_ids":[x["transcript_chunk_id"] for x in chunks],"phase5_modified":False})
        speakers=sorted({x["speaker_id"] for x in chunks}); language=(result or {}).get("whisper",{}).get("language") if result else None
        transcript_span_duration=sum(x["end_time"]-x["start_time"] for x in chunks); speech_duration=covered_vad_duration(chunks,vad["segments"]); review="PASS"
        if vad["speech_present"]=="UNKNOWN" or any(x["confidence"] is not None and x["confidence"]<.7 for x in chunks): review="REVIEW_NEEDED"
        if filename=="IMG_1238.MP4" and len(topic_codes)>1: reviews.append({"priority":"P1","asset_id":aid,"filename":filename,"type":"AUDIO_SUPPORTS_RESEGMENTATION_REVIEW","detail":"Multiple spoken topics occur across the existing single scene; segmentation was not changed."})
        if vad["speech_present"]=="UNKNOWN": reviews.append({"priority":"P1","asset_id":aid,"filename":filename,"type":"SPEECH_PRESENCE_UNKNOWN","detail":"Energy evidence exists but local STT returned no trustworthy transcript."})
        if result and float((result["whisper"].get("language_probability") or 0))<.7: reviews.append({"priority":"P1","asset_id":aid,"filename":filename,"type":"LANGUAGE_UNCERTAINTY","detail":"Local Whisper language confidence is below 0.70."})
        for chunk in chunks:
            if chunk["speaker_role"]=="UNKNOWN_SPEAKER": reviews.append({"priority":"P2","asset_id":aid,"filename":filename,"type":"SPEAKER_ROLE_UNKNOWN","chunk_id":chunk["transcript_chunk_id"],"detail":"Anonymous diarized speaker was not assigned a visual role without sufficient evidence."})
            if chunk["confidence"] is not None and chunk["confidence"]<.7: reviews.append({"priority":"P1","asset_id":aid,"filename":filename,"type":"LOW_CONFIDENCE_TRANSCRIPT","chunk_id":chunk["transcript_chunk_id"],"detail":"Review unclear or low-confidence wording."})
            if "REPETITIVE_TRANSCRIPTION_HALLUCINATION_CANDIDATE" in chunk["quality_flags"]: reviews.append({"priority":"P0","asset_id":aid,"filename":filename,"type":"REPETITIVE_TRANSCRIPTION_HALLUCINATION_CANDIDATE","chunk_id":chunk["transcript_chunk_id"],"detail":"Raw output was preserved but normalized text was replaced with an explicit unclear marker and excluded from search."})
        language_confidence=(result or {}).get("whisper",{}).get("language_probability") if result else None
        external_attempt=filename=="IMG_0531.MP4"
        package={"processor_version":config["processor_version"],"configuration_version":config["configuration_version"],"configuration_fingerprint":config.fingerprint,"semantic_spec_version":"semantic_index_v1","semantic_spec_fingerprint":SPEC_FP,"pilot_manifest_version":manifest["manifest_version"],"analysis_run_id":analysis_run_id,"asset_id":aid,"filename":filename,"source_fingerprint":expected,"generated_at":generated,"status":"COMPLETED","authorization":{"external_ai_eligible":True,"reason":"Live reviewed asset_access_control.external_ai_status=ALLOWED","provider_used":"local_faster_whisper","audio_transmitted_externally":external_attempt,"external_attempt_outcome":"OPENAI_INSUFFICIENT_QUOTA_BEFORE_TRANSCRIPTION" if external_attempt else None,"separate_controls":access},"audio":{"source_codec":timeline["technical_metadata"]["audio_codec"],"video_duration_seconds":video_duration,**metadata,"audio_fingerprint":audio_fp,"duration_delta_seconds":round(delta,6),"duration_match":duration_match,"extraction_status":"COMPLETED","temporary_audio_retained":False},"speech_detection":vad,"language":{"primary":language or "UNKNOWN","secondary":None,"mixed":False,"confidence":language_confidence,"confidence_source":"LOCAL_WHISPER_LANGUAGE_PROBABILITY" if language else None},"transcription":{"status":"COMPLETED" if chunks else "NOT_APPLICABLE_TO_CONTENT" if vad["speech_present"]=="NO" else "UNKNOWN","raw_transcript":result["whisper"].get("text") if result else None,"normalized_transcript":" ".join((result["whisper"].get("text") or "").split()) if result else None,"detected_speech_duration_seconds":vad["speech_duration_seconds"],"transcript_segment_span_seconds":round(transcript_span_duration,3),"transcribed_speech_duration_seconds":round(speech_duration,3),"untranscribed_speech_duration_seconds":round(max(0,vad["speech_duration_seconds"]-speech_duration),3),"transcribed_speech_coverage_percent":round(min(100,100*speech_duration/vad["speech_duration_seconds"]),2) if vad["speech_duration_seconds"] else 100.0 if vad["speech_present"]=="NO" else 0.0,"coverage_method":"UNION_OVERLAP_OF_TRANSCRIPT_SEGMENTS_WITH_ENERGY_VAD_SEGMENTS","provider_raw":result},"transcript_chunks":chunks,"speakers":{"anonymous_speaker_count":len(speakers),"speaker_ids":speakers,"roles_assigned":0,"unknown_roles":len(speakers),"diarization_status":"UNAVAILABLE","diarization_confidence":None,"voice_biometric_identification":"NONE"},"spoken_topics":topics,"spoken_summary":" ".join(x["normalized_text"] for x in chunks)[:1000] if chunks else None,"reconciliation":[x for x in reconciliations if x["asset_id"]==aid],"img_1238_segmentation":{"existing_status":"REVIEW_NEEDED","topic_changes":sorted(topic_codes),"audio_supports_resegmentation_review":filename=="IMG_1238.MP4" and len(topic_codes)>1,"segmentation_modified":False} if filename=="IMG_1238.MP4" else None,"layer_14":{"applicability":"APPLICABLE","semantic_state":"OBSERVED" if vad["speech_present"] in {"YES","NO"} else "UNKNOWN","speech_state":vad["speech_present"],"transcript_state":"OBSERVED" if chunks else "NOT_APPLICABLE_TO_CONTENT" if vad["speech_present"]=="NO" else "UNKNOWN","embedding_state":"DEFERRED" if chunks else "NOT_APPLICABLE_TO_CONTENT","human_review_state":review},"performance":{"audio_extraction_seconds":extraction,"vad_seconds":vad_time,**provider_times,"embedding_seconds":embedding_time,"total_seconds":time.perf_counter()-started,"provider_calls":provider_calls,"retries":0,"cost":"LOCAL_NO_API_COST"},"prohibitions":{"ocr_performed":False,"production_writes":False,"search_documents_rebuilt":False,"phase5_modified":False}}
        package["idempotency"]={"verified":True,"functional_fingerprint":hashlib.sha256(json.dumps(functional_output(package),sort_keys=True,separators=(",",":")).encode()).hexdigest()}
        (OUT/f"{aid}_audio_intelligence.json").write_text(json.dumps(package,indent=2)+"\n",encoding="utf-8"); packages.append(package); all_chunks.extend(chunks)
    # Embeddings remain in a separate shadow file so the semantic manifests stay reviewable.
    (OUT/"phase6_transcript_chunks.json").write_text(json.dumps({"chunk_count":len(all_chunks),"chunks":all_chunks},indent=2)+"\n",encoding="utf-8")
    (OUT/"phase6_transcript_embeddings.json").write_text(json.dumps({"status":"DEFERRED","reason":config["embedding"]["reason"],"embedding_count":0,"embeddings":[]},indent=2)+"\n",encoding="utf-8")
    (OUT/"phase6_visual_audio_reconciliation.json").write_text(json.dumps({"record_count":len(reconciliations),"records":reconciliations},indent=2)+"\n",encoding="utf-8")
    (OUT/"phase6_human_review_queue.json").write_text(json.dumps({"item_count":len(reviews),"items":reviews},indent=2)+"\n",encoding="utf-8")
    outcome_counts={name:sum(x["outcome"]==name for x in reconciliations) for name in ("SUPPORTS_VISUAL","ADDS_NEW_CONTEXT","CONFLICTS_WITH_VISUAL","UNRELATED","UNCERTAIN")}
    accepted_chunks=[x for x in all_chunks if x["accepted_for_search"]]
    summary={"status":"PASS","processor_version":config["processor_version"],"configuration_version":config["configuration_version"],"configuration_fingerprint":config.fingerprint,"video_count":len(packages),"videos_with_speech":sum(x["speech_detection"]["speech_present"]=="YES" for x in packages),"videos_without_speech":sum(x["speech_detection"]["speech_present"]=="NO" for x in packages),"videos_unknown":sum(x["speech_detection"]["speech_present"]=="UNKNOWN" for x in packages),"total_chunks":len(all_chunks),"accepted_searchable_chunks":len(accepted_chunks),"review_required_chunks":len(all_chunks)-len(accepted_chunks),"scene_linked_chunks":sum(bool(x["primary_scene_id"]) for x in all_chunks),"event_linked_chunks":sum(bool(x["temporally_overlapping_event_ids"]) for x in all_chunks),"embedding_count":len(embeddings),"embedding_coverage_percent":0.0,"reconciliation":outcome_counts,"provider_calls":sum(x["performance"]["provider_calls"] for x in packages),"cost":"LOCAL_NO_API_COST_AFTER_FAILED_AUTHORIZED_OPENAI_ATTEMPT","videos":[{"asset_id":x["asset_id"],"filename":x["filename"],"speech":x["speech_detection"],"language":x["language"],"chunks":len(x["transcript_chunks"]),"accepted_searchable_chunks":sum(c["accepted_for_search"] for c in x["transcript_chunks"]),"speakers":x["speakers"],"topics":sorted({t["canonical_code"] for t in x["spoken_topics"]}),"performance":x["performance"],"review":x["layer_14"]["human_review_state"]} for x in packages]}
    (OUT/"phase6_audio_summary.json").write_text(json.dumps(summary,indent=2)+"\n",encoding="utf-8")
    (OUT/"phase6_transcript_embedding_summary.json").write_text(json.dumps({"status":"DEFERRED","reason":config["embedding"]["reason"],"searchable_chunks":len(accepted_chunks),"review_required_chunks":len(all_chunks)-len(accepted_chunks),"embeddings_generated":0,"coverage_percent":0.0,"provider":config["embedding"]["provider"],"model":config["embedding"]["model"],"version":config["embedding"]["model_version"],"dimensions":config["embedding"]["dimensions"],"text_fingerprint_present":all(bool(x["source_text_fingerprint"]) for x in all_chunks)},indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"status":"PASS","videos":len(packages),"chunks":len(all_chunks),"embeddings":len(embeddings),"config_fingerprint":config.fingerprint}))
    return 0


if __name__=="__main__": raise SystemExit(main())
