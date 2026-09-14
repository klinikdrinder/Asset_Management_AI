# FIX 2 — Canonical People Schema

The canonical observed person remains `public.scene_people`; `public.people` remains reserved for verified identities. FIX 2 adds canonical search fields without changing legacy values.

## Contract mapping

| Contract field | Database representation |
|---|---|
| person_id | `scene_people.id` |
| asset_id / scene_id | Existing non-null composite scene binding |
| person_track_id | New nullable FK to `person_tracks(id, asset_id)` |
| person_role | `canonical_person_role` |
| clinician_identity | `clinician_identity_id` FK to `people` |
| gender presentation | `gender_presentation` |
| apparent age range | `apparent_age_min`, `apparent_age_max` |
| age confidence | `apparent_age_confidence` |
| visibility/orientation | `face_visibility`, `scalp_visibility`, `body_orientation` |
| person confidence | `person_confidence` |
| provenance | `source_type`, `model_name`, `model_version`, `semantic_run_id` |
| precedence/version | `authority_rank`, `active`, `superseded_by` |
| timestamps | Existing `created_at`, `updated_at` |

Age is range-only in the canonical contract. Checks reject min greater than max, out-of-policy bounds, and partial ranges. The legacy `exact_age` column is preserved but is not exposed as canonical apparent age.

`person_tracks` models cautious cross-scene linkage. A track is unique within an asset and begins `UNVERIFIED`; the schema does not infer or merge identities.

