from pathlib import Path

ROOT = Path(__file__).parents[1]
FILES = sorted((ROOT / "supabase/migrations").glob("202608190620*_ai_search_v3_job4_*.sql"))


def sql() -> str:
    return "\n".join(p.read_text(encoding="utf-8").lower() for p in FILES)


def test_three_job4_migrations_are_additive() -> None:
    assert len(FILES) == 3
    text = sql()
    for forbidden in ("drop table", "drop column", "delete from", "truncate table", "hybrid_search_assets"):
        assert forbidden not in text
    assert "using hnsw" not in text and "using ivfflat" not in text


def test_mixed_dimensions_and_embedding_integrity() -> None:
    text = sql()
    for table in ("scene_embeddings", "keyframe_embeddings", "transcript_embeddings"):
        assert f"create table public.{table}" in text
        assert f"alter table public.{table} enable row level security" in text
    assert "embedding public.vector not null" in text
    assert "vector_dims(embedding) = embedding_dimensions" in text
    assert "where is_active" in text


def test_search_documents_conversation_and_security_contract() -> None:
    text = sql()
    assert text.count("using gin(search_vector)") == 2
    assert "requested_count integer not null default 5" in text
    assert "unique(search_query_id,rank)" in text
    assert "unique(search_query_id,asset_id)" in text
    assert "from public,anon,authenticated" in text
    assert "security invoker set search_path=''" in text or "security invoker set search_path = ''" in text


def test_query_embedding_cache_is_deliberately_deferred() -> None:
    assert "create table public.search_query_embeddings" not in sql()
