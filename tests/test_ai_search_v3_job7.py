from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SQL=(ROOT/'supabase/migrations/20260820061951_ai_search_v3_job7_hybrid_search.sql').read_text(encoding='utf-8').lower()
SEARCH=(ROOT/'dashboard/app/lib/media/search.ts').read_text(encoding='utf-8')
PARSER=(ROOT/'dashboard/app/lib/media/search-v3.ts').read_text(encoding='utf-8')

def test_v3_is_additive_and_v1_v2_are_not_replaced():
    assert 'create or replace function public.hybrid_search_assets_v3' in SQL
    assert 'create or replace function public.hybrid_search_assets(' not in SQL
    assert 'create or replace function public.hybrid_search_assets_v2' not in SQL

def test_v3_permission_candidates_are_filtered_first():
    assert 'authorized as materialized' in SQL
    assert 'private.authorized_asset_ids()' in SQL
    assert SQL.index('authorized as materialized') < SQL.index('asset_signals as')

def test_v3_function_security_is_explicit():
    assert "security definer set search_path=''" in SQL
    assert 'revoke all on function public.hybrid_search_assets_v3' in SQL
    assert 'grant execute on function public.hybrid_search_assets_v3' in SQL
    assert 'to authenticated,service_role' in SQL

def test_pgvector_models_dimensions_and_indexes_are_fixed():
    assert 'public.vector(512)' in SQL
    assert "model_name='vit-b-32'" in SQL
    assert "model_version='laion2b_s34b_b79k'" in SQL
    assert SQL.count('using hnsw') == 3

def test_hybrid_weights_are_documented_and_normalized():
    for term in ('0.30*st.ss','0.20*s.sv','0.18*a.av','0.12*a.al','0.08*s.sl','0.07*s.kv','0.05*a.fn'):
        assert term in SQL

def test_count_bound_threshold_dedup_and_exclusion():
    assert 'coalesce(result_limit,5),50' in SQL
    assert 'final>=p.threshold' in SQL
    assert 'excluded_asset_ids' in SQL
    assert 'select id,round((final*100)' in SQL

def test_lexical_search_is_parameterized_and_gin_backed():
    assert "websearch_to_tsquery('english'" in SQL
    assert 'ts_rank_cd' in SQL
    assert 'search_query text' in SQL
    assert 'execute format' not in SQL and 'execute search_query' not in SQL

def test_backend_uses_v3_and_graceful_null_visual_vector():
    assert 'rpc/hybrid_search_assets_v3' in SEARCH
    assert 'visual_query_embedding: visualEmbedding' in SEARCH
    assert 'generateVisualQueryEmbedding' in SEARCH

def test_conversation_parser_supports_next_and_refinement():
    assert 'NEXT_RESULTS' in PARSER and 'returnedAssetIds' in PARSER
    assert 'REFINEMENT' in PARSER and 'previous?.filters' in PARSER

def test_no_ollama_or_media_processing_added_by_job7():
    assert 'ollama' not in SQL
    assert all(word not in SQL for word in ('asset_scenes set','asset_keyframes set','truncate','delete from'))
