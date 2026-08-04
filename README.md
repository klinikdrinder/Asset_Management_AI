# KDI Central Media Library

This pilot migrates one configured Google Drive source folder into the KDI
Master destination.

It recursively scans nested folders, records file metadata in Supabase, applies
TAKE/SKIP rules, detects exact duplicates using both `md5Checksum` and file
size, and copies only unique supported files.

The workflow never moves, edits, or deletes source files. In live mode, it uses
Google Drive API v3 `files.copy`, so the original files remain unchanged.

## Pilot scope

Supported file types:

- JPG
- JPEG
- PNG
- WEBP
- MP4
- MOV
- PDF
- PPTX

Temporarily skipped:

- Google Docs
- Google Sheets
- Google Slides
- Google Drive shortcuts
- HEIC
- Unsupported file formats

The canonical format policy lives in `src/kdi_media/rules.py`. It is the
single source of truth for file eligibility, so formats can be enabled,
disabled, or added later without maintaining multiple allowlists.

The currently approved extension/MIME pairs are:

| Category | Extension | Required MIME type |
| --- | --- | --- |
| Image | `jpg` | `image/jpeg` |
| Image | `jpeg` | `image/jpeg` |
| Image | `png` | `image/png` |
| Image | `webp` | `image/webp` |
| Video | `mp4` | `video/mp4` |
| Video | `mov` | `video/quicktime` |
| Document | `pdf` | `application/pdf` |
| Document | `pptx` | `application/vnd.openxmlformats-officedocument.presentationml.presentation` |

All eight formats are accepted for inventory, migration, and exact duplicate
detection. PDF and PPTX content analysis is not implemented yet: this phase
does not extract PDF text, extract PPTX slides, generate document previews, or
perform semantic indexing.

An actual PPTX binary file is distinct from a Google Slides item. PPTX uses the
Open XML presentation MIME type listed above, while Google Slides uses
`application/vnd.google-apps.presentation`. Google-native Docs, Sheets, and
Slides remain unsupported and are never exported automatically. HEIC also
remains unsupported.

## Current Supabase state

The current hosted Supabase project already contains:

- The `source_folders` table
- The first three approved Google Drive source-folder records

The project must preserve this existing data.

Do not reset the hosted Supabase project.

## Supabase migrations

The migration files are:

1. `202607280001_create_foundation_schema.sql`
2. `202607280002_seed_three_source_folders.sql`

### Migration 001

`202607280001_create_foundation_schema.sql`

This migration preserves the existing `source_folders` table and ensures the
required supporting objects exist:

- `set_updated_at()` function
- Indexes
- Updated-at trigger
- Row Level Security
- Service-role permissions

It must not drop or replace the existing `source_folders` table.

### Migration 002

`202607280002_seed_three_source_folders.sql`

This migration registers the first three approved source folders.

It must be idempotent, meaning it can be run again without creating duplicate
folder records.

It must use the current `source_folders` column names, including:

- `account_name`
- `active`
- `google_folder_id`

## Applying the migrations

For the current hosted Supabase project, review and run the required SQL
through:

```text
Supabase
to SQL Editor
to New query
```

Do not run `supabase db reset` against the hosted project. That command is only
appropriate for a disposable local development database.

### Verify the live foundation before deployment

1. Open the Supabase SQL Editor.
2. Create a new query named `foundation verification`.
3. Paste the contents of
   `supabase/verification/verify_live_foundation.sql`.
4. Run the verification query.
5. Copy the result sets for review.
6. Do not rerun migration 001 yet.

Before starting the Python workflow, confirm these tables exist:

- `source_folders`
- `scan_runs`
- `source_files`

Also confirm that the three approved folder records remain inside
`source_folders`.

## Google OAuth setup

1. Open the Google Cloud project for the KDI migration system.
2. Enable Google Drive API.
3. Configure the OAuth consent screen.
4. Create an OAuth 2.0 Desktop application client.
5. Download the OAuth client JSON.
6. Store it securely, for example:

```text
secrets/credentials.json
```

7. Set `GOOGLE_CREDENTIALS_PATH` to that local path.
8. Complete the browser authorization on the first run.
9. Store the generated token securely, for example:

```text
secrets/token.json
```

10. Set `GOOGLE_TOKEN_PATH` to that token path.

The OAuth credentials and token must never be committed to GitHub.

## Google Drive permissions

The authenticated automation Google account must have:

- Viewer access to the configured source folder
- Editor access to the KDI Master destination folder

A Google Drive folder URL or folder ID stored in Supabase does not
automatically grant access.

## Environment configuration

Copy the example environment file:

```powershell
Copy-Item .env.example .env
```

Edit the local `.env` file and provide the required values:

```dotenv
SUPABASE_URL=
SUPABASE_SERVICE_ROLE_KEY=

GOOGLE_CREDENTIALS_PATH=secrets/credentials.json
GOOGLE_TOKEN_PATH=secrets/token.json

DESTINATION_FOLDER_ID=
SOURCE_FOLDER_NAME=

DRY_RUN=true
```

The `SOURCE_FOLDER_NAME` value must exactly match the `source_name` stored in
Supabase.

The Supabase service-role key is a server-side secret. Keep it only in the
local `.env` file. Never expose it in frontend code, screenshots, logs,
documentation, GitHub, or public messages.

## Secret protection

The project `.gitignore` must exclude at least:

```gitignore
.env
.env.*
!.env.example

credentials.json
token.json
secrets/

.venv/
__pycache__/
*.py[cod]
```

Before committing anything, run:

```powershell
git status
```

Confirm that none of these appear as tracked or untracked files:

- `.env`
- `credentials.json`
- `token.json`
- `secrets/`
- `.venv/`

## Python installation

Run these commands from the project root:

```powershell
cd C:\Users\Public\Asset_Management_AI

py -m venv .venv

.\.venv\Scripts\Activate.ps1

python -m pip install --upgrade pip

python -m pip install -r requirements.txt
```

If PowerShell blocks the activation script, use:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\.venv\Scripts\Activate.ps1
```

You can also use the virtual environment without activation by running its
Python executable directly:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m compileall src
```

## Validate the Python code

Run the syntax check:

```powershell
python -m compileall src
```

Set the Python package path:

```powershell
$env:PYTHONPATH = "src"
```

Run the import check:

```powershell
python -c "from kdi_media.main import main; print('Import OK')"
```

Do not continue until both checks pass.

## Run the dry run

Keep this setting in `.env`:

```dotenv
DRY_RUN=true
```

Then run:

```powershell
$env:PYTHONPATH = "src"
python -m kdi_media.main
```

Dry-run mode:

- Reads the configured source folder from Supabase
- Authenticates with Google Drive
- Recursively scans nested folders
- Reads file metadata
- Applies TAKE/SKIP rules
- Checks for exact duplicates
- Writes scan and file results into Supabase
- Does not copy files into KDI Master

After the dry run, review:

- Console output
- `scan_runs`
- `source_files`
- The updated source-folder access status

Before live migration, confirm:

- The correct source folder was scanned
- Files were discovered
- TAKE/SKIP decisions are correct
- Duplicate results are reasonable
- `files_uploaded` is zero
- Any failed files are understood

## TAKE/SKIP rules

Eligibility is evaluated by the canonical, configuration-driven rule engine in
`src/kdi_media/rules.py`. Extension and MIME type must match an approved pair;
an approved MIME type does not compensate for a missing or unsupported
extension.

Supported files receive:

```text
decision = TAKE
```

Unsupported files receive:

```text
decision = SKIP
processing_status = SKIPPED
```

Skipped files remain recorded in Supabase for reporting and auditing but are
not copied.

## Exact duplicate detection

For normal binary files, exact duplicate detection uses:

```text
md5Checksum + file size
```

Filename alone is never used for exact duplicate detection.

A file is treated as an exact duplicate only when:

- `md5_checksum` matches
- `size_bytes` matches
- A matching record has already been uploaded successfully

Duplicate detection should work across all registered source folders.

Google-native files such as Google Slides do not always provide a standard MD5
checksum and are temporarily skipped during the pilot.

## Run the live migration

After reviewing a successful dry run, change:

```dotenv
DRY_RUN=false
```

Then run:

```powershell
$env:PYTHONPATH = "src"
python -m kdi_media.main
```

In live mode, the workflow:

1. Reads the configured source folder from Supabase.
2. Checks Google Drive access.
3. Recursively scans nested folders.
4. Records file metadata.
5. Applies TAKE/SKIP rules.
6. Checks for exact duplicates.
7. Copies unique supported files into the configured KDI Master destination.
8. Saves destination file IDs and links.
9. Records uploaded, duplicate, skipped, inaccessible, and failed outcomes.
10. Continues processing when one individual file fails.

## Expected file statuses

Successful unique file:

```text
decision = TAKE
processing_status = UPLOADED
destination_file_id = populated
destination_web_view_link = populated
uploaded_at = populated
```

Exact duplicate:

```text
decision = TAKE
processing_status = DUPLICATE
duplicate_of_source_file_id = populated
```

Unsupported file:

```text
decision = SKIP
processing_status = SKIPPED
skip_reason = populated
```

Failed file:

```text
decision = TAKE
processing_status = FAILED
processing_error = populated
```

## Source-file protection

The migration workflow must never:

- Delete a source file
- Move a source file
- Rename a source file
- Modify a source file
- Replace a source file
- Change source-folder permissions

Live mode creates a separate copy inside the KDI Master destination.

## Pilot completion criteria

The pilot is complete when one real source folder successfully proves:

- Source-folder access
- Nested-folder scanning
- Metadata recording
- TAKE/SKIP decisions
- Exact duplicate detection
- Unique file copying
- Destination-link recording
- Failure logging
- Original source-file preservation

After the first folder is verified, repeat the workflow for the other two
registered source folders before adding the remaining company Google Drive
links.

## Bulk source onboarding and multi-source processing

Step 8.5 accepts source-folder manifests through CSV and processes registered
sources independently through access verification, recursive metadata scan,
local report creation, inventory import, canonical Step 8 rules, and
reconciliation.

Before onboarding a source, share the Google Drive folder with:

```text
kdimediaautomation@gmail.com
```

Viewer access is sufficient for metadata verification and scanning. The
multi-source scanner uses the Google Drive read-only OAuth scope and does not
download file content or modify Drive files.

### CSV preparation

Start with `config/source_folders.example.csv`. The required columns are:

- `source_name`
- `account_name`
- `folder_url`
- `notes`
- `active`

Optional columns are:

- `expected_folder_id`
- `clinical_content`
- `processing_enabled`

Use a standard HTTPS Google Drive folder URL:

```text
https://drive.google.com/drive/folders/FOLDER_ID
```

Folder IDs must be unique within one CSV. Boolean values accept `true` or
`false` (also `1`/`0` and `yes`/`no`). Do not place credentials, OAuth tokens,
patient details, or private account secrets in the manifest.

Validate a manifest locally without Supabase or Google Drive access:

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe scripts\onboard_source_folders.py `
  --csv "config\source_folders.example.csv" `
  --validate-only
```

Preview inserts, updates, unchanged rows, and rejected rows using read-only
Supabase access:

```powershell
.\.venv\Scripts\python.exe scripts\onboard_source_folders.py `
  --csv "config\source_folders.csv" `
  --dry-run `
  --continue-on-error
```

Future approved registration:

```powershell
.\.venv\Scripts\python.exe scripts\onboard_source_folders.py `
  --csv "config\source_folders.csv" `
  --execute `
  --continue-on-error
```

### Processing registered sources

Dry-run one registered source:

```powershell
.\.venv\Scripts\python.exe scripts\process_registered_sources.py `
  --source-folder-id "<source-folder-uuid>" `
  --dry-run
```

Future approved processing of active sources:

```powershell
.\.venv\Scripts\python.exe scripts\process_registered_sources.py `
  --all-active `
  --limit 3 `
  --execute `
  --continue-on-error
```

Retry a source with a recorded failed or inaccessible checkpoint only after
the cause has been reviewed:

```powershell
.\.venv\Scripts\python.exe scripts\process_registered_sources.py `
  --source-folder-id "<source-folder-uuid>" `
  --execute `
  --retry-failed
```

The default concurrency is one source. `--max-concurrent-sources 2` must be
selected explicitly, and values above two are rejected. Never process all
company drives simultaneously.

Source-specific output is stored under:

```text
tmp/multi-source/<google_folder_id>/
```

Each source receives non-overwriting timestamped recursive JSON/CSV reports,
processing summaries, sanitized error reports when necessary, and an atomic
`checkpoint.json`. Completed report/import stages are reused when their files
and report fingerprint remain valid. Inventory writes use batches of 100,
source identity is protected by `(source_folder_id, google_file_id)`, and a
completed scan run is reused by report fingerprint.

Transient failures use bounded exponential backoff of 1, 2, 4, 8, and 16
seconds. Validation, authentication, and permission failures are not retried
automatically. A source failure is isolated; `--continue-on-error` permits the
next selected source to proceed.

Step 8.5 creates no assets or `asset_sources`, performs no media copying, and
does not use direct SQL. Execute modes can write source registration,
inventory, scan-run, and decision metadata only after explicit approval.
