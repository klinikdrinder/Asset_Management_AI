# AI Search v3 — Job 1 test run: authorization & consent decision

**Cohort:** `ai_search_v3_job1_test_20` — 10 video (`Nushad Raw Video`) + 10 image
(`ALL PATIENT REVIEW`). Asset ids in `job1_test20_candidate_cohort.json`.

**Decision (on file):** Proceed to send these 20 clinical assets to an external
API (Anthropic Claude vision) for a scoped extraction test, **despite
`consent_status = UNKNOWN` on all 881 assets**, and despite the existing
external-AI approval having been scoped to *pilot indexing* (Job 6 / phase-11).

**Rationale:** 20 assets is a small, explicitly-enumerated cohort; the run is
scoped per-asset (no global `KDI_EXTERNAL_AI_ENABLED` flag), reversible by a
single delete on the new `analysis_run_id`, and needed to validate the ontology
resolver + v2 contract before any larger run.

**Scope guarantees for this run:**
- External AI invoked only for the 20 enumerated `asset_id`s.
- `KDI_EXTERNAL_AI_ENABLED=true` set only in the runner's process env; never
  written to any `.env`.
- Per-asset `can_asset_use_external_ai` RPC checked before each call.
- Fresh `analysis_run_id`; reversal = `delete from asset_search_concepts_v2
  where analysis_run_id = <new>`.
- This decision is copied into the run record (`ai_analysis_runs.metadata` /
  cohort record) at execution time.

**REQUIRED BEFORE ANY FULL-LIBRARY RUN:** a consent workflow. `consent_status`
is `UNKNOWN` for every asset; a 20-asset test is acceptable under the reasoning
above, but sending the full library (or any materially larger cohort) to an
external API without a consent determination is **not** authorized by this note.
Resolve consent capture/verification first.

---

## CONSENT CLEARED — 2026-09-12

Klinik Dr Inder has authorized external AI processing of clinic media **for
internal semantic indexing only** — **no publication, no external sharing**.
Existing publication rules are unchanged. On this basis the full-library
extraction run is authorized (external AI, internal-indexing purpose only).

Scope of this authorization:
- Permitted: sending clinic media to Anthropic Claude solely to produce internal
  semantic-search concepts stored in `asset_search_concepts_v2`.
- Not permitted by this clearance: publication, external sharing, or any
  outward-facing use of the media or derived content — governed by the existing
  (unchanged) publication rules.
- Only **decodable** assets are enqueued; quarantined files are held out until
  the forensic pass determines recoverability.
