# KDI real semantic pilot readiness

This document describes a selection/readiness exercise only. No production
asset has been sent to an AI provider and no semantic row has been written.

## Population audit (2026-08-10)

- Assets: 881; VERIFIED destination rows: 881; canonical assets with VERIFIED
  destinations: 881.
- Media: 293 images, 585 videos, 3 documents.
- Extensions: 584 MP4, 251 JPG, 39 JPEG, 3 PNG, 2 PDF, 1 MOV, 1 PPTX.
- Content hashes: 881 distinct hashes; zero duplicate hash rows in this
  catalogue snapshot.
- Sizes: 43 bytes to 87,842,167 bytes. The three 43–47 byte PNGs are controlled
  synchronization fixtures, not useful pilot media. The ten largest files are
  camera-named MP4s (31–88 MB).
- Existing video duration is not stored in the catalogue metadata. Read-only
  Drive metadata supplied duration for all 13 selected videos (2.3–189.3 s).
- Descriptive filenames are exceptional: only two catalogue filenames contain
  obvious clinical/search terms, and both are PDFs. The selected media therefore
  deliberately exercises weak camera/timestamp filenames.

## Selection and privacy result

The manifest at `data/semantic_pilot_manifest.json` contains seven images and
thirteen MP4 videos. Every row defaults to `approved_for_external_ai=false`.

All real JPEG images are sourced from the patient-review collection. Local,
authenticated poster inspection also showed that 12 of the selected videos
contain identifiable patients receiving treatment. Those rows are marked
`DO_NOT_SEND_EXTERNALLY`. The remaining staff-facing clip is `NEEDS_REVIEW`.
No row is automatically classified as low-risk or treated as consent. This is
a technical screening flag, not a legal decision.

## Fail-closed execution contract

`scripts/run_semantic_indexing.py` now requires `--manifest` in every mode.
`--execute` additionally requires `--approved-only`; only rows explicitly set
to true may be selected. Requested IDs outside that approved set are rejected,
duplicates are collapsed, manifests are capped at 20 unique assets, unknown or
unsupported IDs fail, and a VERIFIED destination is required.

Dry-run is always provider-free and read-only, even if credentials are present:
AI calls, database writes, semantic inserts, and embedding inserts are all zero.
There is no missing-manifest fallback to bulk discovery.

## Media preparation controls

- Images: one canonical image byte stream is supplied to `DescriptionProvider`.
- Videos: at most 6 evenly spaced JPEG frames, sampled between 5% and 95% of
  duration; an unreadable timestamp is skipped. Each generated frame is bounded
  to 1,600 × 1,600 pixels while preserving aspect ratio.
- Transcript: whitespace-normalized and capped at 2,000 characters; absent in
  the current selected asset metadata.
- Temporary video and frame files live in `TemporaryDirectory` and are removed
  on exit.
- Retry delays are 1, 2, 4, 8, and 16 seconds with jitter; permanent provider
  failures are not retried.
- A one-hour video still yields at most six provider image inputs.

Current operational gaps: the worker host has no `ffmpeg`/`ffprobe` on PATH, so
live video frame extraction cannot start yet; execute now fails before semantic
writes when a selected video requires them. Video input is currently fetched as
a full canonical file before local extraction, and original still images have no
explicit pixel-dimension cap. These are activation preflight items, not reasons
to weaken the allowlist.

## Metadata and searchable text contract

The structured output contains only `content_type`, `treatment`, `subject`,
`doctor_name`, `ai_description`, plus display-only `short_caption`. Patient
identity is never inferred; uncertain doctor/treatment values are null.

Embedding text is deterministic and contains only content type, treatment,
subject, doctor name, and AI description. `short_caption` is excluded. Filename
remains an independent hybrid-ranking signal.

## Provider boundaries

`DescriptionProvider.describe_media` accepts filename, MIME type, media category,
one image or bounded representative frames, and an optional bounded transcript.
It returns validated `StructuredMetadata` plus optional cost. Configuration is
selected by `AI_DESCRIPTION_PROVIDER`. Active production configuration uses local
Ollama at `http://127.0.0.1:11434` with `qwen3-vl:2b`. The registered OpenAI
adapter remains explicit and optional.

`EmbeddingProvider.embed_text` accepts normalized searchable text and returns a
numeric vector plus optional cost. The vector must exactly match the configured
production dimension (1024). Configuration is selected by
`AI_EMBEDDING_PROVIDER`; production uses `qwen3-embedding:0.6b` through local
Ollama. Models are stored at `E:\KDI_Local_AI\models`. AI concurrency is one,
and `keep_alive: 0` ensures vision and embedding models run sequentially rather
than remaining resident together. The registered OpenAI adapter additionally
uses `OPENAI_API_KEY`, `OPENAI_EMBEDDING_MODEL`, `OPENAI_EMBEDDING_DIMENSIONS`,
and `OPENAI_EMBEDDING_VERSION` when it is explicitly selected.

The worker loads the repository-root `.env`. Provider adapters are replaceable
behind these protocols without changing the database or search architecture.
Provider errors are classified retryable/permanent; worker retry/backoff is
bounded. The OpenAI adapter has an explicit 10-second connection timeout and
30-second request timeout, with SDK retries disabled so only the worker's bounded
retry policy applies.

## Commands prepared (do not run until their prerequisites are approved)

### Human-curated search-only seed

`data/semantic_manual_search_pilot.json` is a separate manual semantic-search
template. It reads no media and never constructs a vision/description provider.
Every entry must retain exactly the approved semantic fields plus `reviewed_by`
and timezone-qualified `reviewed_at`; blank optional treatment, subject, and
doctor fields remain null and are never inferred. Description provenance is
stored as `manual / human-reviewed / manual-v1`, while embeddings remain local
Ollama `qwen3-embedding:0.6b` at exactly 1024 dimensions.

Read-only validation (no embeddings and no writes):

```powershell
$env:PYTHONPATH='src'
.\.venv\Scripts\python.exe scripts\import_manual_semantic_pilot.py --dry-run --manifest data\semantic_manual_search_pilot.json
```

Only after every entry has been completed and reviewed, the explicit import
shape is:

```powershell
$env:PYTHONPATH='src'
.\.venv\Scripts\python.exe scripts\import_manual_semantic_pilot.py --execute --confirm-manual-import --manifest data\semantic_manual_search_pilot.json
```

### Separate local-only approval

Local Ollama processing uses `data/semantic_local_pilot_manifest.json`, not the
external-provider manifest flags. An asset is selectable only when
`approved_for_local_ai` is explicitly `true` and its approval reason, reviewer,
and ISO-8601 timestamp are populated. Missing/false local approval blocks local
processing. It does not change or imply `approved_for_external_ai`, clinical
consent, marketing approval, or patient-use permission.

Local execution additionally requires `--local-only`, both configured providers
must identify as `ollama`, and clinical-tier manifests retain the independent
`--confirm-clinical-local-processing` privacy gate. Before provider construction
or semantic writes, the command requires available host RAM to meet
`LOCAL_AI_MIN_AVAILABLE_RAM_MB` (default/example: 3072 MB). Capacity failure is
reported as `LOCAL_CAPACITY_PREFLIGHT_FAILED` with zero writes and no provider
invocation.

The initial local manifest is a human-review template: all entries are false and
no reviewer identity has been fabricated. Catalog metadata did not establish a
safe image candidate, so one must be separately reviewed before the desired
image-first pilot can run.

After human approval and sufficient available RAM, the controlled local command
shape is:

```powershell
$env:PYTHONPATH='src'
.\.venv\Scripts\python.exe scripts\run_semantic_indexing.py --execute --local-only --tier low-risk --manifest data\semantic_local_pilot_manifest.json --asset-id <LOCALLY_APPROVED_ASSET_UUID> --limit 1 --batch-size 1
```

Safe provider-free manifest check:

```powershell
$env:PYTHONPATH='src'
.\.venv\Scripts\python.exe scripts\run_semantic_indexing.py --dry-run --manifest data\semantic_pilot_manifest.json --limit 20
```

Synthetic description and embedding connectivity—each command performs exactly
one call and writes no production row:

```powershell
$env:PYTHONPATH='src'
.\.venv\Scripts\python.exe scripts\test_ai_provider_connectivity.py --description --execute-live --confirm-synthetic
.\.venv\Scripts\python.exe scripts\test_ai_provider_connectivity.py --embedding --execute-live --confirm-synthetic
```

After human review changes the chosen manifest row to approved, one image or one
video uses the same fail-closed shape:

```powershell
$env:PYTHONPATH='src'
.\.venv\Scripts\python.exe scripts\run_semantic_indexing.py --execute --approved-only --tier low-risk --manifest data\semantic_pilot_low_risk_manifest.json --asset-id <APPROVED_ASSET_UUID> --limit 1 --batch-size 1 --max-cost <APPROVED_USD_LIMIT>
```

Full approved pilot (still capped by the 20-row manifest):

```powershell
$env:PYTHONPATH='src'
.\.venv\Scripts\python.exe scripts\run_semantic_indexing.py --execute --approved-only --tier low-risk --manifest data\semantic_pilot_low_risk_manifest.json --limit 20 --batch-size 5 --max-cost <APPROVED_USD_LIMIT>
```

## Pilot search evaluation set

These queries target observed procedure/patient/staff content without inventing
an unsupported treatment or doctor label:

1. patient receiving a facial treatment
2. clinician performing a treatment procedure
3. woman receiving a clinic procedure
4. male patient during treatment
5. treatment equipment being used on a patient
6. close-up clinical procedure
7. staff member speaking to camera
8. patient treatment result photo
9. one month treatment progress photo
10. before and after treatment result
11. short procedure video
12. longer treatment-room video
13. only videos
14. only images
15. newest first
16. no testimonials
17. doctor explaing treatment (intentional typo; expected diagnostic/no known match)
18. Datuk Dr Inder (exact-name diagnostic; no identity is assumed from imagery)
19. iGraft Long Hair FUE (exact-treatment diagnostic; no treatment is assumed)
20. purple spaceship cooking noodles (nonsense control)

Follow-ups 13–16 must retain the preceding semantic request. Exact doctor and
treatment cases are evaluated only if reviewed AI metadata actually supports
them; absence is not counted as a ranking failure.

## Acceptance criteria

- No fabricated doctor/treatment/patient identity; descriptions are substantially
  accurate and captions useful.
- Each approved asset produces one semantic row and one compatible 1024-vector;
  unchanged reruns cause no paid description or embedding call.
- All writes remain confined to the approved manifest IDs.
- Where a relevant pilot asset exists, it normally appears in leading results;
  exact supported doctor/treatment metadata receives its existing structured
  boost.
- Conversational refinements retain previous intent.
- Provider/query-embedding failure continues through text, metadata, and filename
  hybrid fallback.
- Ranking weights are not changed until real result evidence exists.
