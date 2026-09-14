from pathlib import Path

ROOT = Path(__file__).parents[1]
FILES = sorted((ROOT / "supabase/migrations").glob("20260819064*_ai_search_v3_job5_*.sql"))


def sql() -> str:
    return "\n".join(p.read_text(encoding="utf-8").lower() for p in FILES)


def test_three_additive_job5_migrations() -> None:
    assert len(FILES) == 3
    text = sql()
    for forbidden in ("drop table", "drop column", "delete from", "truncate table", "hybrid_search_assets"):
        assert forbidden not in text


def test_central_controls_remain_independent() -> None:
    text = sql()
    assert "can_user_view_asset_for" in text
    assert "can_user_download_asset_for" in text
    assert "can_asset_use_external_ai" in text
    assert "download_allowed is true" in text
    assert "external_ai_status='allowed'" in text
    assert "marketing_usage_status" not in text
    assert "consent_status" not in text


def test_permission_functions_are_hardened() -> None:
    text = sql()
    assert "security definer set search_path=''" in text
    assert "security invoker set search_path=''" in text
    assert "revoke all on function" in text
    assert "grant execute on function public.can_asset_use_external_ai(uuid) to authenticated" not in text


def test_asset_permissions_propagate_and_raw_vectors_stay_closed() -> None:
    text = sql()
    for table in ("assets", "asset_scenes", "asset_keyframes", "asset_transcript_chunks", "ocr_observations", "clinical_observations", "asset_search_documents", "scene_search_documents"):
        assert table in text
    assert "private.can_user_view_asset(asset_id)" in text
    assert "revoke all on table public.asset_access_control,public.asset_embeddings,public.asset_visual_embeddings" in text
