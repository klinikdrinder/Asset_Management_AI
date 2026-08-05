# Step 14 — Daily Incremental Synchronization

## Status

COMPLETE on 2026-08-05 for production project `wcqqjpndlwsvatjuqnol`.
Migration `202608050001` remains deployed and unchanged. The production adapter,
controlled live Tests 1–10, final reconciliation, Windows scheduled task, and
manual scheduled-task execution all passed.

The controlled source `0e24d6b7-0429-461c-87b4-75471c759e4f` is disabled after
testing. The original three employee sources are the only active sources.

## Existing pipeline entry points reused

Step 14 orchestrates the existing implementations; it does not reimplement
their algorithms:

- Step 8 decision: `kdi_media.rules.evaluate_file(FileRuleInput)`.
- Step 9 SHA-256 and leases: `Step9HashWorker.process`,
  `SupabaseHashRepository`, `read_drive_snapshot`, and `iter_drive_content`.
- Existing SHA-256 asset lookup: `assets.content_hash`, followed by
  `SupabaseCanonicalRepository.create_or_reuse_asset` under the deployed unique
  constraint.
- Canonical grouping/creation: `build_canonical_groups` and
  `SupabaseCanonicalRepository`.
- Source relationship creation: `create_or_reuse_link`; CHANGED rows use the
  deployed one-current-link constraint and append an audit event before moving
  the current relationship. The previous asset and destination remain.
- Destination category: `route_category` and `resolve_category_folder`.
- Deterministic lifecycle creation: `prepare_lifecycle_initialization` and
  `SupabaseStep10Repository.initialize`.
- Claims/recovery: `claim_batch`, `renew`, `release`, `fail`, deployed claim
  RPCs, deterministic idempotency keys, and Drive app properties.
- Resumable upload: `DriveResumableTransfer` through
  `Step10UploadWorker.process`.
- Verification/recovery lookup: `lookup_destination_identity`,
  `verify_destination_metadata`, and the worker's `RECOVER` path.
- Migration events: `SupabaseStep10Repository.append_event` plus deployed
  Step 10 triggers.
- Reconciliation: `kdi_media.incremental_sync.reconcile` and durable
  `sync_runs`/`scan_runs` totals.

The former stop was `scripts/run_incremental_sync.py`: it wrote
`BLOCKED_NOT_VERIFIED` and exited 2 without invoking any of these entry points.
It now constructs `IncrementalSyncRunner`, which scans/classifies and delegates
only NEW/CHANGED rows to `ProductionSyncAdapter`.

## Adapter behavior

`ProductionSyncAdapter` accepts a run ID, source-folder row, persisted
source-file row, Drive metadata, NEW/CHANGED classification, and dry-run flag.
Its outcomes are UNCHANGED, SKIPPED, REUSED_EXISTING_ASSET,
UPLOADED_AND_VERIFIED, FAILED_RETRYABLE, and FAILED_FINAL.

NEW files are evaluated by Step 8, hashed by Step 9, canonicalized, linked, and
uploaded only when the SHA-256 is unique. Existing assets gain one idempotent
source link and no destination upload.

CHANGED files record prior asset/hash/version context, reset only current hash
state, re-run Steps 8–10, and move the one current source relationship after
the new canonical result is durable. Previous asset and verified destination
rows are never overwritten or deleted.

Dry-run performs metadata scanning, classification, rules, reporting, and
reconciliation only. It creates no runs, scans, locks, checkpoints, hashes,
assets, relationships, destinations, uploads, or paid-service calls.

Resume is database-authoritative. Persisted HASHED state is reused; canonical
and relationship uniqueness reconciles database-write-before-crash cases;
deterministic lifecycle IDs and Drive app properties recover upload-before-
verification cases; expired claims and synchronization locks are recoverable.

## Commands

```powershell
# Live all active sources
.\.venv\Scripts\python.exe -m scripts.run_incremental_sync sync --incremental

# Metadata-only dry run
.\.venv\Scripts\python.exe -m scripts.run_incremental_sync sync --incremental --dry-run

# One approved source
.\.venv\Scripts\python.exe -m scripts.run_incremental_sync sync --incremental --source-id UUID
```

Reports are written to `reports/step-14/`. Scheduled logs are written to
`reports/step-14/logs/`. Errors and event details are sanitized.

## Windows Task Scheduler

Task: `KDI-Central-Media-Daily-Incremental-Sync`

- Trigger: daily at 21:00 Singapore Standard Time (UTC+08:00), equivalent to
  21:00 Asia/Kuala_Lumpur.
- Action: non-interactive PowerShell running
  `scripts/run_daily_incremental_sync.ps1`.
- Multiple instances: IgnoreNew.
- Start when available: enabled.
- Battery execution: enabled.
- Execution limit: three hours.
- Principal: current Windows user, Interactive logon, Limited run level.
- Next verified run: `2026-08-05T21:00:00+08:00`.

The manual Scheduler trigger at `2026-08-05T11:53:43+08:00` returned exit code
0, logged clean run `76a9bb8d-90c6-4b30-9e2e-e70737d17933`, reconciled 886
UNCHANGED files, and released the lock.

Disable without deleting:

```powershell
Disable-ScheduledTask -TaskName 'KDI-Central-Media-Daily-Incremental-Sync'
```

## Verification summary

- Tracked tests: 433 passed plus 74 subtests.
- Initial and final original-source live runs: 886 UNCHANGED, zero uploads,
  zero contradictions, zero scan errors.
- Unique, exact-duplicate, CHANGED, SKIP, transient retry, interruption/resume,
  overlap rejection, owner release, and stale-lock recovery all passed live.
- Controlled final counts: 4 source folders (three active), 890 source files,
  881 assets, 881 relationships, and 881 destinations.
- Lock table after every final check: zero rows.

See `reports/step-14-completion-report.md` for exact controlled filenames,
Drive IDs, hashes, database IDs, run IDs, and destination IDs.
