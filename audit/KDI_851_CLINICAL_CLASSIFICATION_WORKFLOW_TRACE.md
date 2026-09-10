# KDI — 851-Asset Clinical Classification Workflow Trace (READ-ONLY)

- **Date:** 2026-09-10
- **Supabase project:** `wcqqjpndlwsvatjuqnol` (from restored `dashboard/.env.local`)
- **Scope:** Trace only. **No data modified. No indexing run. No approvals applied.**

---

## 1. Exact root cause (confirmed)

`assets` = **881**. Library shows **30** because the RLS SELECT policy `assets_asset_permission_read` calls `private.can_user_view_asset_for`, which has a **hard gate `asset_access_control.is_clinical IS NOT NULL`**.

Live `asset_access_control` state:
| Predicate | Count |
|---|---|
| total rows | 881 |
| `internal_usage_status='ALLOWED'` | 880 |
| `is_clinical=true` (ALLOWED) | **30** ← the visible set |
| `is_clinical=false` | 0 |
| `is_clinical IS NULL` | **851** |
| `ALLOWED & sensitivity='GENERAL' & is_clinical NULL` | 850 |
| `review_status='REVIEWED'` | 860 |

The 851 have `is_clinical = NULL` → fail the gate → invisible to everyone (incl. super-admin).

Schema (`…job2_core_schema.sql`): `is_clinical boolean` (**nullable, no default**), `requires_clinical_permission boolean` (nullable, no default), `sensitivity_level text NOT NULL default 'GENERAL'`, `internal_usage_status text NOT NULL default 'UNKNOWN'`, `classification_status default 'UNCLASSIFIED'`. So **`is_clinical=NULL` = never processed by the semantic rollout** (default state), not "false" and not "uncertain-by-classifier".

---

## 2. The existing scripts (what actually writes the fields)

Across the entire repo, the **only** writers of `is_clinical` / `sensitivity_level` / `requires_clinical_permission` are two rollout scripts — both **hardcode a blanket clinical payload**, neither derives it from content:

### `scripts/phase10_controlled_batch.py` — the de-facto classifier
- **Purpose:** Local semantic rollout for a *frozen* manifest (`phase_05_selected_20_manifest.json`, rollout positions **12–30**, 19 assets). Builds on Phase 9's 11 → the current 30.
- **Inputs:** frozen manifest; `.env`/`.env.local`; local SmolVLM2 model (`.kdi-models/…`); Google Drive service-account key; ffmpeg. Network disabled (local only).
- **Reads:** `assets`, `asset_destinations`, `asset_visual_embeddings`, `semantic_analysis_runs`, `asset_scenes/keyframes`, manifest.
- **Writes:** `semantic_analysis_runs`, `asset_scenes`, `asset_keyframes`, `semantic_assertions`, `semantic_assertion_evidence`, `asset_semantic_layers`, `semantic_narratives`, `search_document_build_runs`, `search_document_builds`, `search_document_concepts`, `semantic_embeddings`, `asset_ai_profiles`, `asset_search_documents`, and finally **`asset_access_control`**.
- **ACL columns written (line 115, hardcoded):** `classification_status='VERIFIED', is_clinical=True, sensitivity_level='CLINICAL', internal_usage_status='ALLOWED', requires_clinical_permission=True, download_allowed=False`.
- **Range/ordinals:** NO — hard-scoped to the frozen 12–30 manifest (raises `LOCKED_MANIFEST_SCOPE_INVALID` otherwise).
- **Dry-run / validation-only:** NO (writes as it processes; resumable via checkpoint).
- **Human review:** NO per-asset human decision for `is_clinical`; automated + a `CLINICAL_GATE` that **rejects** assets whose observations contain surgical terms (`surgery, procedure, hair transplant, fue, graft, prp, injection, …`) → those **FAIL** (not classified).

### `scripts/phase09_repair_search_acl.py` — one-off repair (the first 11)
- Hardcoded `ASSETS` list (11 IDs). Writes the **identical** payload `{classification_status:'VERIFIED', is_clinical:True, sensitivity_level:'CLINICAL', internal_usage_status:'ALLOWED', requires_clinical_permission:True, download_allowed:False}`. No ranges, no dry-run, no per-asset logic.

### `scripts/apply_privacy_approvals.py` — external-AI approval apply (NOT is_clinical)
- **Purpose:** Validate/apply a completed CSV worksheet for **external-AI authorization**, frozen ordinals **31–130** (default).
- **Reads:** `reports/…/100/privacy-approval-required.json` manifest + CSV worksheet.
- **Writes `asset_access_control`:** `review_status='REVIEWED'`, `reviewed_at`, `metadata.privacy_review`; on `APPROVE` → `classification_status='VERIFIED', internal_usage_status='ALLOWED', external_ai_status='ALLOWED'`; `DENY`/`HOLD` set `external_ai_status`.
- **Does NOT write:** `is_clinical`, `sensitivity_level`, `requires_clinical_permission`. ⇒ **Running this alone would NOT make an asset visible in the library.**
- **Dry-run:** YES (validate-only unless `--apply`). **Human approval:** YES (per-row `human_decision` ∈ {APPROVE,DENY,HOLD}, `reviewer`, `reviewed_at`; blank = error).
- **Ordinal range:** YES (`--ordinal-start/--ordinal-end`, must equal the frozen cohort exactly). **Asset-ID list:** NO.

### `scripts/create_authorized_privacy_worksheet.py` — worksheet generator
- Generates the CSV for `apply_privacy_approvals` from a frozen manifest ordinal range. Fields: `ordinal, asset_id, filename, local_classification, confidence, patient_context, procedure_context, sensitive_text, external_ai_current, human_decision, reviewer, reviewed_at, notes`. Pre-fills `local_classification='UNCERTAIN'`, `human_decision='APPROVE'`, `reviewer='KDI_OPERATOR'`. **This worksheet governs external-AI usage — not `is_clinical`.**

### `scripts/run_production_semantic_bulk.py` — bulk rollout (ordinals 31–130)
- Bounded, resumable production rollout for **frozen ordinals 31–130** (`--ordinal-start/--ordinal-end` default 31/130, `--resume`, `--only-not-ready`, `--limit N`, `--preflight`, `--provider claude|claude_code|codex_cli`). Uses **external AI** providers. Eligibility gated by `supabase_production_adapter.py`, which only **reads** `classification_status/internal_usage_status/external_ai_status`. It does **not** write `is_clinical` inline.

> **No standalone / evidence-based `is_clinical` classifier exists.** No script anywhere sets `is_clinical=false`.

---

## 3. Database write path per field

| Field | Source of value | Script/function | Table.column | Allowed values | Human approval? |
|---|---|---|---|---|---|
| `is_clinical` | **Hardcoded `True`** on successful local analysis | phase10_controlled_batch / phase09_repair_search_acl | `asset_access_control.is_clinical` | bool / NULL | No (automated; CLINICAL_GATE rejects explicit media) |
| `sensitivity_level` | Hardcoded `'CLINICAL'` | phase10 / phase09 | `.sensitivity_level` | GENERAL, INTERNAL, RESTRICTED, CLINICAL, HIGHLY_RESTRICTED | No |
| `internal_usage_status` | Hardcoded `'ALLOWED'` | phase10 / phase09 / apply_privacy_approvals(APPROVE) | `.internal_usage_status` | UNKNOWN, ALLOWED, RESTRICTED, NOT_ALLOWED | Only in apply-worksheet path |
| `requires_clinical_permission` | Hardcoded `True` | phase10 / phase09 | `.requires_clinical_permission` | bool / NULL | No |
| `classification_status` | `'VERIFIED'` | phase10 / phase09 / apply(APPROVE) | `.classification_status` | UNCLASSIFIED, AI_SUGGESTED, REVIEW_REQUIRED, VERIFIED | Apply-path only |
| `review_status` / `privacy_review` | `'REVIEWED'` + metadata block | apply_privacy_approvals | `.review_status`, `.reviewed_at`, `.metadata` | NOT_REVIEWED, PENDING, REVIEWED, REQUIRES_REVIEW | **Yes** (worksheet) |
| `external_ai_status` | worksheet decision | apply_privacy_approvals | `.external_ai_status` | NOT_REVIEWED, ALLOWED, RESTRICTED, NOT_ALLOWED | **Yes** (worksheet) |
| `marketing_usage_status` | **not written by any workflow** | — | `.marketing_usage_status` | (default UNKNOWN) | — |
| `consent_status` | **not written by any workflow** | — | `.consent_status` | (default UNKNOWN) | — |

`privacy_review_status` — **does not exist**; privacy state lives in `review_status` + `metadata.privacy_review`.

---

## 4. How `is_clinical` is classified (the important part)

**It is not a per-content true/false decision.** The workflow sets `is_clinical = True` (blanket, with `sensitivity='CLINICAL'`, `requires_clinical_permission=True`) for **every asset that successfully completes the local semantic rollout**. There is a `CLINICAL_GATE` that **rejects/fails** assets whose local observations contain explicit surgical terms — those are not indexed and keep `is_clinical=NULL`. **No path sets `is_clinical=false`** (confirmed: 0 rows). Classification basis = **rule/pipeline-driven blanket-clinical**, gated by local visual analysis; not filename/folder/consent-derived.

`is_clinical = NULL` therefore means **"not yet processed by the rollout"** (default), not "uncertain" or "classifier failure".

---

## 5. Can the 851 be classified from existing data (no re-analysis)?

**No, not via the existing approved workflow.** Evidence in the DB:
- `asset_search_documents build_status=READY` = **30**; `asset_ai_profiles` = 36; `asset_semantic_index` = 20. The other ~851 have **no stored semantic evidence**.
- The official workflow does **not** classify from stored evidence — it **re-downloads media and runs local visual analysis** every time, then hardcodes the ACL.

⇒ **Existing-data-sufficient: 0 / 851.** **Requires new analysis: 851 / 851** (local visual re-analysis via phase10-style rollout, or external-AI via bulk) — which is exactly the "indexing" this task forbids. There is currently **no metadata-only ACL backfill script**.

---

## 6. Safe batch capability (existing scripts)
| Capability | Supported? | Detail |
|---|---|---|
| Single asset | Partial | via `run_production_semantic_bulk.py --limit 1` (still within frozen range) |
| Ordinal range | **YES** | `run_production_semantic_bulk.py --ordinal-start N --ordinal-end M` and `apply_privacy_approvals.py --ordinal-start/--end` — **but only inside frozen manifests (≤130)** |
| Asset-ID list | **NO** | no script accepts an arbitrary `--asset-ids` list (phase09's list is hardcoded in source) |
| All 851 | **NO** | frozen manifests/cohorts only cover ordinals ≤130; **ordinals 131–881 have no frozen manifest** and no script scope |

Example (do **not** run): `python scripts/run_production_semantic_bulk.py --ordinal-start 31 --ordinal-end 130 --preflight`

---

## 7. Idempotency
**PARTIAL / safe-to-resume.**
- `phase10_controlled_batch.py`: checkpoint + `if asset_id in done: continue`; uses `upsert`/`if-not-exists` guards → re-run skips completed, no duplicates. Enforces baseline-drift checks (raises on unexpected state).
- `run_production_semantic_bulk.py`: `--resume` / `--only-not-ready`.
- `apply_privacy_approvals.py`: deterministic `update … eq(asset_id)` → re-run overwrites the same values (idempotent result) but rewrites `reviewed_at`/`recorded_at` timestamps.
No workflow creates duplicate ACL rows (`asset_id` is PK).

---

## 8. Human-approval gates
- **External-AI usage:** YES — CSV worksheet (`create_authorized_privacy_worksheet.py`) → `apply_privacy_approvals.py`. Reviewer must set `human_decision` (APPROVE/DENY/HOLD), `reviewer`, `reviewed_at`; blank/invalid rows are rejected; worksheet must contain exactly the frozen ordinal set. Dry-run validates before `--apply`.
- **`is_clinical` value:** **NO human gate.** It is auto-set to `True` by the rollout (with a CLINICAL_GATE rejecting explicit media). There is no per-asset human "is this clinical?" review in code.

---

## 9. Safety boundaries / side effects of the only is_clinical-writing workflow
Running phase10/bulk to set `is_clinical` also:
- **Performs full semantic indexing** — writes `semantic_assertions`, `asset_semantic_layers`, `semantic_narratives`, `search_document_builds/concepts`, `semantic_embeddings`, `asset_ai_profiles`, `asset_search_documents`, `asset_scenes`, `asset_keyframes`, and **activates** them (makes the asset searchable). ⇒ This **is** indexing.
- Sets `internal_usage_status='ALLOWED'`, `sensitivity_level='CLINICAL'`, `requires_clinical_permission=True`, `classification_status='VERIFIED'`.
- **download_allowed=False** — does **not** enable downloads.
- **Does NOT touch** `marketing_usage_status`, `consent_status` (stay UNKNOWN), or `external_ai_status` (phase10 leaves it; only the worksheet/apply path changes it).
- No deletion; does not change source availability.

⇒ Classifying `is_clinical` via the existing workflow **cannot** accidentally grant marketing/public/social/download rights (those are separate, untouched fields). But it **does** trigger semantic indexing + embeddings + search-document activation.

---

## 10. RLS result after classification (from current definitions)
`private.can_user_view_asset_for(user, asset)` (phase18) returns true iff: user active; `upload_status NOT IN ('FAILED','MISSING')`; `is_asset_source_available(asset)`; `internal_usage_status='ALLOWED'`; `sensitivity_level IS NOT NULL`; `is_clinical IS NOT NULL`; AND either
- **non-clinical branch:** `is_clinical=false AND requires_clinical_permission=false AND sensitivity_level IN ('GENERAL','INTERNAL')`, or
- **clinical branch:** `viewer.can_view_clinical=true AND (is_clinical=true OR requires_clinical_permission=true OR sensitivity_level IN ('RESTRICTED','CLINICAL','HIGHLY_RESTRICTED'))`.

So for one of the 851 (currently `is_clinical=NULL, internal='ALLOWED', sensitivity='GENERAL'`, source available):
- **Now:** `is_clinical NULL` → gate fails → hidden.
- **If set `is_clinical=true, requires_clinical_permission=true` (what the rollout does):** visible to the super-admin (`can_view_clinical=true`), hidden from non-clinical staff.
- **If set `is_clinical=false, requires_clinical_permission=false` (sensitivity GENERAL):** visible to **all** staff via the non-clinical branch. *(No existing script produces this state.)*

---

## 11. Safe backfill plan — DESIGN ONLY (do not execute)
> Honest caveat: the existing approved workflow ties `is_clinical` to full semantic indexing and only covers ordinals ≤130. A true metadata-only visibility backfill for all 851 would need **(a)** a policy decision (blanket-clinical vs per-asset clinical/non-clinical) and **(b)** a new, separately-approved ACL-only script. Nothing below should run in this task.

- **PHASE A (read-only):** enumerate the 851 `WHERE is_clinical IS NULL` and cross-check `is_asset_source_available` + `internal_usage_status`. (Already done here: 850 are ALLOWED+GENERAL+source-likely-available.)
- **PHASE B (dry-run):** for ordinals ≤130, generate worksheet (`create_authorized_privacy_worksheet.py`) and run `apply_privacy_approvals.py` **without** `--apply` to validate; run `run_production_semantic_bulk.py --preflight`.
- **PHASE C (human review):** operator completes worksheet decisions (external-AI) and — separately — a decision on clinical classification policy.
- **PHASE D (apply, deliberate, out of this task):** run the approved rollout per frozen cohort to set `is_clinical` (this also indexes). For ordinals 131–881, first define a new frozen manifest **or** author a reviewed metadata-only ACL script.
- **PHASE E (read-only verify):** re-count `is_clinical IS NOT NULL` and RLS-visible count.
- **PHASE F:** re-test `/library` under the admin.

---

## 12. Expected outcome after valid classification
**Not guaranteed 881/881.** Residual gates that can still hide assets:
- **CLINICAL_GATE rejections:** for a hair-transplant clinic, many of the 585 videos / 293 images likely depict procedures and would **FAIL** local analysis (`CLINICAL_GATE_FAILED`) → stay `is_clinical=NULL` → hidden.
- **No frozen cohort beyond ordinal 130:** existing scripts cannot even reach ordinals 131–881 without a new manifest/script.
- **`is_asset_source_available`:** any asset whose `source_files` are missing/trashed/`REMOVED_FROM_SOURCE` or whose folder is inactive stays hidden even if classified.
- **Clinical branch requires `can_view_clinical`:** blanket `is_clinical=true` keeps assets hidden from non-clinical staff (only the super-admin/clinical roles see them).

Realistic ceiling for the **super-admin** after a full, successful rollout is *up to* 881, but the CLINICAL_GATE and cohort-scope limits make < 881 the likely practical outcome without policy changes.

---

## Summary answers
- **Unclassified:** 851 (`is_clinical IS NULL`).
- **Only is_clinical writers:** `phase10_controlled_batch.py` (19) + `phase09_repair_search_acl.py` (11) = current 30; both blanket `True`, tied to indexing.
- **Apply script (external-AI, not is_clinical):** `apply_privacy_approvals.py`.
- **Existing data sufficient:** 0/851. **Needs new analysis:** 851/851.
- **PRODUCTION DATA MODIFIED: 0.**
