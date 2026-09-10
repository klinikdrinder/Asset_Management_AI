import json
from pathlib import Path


ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"reports/semantic-search/phase6"


def load(path): return json.loads(path.read_text(encoding="utf-8"))


def packages():
    manifest=load(ROOT/"config/semantic-search/kdi_semantic_pilot_v1.json")
    videos=[x for x in manifest["assets"] if x["media_type"]=="video"]
    return videos,[load(OUT/f"{x['asset_id']}_audio_intelligence.json") for x in videos]


def test_eight_outputs_and_fingerprint_integrity():
    videos,values=packages(); assert len(videos)==len(values)==8
    for item,value in zip(videos,values):
        timeline=load(ROOT/f"reports/semantic-search/phase3/{item['asset_id']}_timeline.json")
        phase5=load(ROOT/f"reports/semantic-search/phase5/{item['asset_id']}_semantic_layers.json")
        expected=item["content_fingerprint"]["value"]
        assert value["source_fingerprint"]==timeline["source_fingerprint"]==phase5["analysis_run"]["source_fingerprint"]==expected
        assert value["authorization"]["external_ai_eligible"] is True
        assert value["audio"]["temporary_audio_retained"] is False
        assert value["idempotency"]["verified"] is True


def test_chunk_and_embedding_integrity():
    _,values=packages(); chunks=load(OUT/"phase6_transcript_chunks.json")["chunks"]; embedding_data=load(OUT/"phase6_transcript_embeddings.json"); embeddings=embedding_data["embeddings"]
    assert embedding_data["status"]=="DEFERRED" and embeddings==[]
    by_id={x["transcript_chunk_id"]:x for x in chunks}
    assert all(chunk["source_text_fingerprint"] for chunk in chunks)
    for value in values:
        timeline=load(ROOT/f"reports/semantic-search/phase3/{value['asset_id']}_timeline.json")
        scene_ids={x["scene_id"] for x in timeline["scene_candidates"]}; event_ids={x["event_id"] for x in timeline["event_candidates"]}
        last=-1
        for chunk in value["transcript_chunks"]:
            assert 0<=chunk["start_time"]<chunk["end_time"]<=value["audio"]["video_duration_seconds"]+.3
            assert chunk["start_time"]>=last; last=chunk["start_time"]
            if chunk["primary_scene_id"]: assert chunk["primary_scene_id"] in scene_ids
            assert set(chunk["temporally_overlapping_event_ids"])<=event_ids
            assert chunk["speaker_role"]=="UNKNOWN_SPEAKER"


def test_no_forbidden_phase_actions():
    _,values=packages()
    for value in values:
        assert value["prohibitions"]=={"ocr_performed":False,"production_writes":False,"search_documents_rebuilt":False,"phase5_modified":False}
        assert value["speakers"]["voice_biometric_identification"]=="NONE"
    summary=load(OUT/"phase6_audio_summary.json")
    assert summary["video_count"]==8
    embedding=load(OUT/"phase6_transcript_embedding_summary.json")
    assert embedding["status"]=="DEFERRED" and embedding["coverage_percent"]==0
    assert embedding["text_fingerprint_present"] is True
