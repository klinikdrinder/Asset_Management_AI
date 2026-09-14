# AI Search V3 Job 2 Core Schema

## Migrations

- `20260819054255_ai_search_v3_job2_core_schema.sql`
- `20260819054325_ai_search_v3_job2_ontology_seed.sql`
- `20260819054605_ai_search_v3_job2_reviewed_by_index.sql`

All are additive. The review-only Job 1 cleanup draft was not applied.

## New tables

| Table | Purpose | Primary key | Key relationships |
|---|---|---|---|
| `people` | Verified doctors, staff, and presenters; never automatic patient identity | `id uuid` | Referenced optionally by `asset_people.person_id` |
| `treatments` | Hierarchical controlled treatment vocabulary | `id uuid` | `parent_id → treatments.id RESTRICT` |
| `treatment_aliases` | Normalized search aliases | `id uuid` | `treatment_id → treatments.id CASCADE` |
| `anatomy_terms` | Hierarchical anatomical locations, not diagnoses | `id uuid` | `parent_id → anatomy_terms.id RESTRICT` |
| `actions` | Identity-free controlled verbs | `id uuid` | None |
| `locations` | Generic or verified organization locations | `id uuid` | `parent_id → locations.id RESTRICT` |
| `ai_analysis_runs` | Provider/model/pipeline/status/cost/error provenance | `id uuid` | `asset_id → assets.id CASCADE` |
| `asset_derivatives` | Generated files that are not canonical originals | `id uuid` | asset CASCADE; analysis run SET NULL |
| `asset_access_control` | Independent clinical, sensitivity, consent, usage, AI, review, and download controls | `asset_id uuid` | `asset_id → assets.id CASCADE`; reviewer SET NULL |

No biometric, face-template, patient-identity, scene, keyframe, OCR, transcript, V3 search RPC, or vector structure was added.

## Existing-table changes

- `asset_people.person_id`: nullable FK to `people`, `ON DELETE SET NULL`. Anonymous patient observations remain valid without identity.
- `asset_ai_profiles.primary_treatment_id`: nullable controlled treatment filter, SET NULL.
- `asset_ai_profiles.primary_anatomy_id`: nullable anatomical filter, SET NULL.
- `asset_ai_profiles.primary_location_id`: nullable location filter, SET NULL.

No existing free-text field was removed or migrated automatically.

## Constraints and uniqueness

Every ontology code is unique and uppercase-code constrained. Treatment aliases enforce normalized text and unique `(normalized_alias, language)`, preventing capitalization/whitespace duplicates. Hierarchies prevent direct self-parenting. Access-control and analysis statuses use CHECK constraints rather than PostgreSQL enums.

## Indexes

Unique code constraints provide their own indexes and were not duplicated. Additional indexes cover lower-cased names, hierarchy parents, alias treatment FK, asset/type derivative lookup, analysis asset/status/type, access-control classification/review/external-AI filtering, reviewer FK, and new canonical-reference FKs. No vector index was created.

## RLS and privileges

All nine tables have RLS enabled.

- `people`, `treatments`, `treatment_aliases`, `anatomy_terms`, `actions`, and `locations`: authenticated SELECT only, gated by `private.is_active_app_user()`.
- `asset_derivatives`, `asset_access_control`, and `ai_analysis_runs`: no client policies or direct client privileges; service/backend only until per-asset enforcement exists.
- All new tables explicitly revoke all privileges from PUBLIC, anon, and authenticated before the narrow reference SELECT grants.
- Service role retains backend access.
- No new function was created; existing owner-only `set_updated_at()` was reused by triggers.

## Delete behavior

Controlled hierarchy parents use RESTRICT so vocabulary cannot be silently dismantled. Alias rows CASCADE with their treatment. Canonical references use SET NULL so ontology/person deletion never deletes asset intelligence. Asset-dependent access, derivative, and run metadata CASCADE only if the canonical asset itself is deliberately deleted. A deleted analysis run leaves derivative identity intact through SET NULL.

## Access-control backfill

Exactly 881 rows were inserted, one per canonical asset. Values are conservative: UNCLASSIFIED, unknown usage/consent, NOT_REVIEWED external AI/review, nullable clinical and download decisions. V1/V2 do not read or enforce this table.

## Job 3 boundary

Job 3 may build timecoded scenes/keyframes and their relationship tables against these controlled IDs. Job 2 did not create or process any Job 3 object.

