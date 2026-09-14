# FIX 2 — Canonical Appearance Schema

The canonical appearance entity remains `public.person_appearances`. Its existing composite foreign key guarantees that `scene_person_id`, `scene_id`, and `asset_id` refer to one observed person occurrence.

Canonical columns added: `canonical_hair_color`, `canonical_hair_length`, `hair_density`, `hairline_pattern`, `clothing_type`, `clothing_color`, `posture`, `ppe`, `appearance_confidence`, `source_type`, `model_name`, `model_version`, `semantic_run_id`, `authority_rank`, `materialization_key`, `active`, and `superseded_by`.

Check constraints implement the locked vocabularies and confidence bounds. The partial unique index on active `materialization_key` makes deterministic materialization idempotent without treating legitimate multiple people as duplicates.

`public.person_attribute_evidence` links each inferred attribute to asset, scene, observed person, optional appearance, optional keyframe, optional semantic assertion, confidence, source type, model/run provenance, authority, and an idempotency key. Composite foreign keys prevent cross-asset or cross-scene evidence attachment.

The service-only `person_appearance_search_v1` view joins person and appearance on the existing same-person composite binding and returns one access shape for future structured retrieval. It is `security_invoker`, RLS-aware, and not granted to client roles.

