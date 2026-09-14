# Job 5.2 pilot decision matrix

All ten rows are the live `pilot_v1` AI-profile set. No authoritative reviewer decision exists. Rechecking the manifests reveals six overlaps with explicit `approved_for_external_ai: false` evidence, not four: Job 5.1 undercounted DSC00365.JPG and DSC05881.JPG even though it correctly reported both as manifest members. All six must not be approved without a newer, explicit asset-specific authorization by the media/data owner or delegated clinical/privacy authority.

| # | Asset | File | Type | Clinical | Consent | Marketing | External AI | Manifest/evidence | Blocking evidence | Existing review | Human action |
|---:|---|---|---|---|---|---|---|---|---|---|---|
| 1 | `8a34e00e-8f33-4591-8692-fb9358cb72d6` | DSC00365.JPG | image/jpeg | UNCLASSIFIED / unknown | UNKNOWN | UNKNOWN | NOT_REVIEWED | general manifest | `DO_NOT_SEND_EXTERNALLY`; approval false | none | DENY or HOLD unless superseded |
| 2 | `0260a986-3b66-42c6-9ec6-d6cc50a56584` | DSC05881.JPG | image/jpeg | UNCLASSIFIED / unknown | UNKNOWN | UNKNOWN | NOT_REVIEWED | general manifest | `DO_NOT_SEND_EXTERNALLY`; approval false | none | DENY or HOLD unless superseded |
| 3 | `7f72217d-3839-4920-86b4-ccc33e9e3d95` | IMG_0531.MP4 | video/mp4 | UNCLASSIFIED / unknown | UNKNOWN | UNKNOWN | NOT_REVIEWED | live pilot profile only | none found | authorized review required |
| 4 | `029c7315-b1a6-41f6-bb48-f1a91b492571` | IMG_0588.MP4 | video/mp4 | UNCLASSIFIED / unknown | UNKNOWN | UNKNOWN | NOT_REVIEWED | general manifest | `DO_NOT_SEND_EXTERNALLY`; approval false | none | DENY or HOLD unless superseded |
| 5 | `930417e8-24c9-4d51-9d30-ce4da96638df` | IMG_0620.MP4 | video/mp4 | UNCLASSIFIED / unknown | UNKNOWN | UNKNOWN | NOT_REVIEWED | general manifest | `DO_NOT_SEND_EXTERNALLY`; approval false | none | DENY or HOLD unless superseded |
| 6 | `3059f085-aaea-418a-8ef4-a8cba2393065` | IMG_0621.MP4 | video/mp4 | UNCLASSIFIED / unknown | UNKNOWN | UNKNOWN | NOT_REVIEWED | general manifest | `DO_NOT_SEND_EXTERNALLY`; approval false | none | DENY or HOLD unless superseded |
| 7 | `babae120-9372-42ad-b535-02a3276ea2be` | IMG_1238.MP4 | video/mp4 | UNCLASSIFIED / unknown | UNKNOWN | UNKNOWN | NOT_REVIEWED | live pilot profile only | none found | authorized review required |
| 8 | `9a4957bd-61bf-47dd-bd68-1debda5018eb` | IMG_1253.MP4 | video/mp4 | UNCLASSIFIED / unknown | UNKNOWN | UNKNOWN | NOT_REVIEWED | low-risk manifest | approval false | none | DENY or HOLD unless superseded |
| 9 | `c86344e9-5b32-4d86-9205-67952d508651` | IMG_3429.MP4 | video/mp4 | UNCLASSIFIED / unknown | UNKNOWN | UNKNOWN | NOT_REVIEWED | live pilot profile only | none found | authorized review required |
| 10 | `444da390-0117-4380-8c87-d7c32f2903ff` | IMG_9871.MOV | video/quicktime | UNCLASSIFIED / unknown | UNKNOWN | UNKNOWN | NOT_REVIEWED | live pilot profile only | none found | authorized review required |

The six blocked rows are DSC00365.JPG, DSC05881.JPG, IMG_0588.MP4, IMG_0620.MP4, IMG_0621.MP4, and IMG_1253.MP4. This corrects Job 5.1’s undercount without weakening any restriction. All ten remain non-approved. Any override must name the asset, reviewer, authority, reason, timestamp, purpose, scope, and superseded evidence.

## Decision provenance fields

For every row, the current human decision, reviewer, decision reason, review timestamp, and existing authorization evidence are `NONE / NULL`. The only permitted purpose for a future approval packet decision is `KDI AI Search V3 pilot indexing only`; it excludes marketing, public publishing, AI generation, arbitrary providers, general consent, download permission, and unlimited future processing.

## Blocking-evidence detail

| Asset | Evidence source | Restriction type | Superseding authorization |
|---|---|---|---|
| `8a34e00e-8f33-4591-8692-fb9358cb72d6` / DSC00365.JPG | `data/semantic_pilot_manifest.json` | `DO_NOT_SEND_EXTERNALLY`; `approved_for_external_ai=false` | none found |
| `0260a986-3b66-42c6-9ec6-d6cc50a56584` / DSC05881.JPG | `data/semantic_pilot_manifest.json` | `DO_NOT_SEND_EXTERNALLY`; `approved_for_external_ai=false` | none found |
| `029c7315-b1a6-41f6-bb48-f1a91b492571` / IMG_0588.MP4 | `data/semantic_pilot_manifest.json` | `DO_NOT_SEND_EXTERNALLY`; `approved_for_external_ai=false` | none found |
| `930417e8-24c9-4d51-9d30-ce4da96638df` / IMG_0620.MP4 | `data/semantic_pilot_manifest.json` | `DO_NOT_SEND_EXTERNALLY`; `approved_for_external_ai=false` | none found |
| `3059f085-aaea-418a-8ef4-a8cba2393065` / IMG_0621.MP4 | `data/semantic_pilot_manifest.json` | `DO_NOT_SEND_EXTERNALLY`; `approved_for_external_ai=false` | none found |
| `9a4957bd-61bf-47dd-bd68-1debda5018eb` / IMG_1253.MP4 | `data/semantic_pilot_low_risk_manifest.json` | `approved_for_external_ai=false` | none found |

Default result for each row above: **DO NOT APPROVE** unless a newer authoritative, asset-specific decision explicitly supersedes the cited restriction. The other four assets remain `NOT_REVIEWED`; absence of blocking evidence is not approval.
