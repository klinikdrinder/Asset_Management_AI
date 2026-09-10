# FIX 2 — Validation Results

## Database migration

Applied migration: `supabase/migrations/20260910030436_fix02_people_appearance_foundation.sql` (`fix02_people_appearance_foundation`). It contains additive DDL only and no cohort backfill.

| Validation | Before | After | Result |
|---|---:|---:|---|
| `scene_people` rows | 18 | 18 | PASS |
| `person_appearances` rows | 18 | 18 | PASS |
| Structured assets | 10 | 10 | PASS |
| Existing asset IDs preserved | 10 | 10 | PASS |
| Valid appearance-person bindings | 18 | 18 | PASS |
| Orphan people | 0 | 0 | PASS |
| Orphan appearances | 0 | 0 | PASS |
| Invalid age ranges | 0 | 0 | PASS |
| Duplicate active tracked person occurrences | 0 | 0 | PASS |
| Duplicate active appearance materializations | 0 | 0 | PASS |

New tables start empty (`person_tracks=0`, `person_attribute_evidence=0`) because no backfill was run. The search view returns all 18 legacy-bound occurrences. The representative same-person structured query executed successfully and returned zero current matches, as expected before materialization/backfill.

## Controlled materialization sample

The read-only harness selected 10 scene-bound assertion samples and produced 10 deterministic proposals. It wrote zero database rows. Proposed evidence-row counts were 4, 4, 3, 2, 3, 3, 3, 1, 2, and 3 (28 total). These are extraction proposals, not approved production facts; a future writer must confirm person-level binding first.

Exact validation asset IDs:

- `b79c659c-c5fe-438c-8c46-10d1542b3301`
- `fbfe0bdf-bb73-49f1-883d-3c7043878355`
- `8cfdfc5e-4c54-45b3-bdb5-54129cc96ba9`
- `ef44c4b1-048b-41f7-b675-a1a0ae29331b`
- `cd453280-2096-4a68-bfd2-1bf070f79140`
- `f29e992c-8072-4b9a-b4c7-fddfc6efbcd9`
- `4248f9e4-9ace-4923-94be-ff6cde1eb506`
- `536417dd-2987-4f12-9acc-2eb4daa790e4`
- `b1e6a644-b467-4867-af4f-66b60717ea38`
- `0142e25c-f4d6-4c37-87dd-b09aab2c8cc4`

## Automated verification

- Foundation tests: 7 passed, 0 failed.
- TypeScript typecheck: passed.
- Covered same-person positive match, two-person anti-join behavior, range-only age policy, cross-scene track model, UNKNOWN preservation, supported assertion normalization, and precedence protection.

## Security/performance review

RLS is enabled on both new tables; public, anonymous, and authenticated grants are revoked. The advisor reports the intentional informational `RLS enabled, no policy` condition for these service-only tables. Existing project-wide extension, auth, unindexed-FK, unused-index, and duplicate-index notices were not introduced as FIX 2 repair scope and were not changed.

