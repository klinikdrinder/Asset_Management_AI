# Job 7 permission filtering

The V3 SQL candidate CTE is materialized from `private.authorized_asset_ids()` before vector, scene, keyframe, or document retrieval. Unauthorized assets therefore cannot enter candidates, counts, explanations, or debug evidence.

Function posture: owner `postgres`, SECURITY DEFINER, `search_path=''`; PUBLIC execute FALSE, anon execute FALSE, authenticated execute TRUE. Parent and search/session tables retain RLS. An inactive-user invocation returned zero rows. Unauthenticated live V3 returned HTTP 403; unauthorized download returned HTTP 401.

