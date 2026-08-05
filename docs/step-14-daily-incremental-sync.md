# Step 14 — Daily Incremental Synchronization

## Current status

BLOCKED after migration and fail-closed as of 2026-08-05. Migration
`202608050001` is deployed. The classifier, reconciliation primitive, bounded
retry helper, report writer, durable lock RPCs, command guard, and Windows
wrapper are implemented and unit-tested. The production adapter is not yet
complete for NEW and CHANGED files, so the task is not scheduled.

The CLI confirmed the linked project is exactly `wcqqjpndlwsvatjuqnol`
(`asset_management_ai`). Migration history and dry-run preview showed only the
Step 14 migration pending; deployment succeeded. Post-deployment verification
confirmed source_folders=3, source_files=886, assets=878, asset_sources=878,
and asset_destinations=878. The checkpoint columns are present and the new lock
table is empty.

A forced read-only scan reached all three sources and reconciled
1 + 300 + 585 = 886 identities with zero scan errors. All 886 classify
UNCHANGED after normalizing equivalent UTC timestamp representations. No live
NEW or CHANGED item was available, so the mutation-path A–J tests remain
incomplete.

## Architecture and reused components

Google Drive metadata scanning remains in `kdi_media.google_drive`; its selected
fields now include provider MD5 when available. `kdi_media.rules` remains the
only TAKE/SKIP policy. Content hashing and retry leases remain in
`kdi_media.step9_hashing`, canonical SHA-256 grouping and conflict-safe
asset/source linking remain in `kdi_media.step9_canonicalization`, and verified
resumable uploads remain in `kdi_media.step10_upload`. Existing `sync_runs`,
`scan_runs`, `source_files`, `assets`, `asset_sources`, `asset_destinations`, and
`migration_events` remain authoritative.

Step 14 adds only checkpoint columns to `source_files` and a project-wide
`synchronization_locks` row. Lock acquisition is atomic through
`acquire_synchronization_lock`; a different owner receives false. A lease of
60–21,600 seconds permits controlled stale-lock recovery. Release requires the
same run ID.

## Incremental comparison

The stable key is `(source_folder_id, google_file_id)`. Modified time, size,
MIME type, and available MD5 are compared before content is read. Outcomes are
NEW, CHANGED, UNCHANGED, INACCESSIBLE, and REMOVED_FROM_SOURCE. Missing provider
MD5 alone does not imply change. UNCHANGED content with trusted completed state
never reaches hashing or upload. Missing IDs are recorded only; originals and
master files are never deleted.

NEW and CHANGED items must pass the existing Step 8 rules, then the existing
leased SHA-256 worker. `SupabaseCanonicalRepository` reuses an asset on SHA-256
conflict and its source-link uniqueness prevents repeated relationships. Only a
new canonical asset may enter the Step 10 destination lifecycle, whose
idempotency key, Google app properties, claims, bounded attempts, recovery
lookup, and verification prevent repeat master files.

## Run lifecycle, checkpoint, retry, and reconciliation

A production run must create `sync_runs` with run type `DAILY_SYNC` and metadata
`run_type=incremental_sync`, trigger, dry-run flag, expanded counters, lock
events, and final reconciliation. Each source uses a `scan_runs` row. Each file
stores classification, processing status, attempt count (maximum five), retry
eligibility, sanitized last failure, and last success. Completed file states are
resume boundaries. Existing Step 9/10 leases remain the content/upload resume
boundaries.

Transient Drive 429/5xx, timeouts, and temporary database failures use at most
five attempts with 1, 2, 4, and 8 second exponential delays plus bounded jitter.
Permanent access/validation failures are not retried indefinitely.

Every relevant file must end as unchanged, skipped with reason, linked exact
duplicate, uploaded and verified, failed, awaiting retry, inaccessible, or
removed-record-only. Failures/retries/inaccessibility keep reconciliation from
being clean and prevent a successful run verdict.

## Commands

The current command is intentionally a non-zero fail-closed guard until the
production adapter and tests A–J pass:

```powershell
.\.venv\Scripts\python.exe -m scripts.run_incremental_sync sync --incremental
.\.venv\Scripts\python.exe -m scripts.run_incremental_sync sync --incremental --dry-run
```

Optional future routing flags are `--source-id`, `--run-id`, and `--trigger`.
JSON reports are written to `reports/step-14/`; scheduled logs go to
`reports/step-14/logs/`. No secrets are included.

## Windows Task Scheduler (not enabled)

Target: 21:00 Asia/Kuala_Lumpur (UTC+08:00), equivalent to 13:00 UTC. Windows
uses the machine timezone, so confirm it before creating a local 21:00 trigger.
After—and only after—A–J pass, an administrator may run:

```powershell
$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument '-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "C:\Users\Public\Asset_Management_AI\scripts\run_daily_incremental_sync.ps1"'
$trigger = New-ScheduledTaskTrigger -Daily -At '21:00'
Register-ScheduledTask -TaskName 'KDI-Central-Media-Daily-Incremental-Sync' -Action $action -Trigger $trigger -Description 'KDI daily incremental sync at 21:00 Asia/Kuala_Lumpur'
```

Manual fallback is the first command above. Disable with
`Disable-ScheduledTask -TaskName 'KDI-Central-Media-Daily-Incremental-Sync'`;
remove with `Unregister-ScheduledTask ...` only after explicit approval. The
wrapper validates the project virtual environment, sets the working directory,
captures logs, and propagates the worker exit code.

## Security and troubleshooting

Environment variables and existing ignored OAuth files remain the only secret
sources. Never place service-role keys or tokens in task arguments. RLS and
frontend authentication are unchanged. A status of `BLOCKED_CONFIGURATION`
means required variable names were absent; `BLOCKED_NOT_VERIFIED` means the
adapter/A–J gate remains incomplete. Both guarantee no Drive or database write.

## Test evidence

On 2026-08-05 the repository Python suite passed: 423 tests and 74 subtests;
the focused Step 14 suite contributed 8 tests. It covers the five metadata
classifications (including removed recording), trusted unchanged short-circuit,
bounded retry, outcome reconciliation/idempotence checks, atomic JSON report
writing, and static durable-lock/checkpoint contracts. Live A–J tests were not
completed. The live baseline/no-change checks passed, but no live
upload/idempotency claim is made and the schedule remains absent.

An unscoped `pytest` also collected legacy generated tests under ignored
`tmp/`; 436 passed and 7 failed because the managed sandbox denied those tests
write access to `tmp/dashboard_session_status.json`. The authoritative tracked
`tests/` suite passed completely.
