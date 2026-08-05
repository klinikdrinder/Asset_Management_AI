# Step 14 completion report

Status: **COMPLETE** (2026-08-05)

Production project: `wcqqjpndlwsvatjuqnol` (`asset_management_ai`). Migration
`202608050001_add_step14_incremental_sync.sql` was already deployed; no database
migration or frontend file changed in this continuation.

## Production adapter

`src/kdi_media/production_sync_adapter.py` composes the existing Step 8 rule
evaluator, Step 9 leased SHA-256 worker/canonical repository, and Step 10
deterministic lifecycle/resumable upload/verification worker.
`src/kdi_media/daily_sync.py` owns run/scan rows, lock RPCs, metadata-only
classification, checkpoints, totals, and final reconciliation. The CLI now
executes this runner instead of the old fail-closed stub.

## Controlled fixture

Controlled source folder:

- name: `KDI Step 14 Controlled Sync Test`
- Drive folder ID: `1Z164RcxLFgnxcb_QsE7atSeBy4Daa8F7`
- source-folder ID: `0e24d6b7-0429-461c-87b4-75471c759e4f`
- final state: disabled

Files:

| Purpose | Filename | Drive file ID | SHA-256 |
|---|---|---|---|
| Unique v1 / changed v2 | `step14-unique.png` | `12T84bV4ihNAxDp9w5KR4LX0e36_TOW-R` | v1 `41c02ae07519ea01cdd4095d97c0e57c27ac03944c8788b6f26751a88042445f`; v2 `d0179b7cfdb20065ab660278e78e41118c4ba7883590a477cac3e7fbe53de0b6` |
| Exact duplicate v1 | `step14-byte-identical-copy.png` | `1Kqp1cpuL3dPvPd9XZR6vkcS6VQPtax3_` | `41c02ae07519ea01cdd4095d97c0e57c27ac03944c8788b6f26751a88042445f` |
| SKIP | `step14-unsupported.txt` | `1ZVeC8HOh8NTi0P8GRFV65kUoOi1PBuXM` | not hashed by pipeline; fixture SHA-256 `725943df0dfdf2d3bd601034bf6ce20c24a249b96317881532b960e5f3a78566` |
| Retry | `step14-retry.png` | `161bwP75Nz0DFmFtFDN5rrzdn1TrZ1Wjr` | `557f49a8b197729004e7899af89e01d8e59d89e00924032d8fd33728ed06b4db` |

Database identities:

| Content | Source file ID | Asset ID | Relationship ID | Lifecycle ID | Destination Drive ID |
|---|---|---|---|---|---|
| Unique v1 / duplicate canonical | duplicate source `a6de1ac8-7604-4da5-861d-b7c0437de28a` | `c89e88bf-39fb-4bd6-8ed2-dc4cb9e3901c` | `acf33c27-d6e4-46fb-980e-a3f7485147d2` | `79259fbd-ea3f-5e79-b55f-cdd604b7b1c5` | `104ZRQ1kp9m9rf2rxJmiVb3-jDobpsyKD` |
| Changed v2 | `b28c74fb-20ec-4acd-90e3-db50e5e68276` | `2746a447-4b32-415c-971e-ed3878176848` | `0ec9b63b-9ba9-441d-83d0-5ab98b3fa71a` | `5027e2e6-58e8-55bb-a0f6-73cbdfaec441` | `1DY0wX6gAvXi0mgzSyCwcPOSpOnD_gOzd` |
| Retry fixture | `20dc7d52-1843-4249-a5d8-0851d7f4ba21` | `1e6651de-6ffb-4565-9094-b1c5cc9c09b8` | `d260e0a8-1f5d-4095-b6a5-5df73b143534` | `291b263b-92ce-589e-8ff7-571a9a209f9b` | `194PSKXpBPZun7MpAddYCUze-VlEfscgQ` |
| SKIP | `def772cd-ed3c-4087-8d37-89b895c67ef4` | none | none | none | none |

## Live Tests 1–10

1. Existing no-change baseline: run `a20f3382-1fe2-407b-8612-8f6db569ffa7`
   completed with 886 UNCHANGED and zero hash/upload/asset/link/destination
   effects. Counts remained 3 / 886 / 878 / 878 / 878.
2. Unique supported file: run `0b1d4623-ea60-4141-9aea-22c8193904f6`
   classified one NEW, applied TAKE, hashed once, created one asset/link/
   lifecycle, uploaded once, and verified the destination.
3. Repeat without change: run `c33c8a6b-2bb0-4eed-8cbb-f2aad6e1c4bd`
   returned one UNCHANGED and zero work counters; all IDs stayed stable.
4. Exact duplicate: the first run reached durable hash/link creation and then
   stopped on a legacy audit-field compatibility error. Run
   `9920132f-7b81-42f7-9fbe-b121e305093e` resumed from the database checkpoint,
   reused asset `c89e88bf…`, created no asset/destination/upload, and finalized
   the existing relationship. Run `a57b00a1-db0c-4e82-87b8-7a8d3b5f7b18`
   then returned two UNCHANGED with zero repeated work.
5. Changed file: run `23467823-8ecc-471e-8831-1a0d1294355a` classified one
   CHANGED, evaluated the new SHA-256, created and verified the v2 asset/master,
   and moved the current source relationship. The v1 asset, v1 destination,
   exact-duplicate source relationship, and append-only SOURCE_CHANGED event
   remain.
6. SKIP: run `ceb860d0-fcf2-4946-9eff-6c51e0e33062` recorded
   `UNSUPPORTED_EXTENSION`, hash status NOT_STARTED, and no asset/link/upload.
   Final fixture run `f88ac64d-aa99-4755-98f4-255f88846c23` returned all four
   files UNCHANGED with zero work.
7. Retryable failure: run `489c3603-8560-4804-bb3a-9da3185572d3` injected one
   controlled `RetryableHashingError`; the existing bounded retry performed one
   retry, then hashed/uploaded/verified exactly once.
8. Interruption/resume: Test 4 supplied a real database-write-before-process-
   stop boundary. Resume reused the persisted HASHED state and relationship and
   did not repeat content download or upload. Existing Step 10 marker recovery
   and verified-lifecycle short circuit are covered by focused tests.
9. Overlap lock: first acquire, second-owner rejection, owner release,
   acquisition after release, stale takeover, and final release all returned
   true as expected. Test run IDs: `37523224-86d1-4430-a51f-b8f923d9d087`,
   `0ce8ed37-7056-46bb-aacd-da6173bb4e93`,
   `fb7ec498-e354-4d66-b9e0-06f68a739118`, and
   `5aae712e-55c9-43ed-b4de-a5b3e2b68a4b`. Remaining locks: zero.
10. Final production no-change: after disabling the controlled source, run
    `c6f280fc-91f5-431c-bbe9-94d45d2db200` reconciled the original three
    sources as 886 UNCHANGED with zero work and zero contradictions.

Final controlled evidence counts are source_folders=4 (three active),
source_files=890, assets=881, asset_sources=881, and asset_destinations=881.
The net +4/+3/+3/+3 matches four source files, one SKIP, one duplicate, and
three unique content versions.

## Scheduling

Task `KDI-Central-Media-Daily-Incremental-Sync` is enabled and Ready. It runs
daily at 21:00 Singapore Standard Time / Asia/Kuala_Lumpur using
`scripts/run_daily_incremental_sync.ps1`. Battery starts are allowed,
StartWhenAvailable is enabled, and overlapping instances are ignored.

Manual Task Scheduler execution began `2026-08-05T11:53:43+08:00`, returned
exit code 0, and produced log
`reports/step-14/logs/scheduled-20260805-115346.log`. Scheduled run
`76a9bb8d-90c6-4b30-9e2e-e70737d17933` reconciled 886 UNCHANGED with zero work
and zero locks remaining. Next run: `2026-08-05T21:00:00+08:00`.

## Automated verification

Tracked suite: 433 tests and 74 subtests passed. Focused coverage includes NEW,
CHANGED, SKIP, existing-canonical reuse, unique upload, relationship and
destination idempotency, persisted-hash/crash recovery, dry-run non-mutation,
retry classification, counters, and reconciliation.

No credentials, OAuth files, source media, or test secrets are tracked.
