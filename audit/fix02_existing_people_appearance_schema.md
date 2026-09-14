# FIX 2 — Existing People and Appearance Schema Inventory

Captured before applying the FIX 2 migration. This is the required pre-migration schema inventory; no database rows were changed while producing it.

## Live baseline

| Object | Rows | Assets | Current role |
|---|---:|---:|---|
| `scene_people` | 18 | 10 | Scene-bound observed people |
| `person_appearances` | 18 | 10 | Appearance bound by `(scene_person_id, scene_id, asset_id)` |
| `people` | 0 | 0 | Verified/canonical identities; not the observed-person entity |

All 18 observed-person rows have a matching appearance row. The existing 10-asset cohort has valid scene-person and appearance-person bindings. No existing record is to be rewritten or deleted by FIX 2.

## Existing 10 structured asset IDs

- `37838d30-a0ce-4f90-8cc3-c986db0aaa65`
- `444da390-0117-4380-8c87-d7c32f2903ff`
- `47611c6d-7923-42a4-87b6-c2a416a90f5c`
- `6215ad8b-12be-4a8e-bc49-f6b3dcf55c21`
- `64712c6a-c02c-46e9-9f73-16786109468b`
- `753eb5f3-82c7-4148-a226-d5b960fd8619`
- `7f72217d-3839-4920-86b4-ccc33e9e3d95`
- `babae120-9372-42ad-b535-02a3276ea2be`
- `bfae6c51-5d71-47ae-a3e1-6d07092b8896`
- `c86344e9-5b32-4d86-9205-67952d508651`

## Existing architecture

### `scene_people`

Important pre-FIX-2 columns: `id`, `scene_id`, `asset_id`, nullable `person_id`, `person_role`, `gender`, `exact_age`, `age_min`, `age_max`, `activity_summary`, `position_summary`, `identity_status`, `confidence`, `provenance`, `analysis_run_id`, `metadata`, timestamps.

Integrity mechanisms:

- Composite foreign key `(scene_id, asset_id)` to `asset_scenes`.
- Foreign key `person_id` to `people`.
- Unique `(id, scene_id, asset_id)` supports dependent composite references.
- Existing age-range validity check.

Observed roles use legacy values such as `SUBJECT`, `PATIENT_LIKE`, `CLINICIAN_LIKE`, and `STAFF_LIKE`. Only two rows contain legacy age ranges and gender values. All rows contain confidence/provenance. `person_id` is null because the `people` table is reserved for verified identities.

### `person_appearances`

Important pre-FIX-2 columns: `id`, `asset_id`, `scene_id`, `scene_person_id`, `keyframe_id`, `hair_color`, `hair_length`, `hair_texture`, `hair_style`, `hair_density_appearance`, `facial_hair`, skin/face/body attributes, `eyewear`, `wardrobe`, `uniform`, `accessories`, `makeup`, `general_description`, `confidence`, `provenance`, `analysis_run_id`, `metadata`, timestamps.

Integrity mechanisms:

- Composite foreign key `(scene_person_id, scene_id, asset_id)` to `scene_people`.
- Composite keyframe reference where a keyframe is present.
- RLS enabled; public, anonymous, and authenticated roles have no direct access; service role has the existing administrative access pattern.

## Gaps and reuse decision

The existing tables already express the two essential ownership relationships, so FIX 2 extends them instead of creating parallel person/appearance tables. Missing canonical capabilities are controlled search vocabularies, arbitrary apparent-age ranges with explicit confidence, person tracking, per-attribute evidence, model/run provenance, precedence, active/supersession state, and a same-person search access contract.

FIX 2 therefore:

- Reuses `scene_people` as the canonical observed-person occurrence.
- Reuses `person_appearances` as the canonical appearance occurrence.
- Keeps `people` for verified identity only.
- Adds `person_tracks` without automatically merging any people.
- Adds `person_attribute_evidence` for field-level evidence/provenance.
- Adds canonical columns alongside legacy columns, preserving every existing value.
- Adds a same-person, same-scene read view for FIX 3.

## Migration safety expectation

The migration is additive: it creates two tables and one view, adds nullable/defaulted columns, constraints, indexes, RLS/grants, and an update trigger. It contains no row backfill and no `INSERT`, `UPDATE`, `DELETE`, `UPSERT`, `TRUNCATE`, or destructive object operation.
