-- Job 5 post-DDL advisor follow-up: cover the two remaining relevant FKs.
create index asset_keyframes_scene_asset_idx on public.asset_keyframes(scene_id,asset_id);
create index asset_scenes_reviewed_by_idx on public.asset_scenes(reviewed_by) where reviewed_by is not null;
