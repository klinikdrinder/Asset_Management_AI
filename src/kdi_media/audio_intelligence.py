"""Versioned Phase 6 audio intelligence primitives; no database write path."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import subprocess
import uuid
import wave
from typing import Any, Callable


NAMESPACE = uuid.UUID("4c43e8ca-84c0-4ab4-af5a-f23651b0f354")


def canonical_fingerprint(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""): digest.update(block)
    return digest.hexdigest()


def text_fingerprint(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class AudioConfig:
    values: dict[str, Any]
    fingerprint: str

    @classmethod
    def load(cls, path: Path) -> "AudioConfig":
        values = json.loads(path.read_text(encoding="utf-8"))
        if values.get("processor_version") != "kdi_audio_intelligence_v1": raise ValueError("AUDIO_PROCESSOR_VERSION_MISMATCH")
        if not values.get("shadow_mode") or values.get("production_database_writes"): raise ValueError("AUDIO_SHADOW_SAFETY_MISMATCH")
        return cls(values, canonical_fingerprint(values))

    def __getitem__(self, key: str) -> Any: return self.values[key]


def extract_audio(ffmpeg: str, source: Path, output: Path, *, sample_rate: int, channels: int) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run([ffmpeg, "-v", "error", "-i", str(source), "-vn", "-ac", str(channels), "-ar", str(sample_rate), "-c:a", "pcm_s16le", "-y", str(output)], capture_output=True, timeout=120)
    if result.returncode != 0 or not output.is_file(): raise RuntimeError("AUDIO_EXTRACTION_FAILED:" + result.stderr.decode("utf-8", "replace")[:300])


def wav_metadata(path: Path) -> dict[str, Any]:
    with wave.open(str(path), "rb") as wav:
        frames, rate, channels, width = wav.getnframes(), wav.getframerate(), wav.getnchannels(), wav.getsampwidth()
    return {"duration_seconds": frames / rate if rate else 0.0, "sample_rate": rate, "channels": channels, "sample_width_bytes": width, "frame_count": frames}


def energy_vad(path: Path, config: dict[str, Any]) -> dict[str, Any]:
    with wave.open(str(path), "rb") as wav:
        rate, width, channels = wav.getframerate(), wav.getsampwidth(), wav.getnchannels()
        if width != 2 or channels != 1: raise ValueError("VAD_REQUIRES_MONO_PCM16")
        window = max(1, round(rate * config["window_ms"] / 1000))
        db_values=[]
        while True:
            raw=wav.readframes(window)
            if not raw: break
            count=len(raw)//2
            values=[int.from_bytes(raw[i:i+2],"little",signed=True) for i in range(0,count*2,2)]
            rms=math.sqrt(sum(v*v for v in values)/len(values)) if values else 0
            db_values.append(20*math.log10(max(rms,1)/32768))
    if not db_values: return {"speech_present":"UNKNOWN","segments":[],"speech_duration_seconds":0.0,"speech_ratio":0.0,"confidence":0.0,"reason":"EMPTY_AUDIO"}
    ordered=sorted(db_values); noise=ordered[max(0,int(len(ordered)*.2)-1)]
    threshold=max(float(config["absolute_floor_dbfs"]), noise+float(config["noise_margin_db"]))
    active=[value>=threshold for value in db_values]
    minimum=max(1,math.ceil(config["minimum_speech_ms"]/config["window_ms"])); merge=max(0,round(config["merge_gap_ms"]/config["window_ms"]))
    runs=[]; start=None
    for i,on in enumerate(active+[False]):
        if on and start is None: start=i
        elif not on and start is not None:
            if i-start>=minimum: runs.append([start,i])
            start=None
    merged=[]
    for run in runs:
        if merged and run[0]-merged[-1][1]<=merge: merged[-1][1]=run[1]
        else: merged.append(run)
    step=config["window_ms"]/1000
    segments=[{"start_time":round(a*step,3),"end_time":round(min(b*step,len(db_values)*step),3),"state":"SPEECH_CANDIDATE"} for a,b in merged]
    duration=sum(x["end_time"]-x["start_time"] for x in segments); total=len(db_values)*step; ratio=duration/total if total else 0
    present="YES" if ratio>=config["speech_candidate_ratio_floor"] else "NO"
    confidence=min(.99,max(.6,(max(db_values)-threshold)/30+.65)) if present=="YES" else .9
    return {"speech_present":present,"segments":segments,"speech_duration_seconds":round(duration,3),"speech_ratio":round(ratio,6),"confidence":round(confidence,3),"confidence_source":"HEURISTIC","threshold_dbfs":round(threshold,2),"noise_floor_dbfs":round(noise,2),"peak_dbfs":round(max(db_values),2)}


def overlap(start: float, end: float, other_start: float, other_end: float) -> float:
    return max(0.0, min(end, other_end) - max(start, other_start))


def temporal_links(start: float, end: float, scenes: list[dict[str, Any]], events: list[dict[str, Any]]) -> dict[str, Any]:
    scene_scores=[(overlap(start,end,float(s["start_time"]),float(s["end_time"])),s["scene_id"]) for s in scenes]
    scene_ids=[sid for score,sid in scene_scores if score>0]; primary=max(scene_scores,default=(0,None))[1] if scene_ids else None
    event_ids=[e["event_id"] for e in events if overlap(start,end,float(e["start_time"]),float(e["end_time"]))>0]
    return {"primary_scene_id":primary,"overlapping_scene_ids":scene_ids,"temporally_overlapping_event_ids":event_ids,"event_relationship":"TEMPORAL_OVERLAP_ONLY" if event_ids else None}


TOPICS = {
    "HAIRLINE_DESIGN": ("hairline design", "design the hairline", "draw the hairline"),
    "FRONTAL_HAIRLINE": ("frontal hairline", "front hairline"),
    "HAIR_TRANSPLANT_FUE": ("fue", "follicular unit extraction"),
    "GRAFTS": ("graft", "grafts"),
    "IMPLANTING_GRAFTS": ("placing grafts", "implanting grafts", "implant grafts"),
    "DONOR_REGION": ("donor area", "donor region"),
    "RECIPIENT_REGION": ("recipient area", "recipient region"),
    "AFTERCARE": ("aftercare", "after care"),
    "CONSULTATION": ("consultation", "consult"),
    "MEDICATION": ("medication", "medicine", "tablet", "antibiotic"),
    "PRP": ("prp", "platelet rich plasma"),
    "NO_SHAVING": ("no shaving", "without shaving", "unshaven")
}


def normalize_topics(text: str) -> list[dict[str, Any]]:
    lowered=" ".join(text.lower().split()); found=[]
    for code,phrases in TOPICS.items():
        for phrase in phrases:
            if phrase in lowered:
                found.append({"original_phrase":phrase,"canonical_code":code,"normalization_confidence":.95,"evidence_type":"TRANSCRIPT"}); break
    return found


def normalize_text(text: str) -> str: return " ".join(text.replace("\u0000", " ").split())


def repetition_hallucination_candidate(text: str) -> bool:
    tokens=[token.strip(".,!?;:\"'()[]").lower() for token in text.split()]
    tokens=[token for token in tokens if token]
    if len(tokens)<20: return False
    counts={token:tokens.count(token) for token in set(tokens)}
    return max(counts.values(),default=0)/len(tokens)>.6


def build_chunks(asset_id: str, segments: list[dict[str, Any]], scenes: list[dict[str, Any]], events: list[dict[str, Any]], analysis_run_id: str, topics_fn: Callable[[str],list[dict[str,Any]]]=normalize_topics) -> list[dict[str, Any]]:
    chunks=[]
    for index,segment in enumerate(segments):
        raw=str(segment.get("text") or "").strip()
        if not raw: continue
        start,end=max(0.0,float(segment["start"])),max(0.0,float(segment["end"]))
        if end<=start: continue
        normalized=normalize_text(raw); speaker=str(segment.get("speaker") or "UNKNOWN_SPEAKER"); flags=[]
        confidence=segment.get("confidence")
        if repetition_hallucination_candidate(normalized):
            flags.append("REPETITIVE_TRANSCRIPTION_HALLUCINATION_CANDIDATE")
            normalized="[unclear repetitive speech-like audio]"; confidence=min(float(confidence or 1),.2)
        links=temporal_links(start,end,scenes,events)
        chunk_id=str(uuid.uuid5(NAMESPACE,f"{asset_id}:{start:.3f}:{end:.3f}:{speaker}:{normalized}"))
        topics=topics_fn(normalized)
        search_text=f"Speaker role: UNKNOWN_SPEAKER\nLanguage: {segment.get('language') or 'unknown'}\nTranscript: {normalized}"
        if topics: search_text += "\nTopics: " + ", ".join(x["canonical_code"] for x in topics)
        chunks.append({"transcript_chunk_id":chunk_id,"asset_id":asset_id,"start_time":round(start,3),"end_time":round(end,3),"raw_text":raw,"normalized_text":normalized,"language":segment.get("language") or "unknown","confidence":confidence,"confidence_source":segment.get("confidence_source"),"quality_flags":flags,"accepted_for_search":not flags and confidence is not None and confidence>=.6,"speaker_id":speaker,"speaker_role":"UNKNOWN_SPEAKER","speaker_role_confidence":None,"analysis_run_id":analysis_run_id,**links,"topics":topics,"transcript_search_text":search_text,"source_text_fingerprint":text_fingerprint(search_text)})
    return chunks


def functional_output(value: dict[str, Any]) -> dict[str, Any]:
    ignored={"generated_at","started_at","completed_at","performance","idempotency"}
    return {k:v for k,v in value.items() if k not in ignored}
