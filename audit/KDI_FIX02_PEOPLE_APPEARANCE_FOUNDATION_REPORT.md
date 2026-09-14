# KDI SEMANTIC SEARCH REPAIR — FIX 2 PEOPLE + APPEARANCE FOUNDATION

## Status

PASS. The canonical additive schema, ontology, deterministic materialization contract, evidence model, same-person access view, regression validation, and tests are complete. No 877-asset mass backfill occurred, and production parsing/ranking behavior was not changed or declared fixed.

## Foundation delivered

- `scene_people` remains the observed-person entity and now supports canonical roles, gender presentation, arbitrary apparent-age ranges, visibility/orientation, confidence, provenance, precedence, lifecycle, and cautious track linkage.
- `person_appearances` remains bound to one `scene_people` occurrence and now supports canonical hair, hairline, clothing, posture, PPE, confidence, provenance, precedence, and idempotent materialization.
- `person_tracks` can link distinct scene-person occurrences within one asset without automatically merging identities.
- `person_attribute_evidence` preserves field-level asset/scene/person/keyframe/assertion evidence and provenance.
- `person_appearance_search_v1` exposes a service-only same-person/same-scene structured access contract with range-overlap-ready age fields.

The target structure can be represented as one joined row: `PATIENT`, `MALE`, age 30–40, `RECEDING`, `SHIRT`, `BLUE`, all sharing the same person and scene identifiers. The view supports a target-35 overlap predicate (`min <= 35 AND max >= 35`).

## Controlled vocabulary and materialization

The locked code-level ontology is separate from the current parser and therefore cannot alter search behavior in FIX 2. The pure materializer normalizes explicit evidence only, preserves UNKNOWN as absence, uses stable keys, and enforces authority precedence. Person binding is a required precondition for future writes; scene-wide prose cannot safely prove which individual owns an attribute.

## Existing data regression

People remained 18 before and after; appearances remained 18 before and after. All 10 previously structured assets and all 18 composite bindings survived. Orphan people, orphan appearances, invalid age ranges, and duplicate active materializations are all zero. No raw assertions were removed.

## Validation sample

Ten existing scene-level assertion samples were run through the new transformation in dry-run mode. All 10 produced deterministic candidate structures and 28 proposed evidence rows; database rows written were zero. The exact asset IDs and field-level structural summaries are recorded in `audit/fix02_validation_results.md`.

## Tests

Seven automated tests passed and none failed. TypeScript typechecking also passed.

## Changed database objects

- Created: `person_tracks`, `person_attribute_evidence`, `person_appearance_search_v1`.
- Extended: `scene_people`, `person_appearances`.
- Added controlled-value, range, confidence, binding, lifecycle, idempotency, and lookup constraints/indexes.
- Enabled service-only access on new tables/view with RLS and explicit grant revocation.

## Files created

- `supabase/migrations/20260910030436_fix02_people_appearance_foundation.sql`
- `config/semantic-search/kdi_people_appearance_ontology_v1.json`
- `dashboard/db/people-appearance-materializer.ts`
- `dashboard/scripts/fix02-materialization-dry-run.ts`
- `dashboard/tests/fix02-people-appearance-foundation.test.ts`
- `audit/fix02_existing_people_appearance_schema.md`
- `audit/fix02_people_schema.md`
- `audit/fix02_appearance_schema.md`
- `audit/fix02_ontology.md`
- `audit/fix02_materialization_contract.md`
- `audit/fix02_validation_results.md`
- `audit/KDI_FIX02_PEOPLE_APPEARANCE_FOUNDATION_REPORT.md`

## Acceptance criteria

All 14 criteria pass. Canonical people and appearance schemas exist; age is range-based; bindings, confidence, evidence, vocabulary, same-person retrieval, existing records, dry-run materialization, automated tests, additive migration safety, and backfill limits are verified. Production complex-query search remains unfixed by design; FIX 3 must connect query understanding and structured retrieval.

## Next

FIX 3 — Natural-language query understanding and structured People/Appearance retrieval.
