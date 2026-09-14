# ACL Backfill — Current `asset_access_control` Contract (READ-ONLY discovery)

Source of truth: `supabase/migrations/20260819054255_ai_search_v3_job2_core_schema.sql` (+ RLS in `…job5_rls_permission_enforcement.sql` and `…phase18_authorization_enforcement.sql`). No schema changes proposed or made.

## Columns, defaults, constraints
| Column | Type | Default | Allowed values (CHECK) | Notes |
|---|---|---|---|---|
| `asset_id` | uuid PK | — | FK → assets(id) | |
| `classification_status` | text NOT NULL | `'UNCLASSIFIED'` | UNCLASSIFIED, AI_SUGGESTED, REVIEW_REQUIRED, VERIFIED | |
| `is_clinical` | boolean | **none (NULL)** | — | **RLS gate: must be NOT NULL** |
| `sensitivity_level` | text NOT NULL | `'GENERAL'` | GENERAL, INTERNAL, RESTRICTED, CLINICAL, HIGHLY_RESTRICTED | never null |
| `consent_status` | text NOT NULL | `'UNKNOWN'` | UNKNOWN, NOT_REQUIRED, PENDING, CONFIRMED, RESTRICTED, EXPIRED, REVOKED | **untouched** |
| `internal_usage_status` | text NOT NULL | `'UNKNOWN'` | UNKNOWN, ALLOWED, RESTRICTED, NOT_ALLOWED | **preserved** (RLS needs ALLOWED) |
| `marketing_usage_status` | text NOT NULL | `'UNKNOWN'` | UNKNOWN, PENDING, APPROVED, RESTRICTED, NOT_ALLOWED | **untouched** |
| `external_ai_status` | text NOT NULL | `'NOT_REVIEWED'` | NOT_REVIEWED, ALLOWED, RESTRICTED, NOT_ALLOWED | **untouched** |
| `requires_clinical_permission` | boolean | none (NULL) | — | set by decision |
| `download_allowed` | boolean | none (NULL) | — | **untouched** |
| `review_status` | text NOT NULL | `'NOT_REVIEWED'` | NOT_REVIEWED, PENDING, REVIEWED, REQUIRES_REVIEW | **untouched** (see invariant) |
| `reviewed_by` | uuid | — | FK → auth.users(id) | **untouched** |
| `reviewed_at` | timestamptz | — | — | **untouched** |
| `metadata` | jsonb NOT NULL | `'{}'` | must be object | provenance appended (merge, non-destructive) |

## Invariants observed
- `asset_access_control_review_fields_check`: `(reviewed_at IS NULL AND reviewed_by IS NULL) OR review_status IN ('REVIEWED','REQUIRES_REVIEW')`. ⇒ **We deliberately do NOT write `reviewed_at`/`reviewed_by`/`review_status`**, so this constraint can never be violated and existing external-AI review state (860 REVIEWED rows) is preserved. Reviewer/reviewed_at provenance is recorded in `metadata.acl_classification_backfill` + the audit log instead.
- `metadata` must be a JSON object → we merge, never replace.
- `is_clinical` / `requires_clinical_permission` are nullable with no default → NULL = "never classified".

## Fields with NO column (do not invent)
- `privacy_review_status` — **does not exist**. Privacy provenance lives in `review_status` + `metadata.privacy_review` (written only by `apply_privacy_approvals.py`).

## RLS visibility (current) — `private.can_user_view_asset_for`
Visible iff: user active; `upload_status NOT IN ('FAILED','MISSING')`; `is_asset_source_available(asset)`; `internal_usage_status='ALLOWED'`; `sensitivity_level IS NOT NULL`; `is_clinical IS NOT NULL`; AND (non-clinical branch: `is_clinical=false AND requires_clinical_permission=false AND sensitivity_level IN ('GENERAL','INTERNAL')`) OR (clinical branch: `viewer.can_view_clinical AND (is_clinical=true OR requires_clinical_permission=true OR sensitivity_level IN ('RESTRICTED','CLINICAL','HIGHLY_RESTRICTED'))`).

## Live state (read-only, project `wcqqjpndlwsvatjuqnol`)
- 881 rows; `is_clinical`: TRUE=30, FALSE=0, NULL=851.
- 850 of the 851 already have `internal_usage_status='ALLOWED'` + `sensitivity_level='GENERAL'` → **only the `is_clinical IS NULL` gate hides them**.
