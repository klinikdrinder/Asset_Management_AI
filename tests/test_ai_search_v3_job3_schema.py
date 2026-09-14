from pathlib import Path


ROOT = Path(__file__).parents[1]
MIGRATIONS = [
    ROOT / "supabase/migrations/20260819061000_ai_search_v3_job3_scene_core.sql",
    ROOT / "supabase/migrations/20260819061100_ai_search_v3_job3_intelligence_layers.sql",
    ROOT / "supabase/migrations/20260819061200_ai_search_v3_job3_transcript_ocr.sql",
    ROOT / "supabase/migrations/20260819061300_ai_search_v3_job3_time_guard_fix.sql",
]


def sql() -> str:
    return "\n".join(path.read_text(encoding="utf-8").lower() for path in MIGRATIONS)


def test_job3_is_additive_and_does_not_process_media() -> None:
    text = sql()
    for forbidden in ("drop table", "drop column", "truncate table", "delete from"):
        assert forbidden not in text
    assert "insert into public.asset_scenes" not in text
    assert "asset_video_segments" not in text


def test_job3_security_and_cross_asset_integrity_are_explicit() -> None:
    text = sql()
    for table in ("asset_scenes", "asset_keyframes", "scene_people", "clinical_observations", "ocr_observations"):
        assert f"alter table public.{table} enable row level security" in text
    assert "from public, anon, authenticated" in text
    assert "foreign key (scene_id, asset_id)" in text or "foreign key(scene_id,asset_id)" in text
    assert "security invoker set search_path = ''" in text
    assert "revoke all on function public.validate_job3_scene_time_bounds()" in text


def test_identity_appearance_and_clinical_claims_remain_separate() -> None:
    text = sql()
    assert "create table public.scene_people" in text
    assert "create table public.person_appearances" in text
    assert "create table public.clinical_observations" in text
    for forbidden in ("face_embedding", "biometric", "ethnicity", "nationality_from_face", "diagnosis"):
        assert forbidden not in text
