# Job 5.3 human review decisions

Status: **CONSOLIDATED HUMAN AUTHORIZATION AWAITED — NO DATABASE WRITE PERFORMED**

Purpose: `KDI AI Search V3 pilot indexing only`.

Scope excludes marketing use, public publishing, AI generation, general consent, download permission, arbitrary providers, and unlimited future third-party processing.

## Exact original pilot

| Pilot # | Asset ID | Filename | Media type | External AI | Manifest restriction | Clinical | Consent | Marketing | Existing authorization evidence |
|---:|---|---|---|---|---|---|---|---|---|
| 1 | `8a34e00e-8f33-4591-8692-fb9358cb72d6` | DSC00365.JPG | image/jpeg | NOT_REVIEWED | YES | UNCLASSIFIED; is_clinical NULL | UNKNOWN | UNKNOWN | none |
| 2 | `0260a986-3b66-42c6-9ec6-d6cc50a56584` | DSC05881.JPG | image/jpeg | NOT_REVIEWED | YES | UNCLASSIFIED; is_clinical NULL | UNKNOWN | UNKNOWN | none |
| 3 | `7f72217d-3839-4920-86b4-ccc33e9e3d95` | IMG_0531.MP4 | video/mp4 | NOT_REVIEWED | NO | UNCLASSIFIED; is_clinical NULL | UNKNOWN | UNKNOWN | none |
| 4 | `029c7315-b1a6-41f6-bb48-f1a91b492571` | IMG_0588.MP4 | video/mp4 | NOT_REVIEWED | YES | UNCLASSIFIED; is_clinical NULL | UNKNOWN | UNKNOWN | none |
| 5 | `930417e8-24c9-4d51-9d30-ce4da96638df` | IMG_0620.MP4 | video/mp4 | NOT_REVIEWED | YES | UNCLASSIFIED; is_clinical NULL | UNKNOWN | UNKNOWN | none |
| 6 | `3059f085-aaea-418a-8ef4-a8cba2393065` | IMG_0621.MP4 | video/mp4 | NOT_REVIEWED | YES | UNCLASSIFIED; is_clinical NULL | UNKNOWN | UNKNOWN | none |
| 7 | `babae120-9372-42ad-b535-02a3276ea2be` | IMG_1238.MP4 | video/mp4 | NOT_REVIEWED | NO | UNCLASSIFIED; is_clinical NULL | UNKNOWN | UNKNOWN | none |
| 8 | `9a4957bd-61bf-47dd-bd68-1debda5018eb` | IMG_1253.MP4 | video/mp4 | NOT_REVIEWED | YES | UNCLASSIFIED; is_clinical NULL | UNKNOWN | UNKNOWN | none |
| 9 | `c86344e9-5b32-4d86-9205-67952d508651` | IMG_3429.MP4 | video/mp4 | NOT_REVIEWED | NO | UNCLASSIFIED; is_clinical NULL | UNKNOWN | UNKNOWN | none |
| 10 | `444da390-0117-4380-8c87-d7c32f2903ff` | IMG_9871.MOV | video/quicktime | NOT_REVIEWED | NO | UNCLASSIFIED; is_clinical NULL | UNKNOWN | UNKNOWN | none |

## Restricted original assets

| Asset | Restriction source | Reason | Version/timestamp | Newer superseding evidence | Current decision state |
|---|---|---|---|---|---|
| DSC00365.JPG | `data/semantic_pilot_manifest.json` | `risk_flag=DO_NOT_SEND_EXTERNALLY`; `approved_for_external_ai=false` | manifest v1; no timestamp supplied | none found | BLOCKED |
| DSC05881.JPG | `data/semantic_pilot_manifest.json` | `risk_flag=DO_NOT_SEND_EXTERNALLY`; `approved_for_external_ai=false` | manifest v1; no timestamp supplied | none found | BLOCKED |
| IMG_0588.MP4 | `data/semantic_pilot_manifest.json` | `risk_flag=DO_NOT_SEND_EXTERNALLY`; `approved_for_external_ai=false` | manifest v1; no timestamp supplied | none found | BLOCKED |
| IMG_0620.MP4 | `data/semantic_pilot_manifest.json` | `risk_flag=DO_NOT_SEND_EXTERNALLY`; `approved_for_external_ai=false` | manifest v1; no timestamp supplied | none found | BLOCKED |
| IMG_0621.MP4 | `data/semantic_pilot_manifest.json` | `risk_flag=DO_NOT_SEND_EXTERNALLY`; `approved_for_external_ai=false` | manifest v1; no timestamp supplied | none found | BLOCKED |
| IMG_1253.MP4 | `data/semantic_pilot_low_risk_manifest.json` | `approved_for_external_ai=false` | manifest v1; no timestamp supplied | none found | BLOCKED |

The six restricted assets cannot receive a casual approval. An override requires explicit asset-specific superseding authorization that identifies the prior restriction, the reviewer and their authority, the reason, the timestamp, and the purpose/scope.

## Reviewer validation rule

Before any decision is applied, the supplied reviewer identity must resolve to an active record in `public.app_users` with `role=ADMIN`. The management role and active state will be recorded. A reviewer identity is not inferred or invented.

## Pending human fields

Reviewer: `[REQUIRED]`

Decision timestamp: server-recorded only after reviewer validation and exact pre-commit confirmation.

Per-asset decisions and reasons: `[REQUIRED]`

No authorization, replacement selection, or production media processing has occurred.

## Live reviewer validation

`kdimediaautomation@gmail.com` was revalidated against the live `public.app_users` table:

- exact matching rows: 1
- `role`: `ADMIN`
- `management_role`: `super_admin`
- `is_active`: `true`
- linked user UUID: present

Result: **AUTHORIZED REVIEWER VALIDATION PASS**. This validates identity/authority only and is not a media decision.

The operator explicitly directed all six restricted original assets to remain blocked and be replaced. The four unrestricted originals remain `NOT_REVIEWED` pending the single consolidated decision.

## Final explicit decisions

At `2026-08-20T04:49:35.1216176Z`, the validated reviewer explicitly approved the four unrestricted originals and six primary replacements for the purpose above. The six restricted originals were explicitly kept blocked. All six backup candidates were placed on HOLD and were not modified.

Approved originals: IMG_0531.MP4, IMG_1238.MP4, IMG_3429.MP4, IMG_9871.MOV.

Approved replacements: DSC03753.JPG, DSC08097.JPG, IMG_0493.MP4, IMG_1148.MP4, IMG_2963.MP4, IMG_1160.MP4.

Result: exactly 10 explicit approvals. Database representation is `external_ai_status=ALLOWED`; human decision representation is `APPROVE`. Each approved row records reviewer UUID/email, timestamp, exact reason, purpose, exclusions, authorization source, and replacement mapping in its authoritative access-control fields/metadata.
