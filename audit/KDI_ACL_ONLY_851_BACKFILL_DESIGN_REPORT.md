# KDI — ACL-Only 851 Classification Backfill — Design Report

- **Date:** 2026-09-10
- **Supabase project:** `wcqqjpndlwsvatjuqnol` (restored `dashboard/.env.local`)
- **Task type:** Design + implementation + read-only preview. **Production data modified: 0.** `--apply` was NOT run.

## Why this workflow is needed
881 assets exist; only **30** are visible in the Central Library because the RLS visibility function requires `asset_access_control.is_clinical IS NOT NULL`, and **851 rows are NULL**. The only existing writers of `is_clinical` (`phase10_controlled_batch.py`, `phase09_repair_search_acl.py`) do so as a side-effect of **full semantic indexing** and blanket-set `CLINICAL`, and cover only frozen cohorts ≤ ordinal 130. There is no indexing-free, reviewed way to classify the 851. This workflow fills that gap.

## Existing ACL architecture
See `audit/fix_acl_backfill_current_contract.md` for the full column/constraint/RLS contract. Key point: 850/851 already have `internal_usage_status='ALLOWED'` + `sensitivity_level='GENERAL'`; only the `is_clinical` gate hides them.

## New components
| Path | Role |
|---|---|
| `src/kdi_media/acl_classification.py` | Pure logic: suggestion rules, decision→ACL mapping, validation, staleness/idempotency (`plan_row`), RLS prediction, integrity hashing, field-safety invariants, `apply_plans`. No DB, no secrets. |
| `scripts/create_acl_classification_worksheet.py` | **Read-only** worksheet generator (CSV + SHA-256 manifest). Only `.select()` calls. |
| `scripts/apply_acl_classification_decisions.py` | Validator/applier. **Dry-run by default**; `--apply` gated. |
| `tests/test_acl_classification_backfill.py` | 23 tests (14 required cases + fixtures A–E + prediction/hash). |

## Worksheet fields
`asset_id, ordinal, filename, original_filename, media_type, source_name, source_folder, source_reference, current_internal_usage_status, current_sensitivity_level, current_is_clinical, current_requires_clinical_permission, current_download_allowed, source_available, existing_description_summary, existing_content_type, existing_treatment, existing_subject, existing_clinical_visual_summary, existing_semantic_evidence_available, existing_people_evidence_available, suggested_classification, suggestion_reason, suggestion_confidence, review_decision, reviewer, reviewed_at, review_notes`. No credentials or URLs (only relative source paths).

## Advisory classification rules (stored metadata only)
Suggestion derived from source folder/name + filename + stored OCR text. Clinical hints (patient, treatment, procedure, hair transplant, fue, graft, donor, recipient, prp, injection, scalp, consultation, before/after, …) → `CLINICAL`; branding/equipment/marketing/admin hints → `NON_CLINICAL`; conflicting or absent evidence → `UNRESOLVED`. **Never** analyzes media, downloads, or calls external AI. Suggestions are advisory and never applied without a human `review_decision`.

## Reviewed decision → ACL mapping
| review_decision | is_clinical | sensitivity_level | requires_clinical_permission | classification_status | internal_usage_status |
|---|---|---|---|---|---|
| CLINICAL | TRUE | CLINICAL | TRUE | VERIFIED | **preserved** |
| NON_CLINICAL | FALSE | GENERAL (or preserve INTERNAL) | FALSE | VERIFIED | **preserved** |
| UNRESOLVED | — | — | — | — | no write |
| SKIP | — | — | — | — | no write |

## Fields never touched
`external_ai_status`, `marketing_usage_status`, `consent_status`, `download_allowed`, `internal_usage_status`, `review_status`/`reviewed_at`/`reviewed_by`, and all semantic/search/embedding/scene/keyframe state. Enforced in code by `ALLOWED_WRITE_KEYS`/`FORBIDDEN_WRITE_KEYS` and asserted per write (test 11).

## Transaction / safety design
PostgREST has no multi-row transaction, so: **validate-all-first** (any row-level `ERROR` aborts before any write), then per-row idempotent updates, each recorded immediately to an audit file so a partial failure reports exactly what was applied. Batch size configurable. Provenance appended to `metadata.acl_classification_backfill` (merge, non-destructive) + local audit JSON under `audit/acl_backfill/`.

## Stale protection & no-blind-overwrite
Manifest carries `worksheet_version`, `project_id`, `generated_at`, `cohort_count`, and a **canonical SHA-256** over the *immutable* columns (review columns excluded, so legitimate review edits don't break it, but identity/suggestion tampering does). Apply re-verifies the hash, rejects duplicate asset_ids, and by default only writes rows where live `is_clinical IS NULL`. Rows whose state changed since generation are marked `STALE` and skipped. Reclassifying already-set rows requires explicit `--allow-reclassification`.

## Idempotency
Re-running an applied worksheet yields `ALREADY_APPLIED` (0 additional writes, no duplicates — `asset_id` is PK). Verified by test 12.

## RLS prediction
Dry-run predicts per-row `EXPECTED_VISIBLE_AFTER_APPLY` using the current phase18 predicate (internal_usage=ALLOWED, sensitivity not null, is_clinical not null, source available, correct branch for a `can_view_clinical` super-admin). CLINICAL + super-admin → visible; NON_CLINICAL + GENERAL → visible to all staff; source-unavailable → predicted hidden.

## Tests
23/23 pass (`.venv`, `PYTHONPATH=src`): NULL→CLINICAL, NULL→NON_CLINICAL, UNRESOLVED/SKIP no-write, existing-classified skip, duplicate rejection, missing reviewer/reviewed_at, stale state, dry-run 0 writes, unrelated-fields-untouched, idempotent rerun, invalid decision, source-unavailable prediction, advisory fixtures A–E, and hash/prediction properties.

## Read-only 851 preview (generated this task, NOT applied)
- `audit/acl_backfill/acl_851_review_worksheet.csv` (851 rows, review columns blank)
- `audit/acl_backfill/acl_851_review_manifest.json`
- Cohort 851 · suggestions: **CLINICAL 281**, **NON_CLINICAL 0**, **UNRESOLVED 570** · source-unavailable 3 · SHA-256 `9bc950f1…c54d8`.
- Suggestions are labeled **NOT APPROVED / NOT APPLIED** in the manifest.

## Dry-run proof (synthetic fixture; real 851 worksheet untouched)
`apply_acl_classification_decisions.py --worksheet fixture_reviewed.csv --manifest fixture_manifest.json` (no `--apply`) → hash validated, `APPLY=2, SKIP_UNRESOLVED=1`, `predicted_visible_after_apply=2`, **`writes_performed=0`**.

## Remaining blockers / notes for the human reviewer
- 570/851 are `UNRESOLVED` from stored metadata alone — they need a human decision (folder/filename gave no signal). This is expected and safe (never auto-applied).
- The advisory suggestion is intentionally conservative and clinical-leaning for a clinic; **the reviewer's decision is authoritative**.
- 3 assets have unavailable sources → even if classified they stay hidden until the source is restored.
- Making assets visible also requires `internal_usage_status='ALLOWED'` (already true for 850) and, for CLINICAL, a viewer with `can_view_clinical` (the super-admin has it; general staff will not see clinical assets).
