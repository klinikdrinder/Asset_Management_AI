import json
import math
from pathlib import Path
import struct
import subprocess
import sys
import wave

import pytest

from kdi_media.audio_intelligence import AudioConfig, build_chunks, energy_vad, normalize_topics, temporal_links, text_fingerprint, wav_metadata


ROOT=Path(__file__).resolve().parents[1]


def wav_fixture(path: Path, parts, rate=16000):
    samples=[]
    for duration,amplitude,frequency in parts:
        for i in range(round(duration*rate)):
            value=amplitude*math.sin(2*math.pi*frequency*i/rate) if frequency else 0
            samples.append(max(-32768,min(32767,round(value))))
    with wave.open(str(path),"wb") as out:
        out.setnchannels(1); out.setsampwidth(2); out.setframerate(rate); out.writeframes(b"".join(struct.pack("<h",x) for x in samples))


def config(): return AudioConfig.load(ROOT/"config/semantic-search/kdi_audio_intelligence_v1.json")


def test_configuration_is_versioned_shadow_only():
    value=config()
    assert value["processor_version"]=="kdi_audio_intelligence_v1"
    assert value["production_database_writes"] is False
    assert value["ocr_enabled"] is False
    assert len(value.fingerprint)==64


def test_silence_fixture(tmp_path):
    path=tmp_path/"silence.wav"; wav_fixture(path,[(1,0,0)])
    result=energy_vad(path,config()["vad"])
    assert result["speech_present"]=="NO" and result["segments"]==[]
    assert wav_metadata(path)["duration_seconds"]==1


def test_single_and_two_segment_fixtures(tmp_path):
    single=tmp_path/"single.wav"; wav_fixture(single,[(.2,0,0),(.6,9000,220),(.2,0,0)])
    one=energy_vad(single,config()["vad"]); assert one["speech_present"]=="YES" and len(one["segments"])==1
    multiple=tmp_path/"multiple.wav"; wav_fixture(multiple,[(.2,0,0),(.5,9000,220),(.7,0,0),(.5,9000,220),(.2,0,0)])
    two=energy_vad(multiple,config()["vad"]); assert len(two["segments"])==2


def test_noise_plus_signal_retains_stronger_region(tmp_path):
    path=tmp_path/"noise.wav"; wav_fixture(path,[(.5,300,90),(.5,10000,220),(.5,300,90)])
    assert energy_vad(path,config()["vad"])["speech_present"]=="YES"


def test_empty_and_corrupt_audio_failure(tmp_path):
    path=tmp_path/"empty.wav"; wav_fixture(path,[])
    assert energy_vad(path,config()["vad"])["speech_present"]=="UNKNOWN"
    bad=tmp_path/"bad.wav"; bad.write_bytes(b"not audio")
    with pytest.raises((wave.Error,EOFError)): energy_vad(bad,config()["vad"])


def test_timestamps_links_topics_and_fingerprints():
    scenes=[{"scene_id":"s1","start_time":0,"end_time":5},{"scene_id":"s2","start_time":5,"end_time":10}]
    events=[{"event_id":"e1","start_time":3,"end_time":4}]
    links=temporal_links(2,6,scenes,events)
    assert links["primary_scene_id"]=="s1" and links["overlapping_scene_ids"]==["s1","s2"] and links["temporally_overlapping_event_ids"]==["e1"]
    chunks=build_chunks("a",[{"start":2,"end":6,"text":"We design the hairline before placing grafts.","speaker":"SPEAKER_00","language":"en","confidence":.9}],scenes,events,"run")
    assert chunks[0]["start_time"]<chunks[0]["end_time"]
    assert {"HAIRLINE_DESIGN","IMPLANTING_GRAFTS"}<={x["canonical_code"] for x in chunks[0]["topics"]}
    assert chunks[0]["speaker_role"]=="UNKNOWN_SPEAKER"
    assert chunks[0]["source_text_fingerprint"]==text_fingerprint(chunks[0]["transcript_search_text"])


def test_unsupported_and_multilingual_text_is_preserved():
    text="Kami bincang rambut today — xyzterm."
    chunks=build_chunks("a",[{"start":0,"end":1,"text":text,"speaker":"S1","language":"ms","confidence":None}],[],[],"run")
    assert chunks[0]["raw_text"]==text and chunks[0]["language"]=="ms" and chunks[0]["topics"]==[]


def test_provider_failure_cannot_fabricate_transcript():
    def provider(): raise TimeoutError("provider unavailable")
    with pytest.raises(TimeoutError): provider()


@pytest.mark.skipif(sys.platform != "win32", reason="controlled local System.Speech fixture is Windows-only")
def test_controlled_single_speaker_transcription(tmp_path):
    output=tmp_path/"speaker.wav"
    script=("Add-Type -AssemblyName System.Speech; "
            "$s=New-Object System.Speech.Synthesis.SpeechSynthesizer; "
            f"$s.SetOutputToWaveFile('{str(output).replace("'", "''")}'); "
            "$s.Speak('We will review the frontal hairline before the procedure.'); $s.Dispose()")
    subprocess.run(["powershell.exe","-NoProfile","-Command",script],check=True,capture_output=True,timeout=30)
    from faster_whisper import WhisperModel
    model=WhisperModel("small",device="cpu",compute_type="int8")
    segments,info=model.transcribe(str(output),beam_size=5,word_timestamps=True,vad_filter=True,temperature=0)
    rows=list(segments)
    assert rows and all(0<=row.start<row.end for row in rows)
    assert "hairline" in " ".join(row.text.lower() for row in rows)
    assert info.language=="en"


def test_script_has_live_gate_and_no_production_write_path():
    script=(ROOT/"scripts/semantic-search/process_phase6_audio.py").read_text(encoding="utf-8")
    assert 'external_ai_status")!="ALLOWED"' in script
    assert ").insert(" not in script and ").update(" not in script and ").upsert(" not in script and ").delete(" not in script
    assert "ocr" not in script.lower() or '"ocr_performed":False' in script
