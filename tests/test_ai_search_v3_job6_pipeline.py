from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PREP = (ROOT / "scripts" / "prepare_ai_search_v3_job6_media.py").read_text(encoding="utf-8")
WRITE = (ROOT / "scripts" / "run_ai_search_v3_job6_indexing.py").read_text(encoding="utf-8")


def test_exact_manifest_boundary_and_gate_are_mandatory():
    assert 'manifest.get("pilot_size") != 10' in PREP
    assert 'can_asset_use_external_ai' in PREP
    assert 'set(OBS) != set(prep)' in WRITE
    assert 'AUTHORIZATION_REVOKED' in WRITE


def test_no_ollama_or_new_vector_database():
    combined = (PREP + WRITE).lower()
    for forbidden in ("pinecone", "weaviate", "qdrant", "chroma", "milvus", "ollama"):
        assert forbidden not in combined


def test_pgvector_dimensions_and_existing_visual_vectors_are_preserved():
    assert 'asset_visual_embeddings' in WRITE
    assert '"embedding_dimensions":512' in WRITE
    assert 'scene_embeddings' in WRITE
    assert 'keyframe_embeddings' in WRITE
    assert '.delete()' not in WRITE


def test_restart_safety_uses_deterministic_ids_and_upserts():
    assert "uuid.uuid5" in WRITE
    assert ".upsert(" in WRITE
    assert "truncate" not in WRITE.lower()


def test_still_images_do_not_get_fake_scenes():
    assert 'if not spec.get("image")' in WRITE
    assert '"DSC03753.JPG"' not in WRITE  # observations are keyed by UUID, not filename guesses

