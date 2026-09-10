# Job 5.1 external-AI review

## Authoritative evidence result

All ten pilot assets have `external_ai_status = NOT_REVIEWED`, `review_status = NOT_REVIEWED`, `reviewed_by = NULL`, `reviewed_at = NULL`, `consent_reference = NULL`, empty access-control metadata, and no usage restriction/decision record. Their profile provenance is also empty. Across the complete library, all 881 access-control rows remain `NOT_REVIEWED`.

The general and low-risk pilot manifests explicitly state `approved_for_external_ai: false`. Labels such as `LOW_RISK_FOR_PILOT`, existing AI profiles, internal visibility, or prior local processing are not authorization.

| asset_id | file_name | external AI | clinical | consent | marketing | reason human approval is required | recommended decision field |
|---|---|---|---|---|---|---|---|
| `8a34e00e-8f33-4591-8692-fb9358cb72d6` | DSC00365.JPG | NOT_REVIEWED | unknown | UNKNOWN | UNKNOWN | no explicit reviewer decision | `external_ai_status` plus reviewer, time, reason and scoped purpose |
| `0260a986-3b66-42c6-9ec6-d6cc50a56584` | DSC05881.JPG | NOT_REVIEWED | unknown | UNKNOWN | UNKNOWN | no explicit reviewer decision | same |
| `7f72217d-3839-4920-86b4-ccc33e9e3d95` | IMG_0531.MP4 | NOT_REVIEWED | unknown | UNKNOWN | UNKNOWN | no explicit reviewer decision | same |
| `029c7315-b1a6-41f6-bb48-f1a91b492571` | IMG_0588.MP4 | NOT_REVIEWED | unknown | UNKNOWN | UNKNOWN | no explicit reviewer decision; manifest explicitly denies approval | same |
| `930417e8-24c9-4d51-9d30-ce4da96638df` | IMG_0620.MP4 | NOT_REVIEWED | unknown | UNKNOWN | UNKNOWN | no explicit reviewer decision; manifest explicitly denies approval | same |
| `3059f085-aaea-418a-8ef4-a8cba2393065` | IMG_0621.MP4 | NOT_REVIEWED | unknown | UNKNOWN | UNKNOWN | no explicit reviewer decision; manifest explicitly denies approval | same |
| `babae120-9372-42ad-b535-02a3276ea2be` | IMG_1238.MP4 | NOT_REVIEWED | unknown | UNKNOWN | UNKNOWN | no explicit reviewer decision | same |
| `9a4957bd-61bf-47dd-bd68-1debda5018eb` | IMG_1253.MP4 | NOT_REVIEWED | unknown | UNKNOWN | UNKNOWN | no explicit reviewer decision; low-risk manifest still denies approval | same |
| `c86344e9-5b32-4d86-9205-67952d508651` | IMG_3429.MP4 | NOT_REVIEWED | unknown | UNKNOWN | UNKNOWN | no explicit reviewer decision | same |
| `444da390-0117-4380-8c87-d7c32f2903ff` | IMG_9871.MOV | NOT_REVIEWED | unknown | UNKNOWN | UNKNOWN | no explicit reviewer decision | same |

Eligible: 0. Explicitly blocked by approval evidence: 4 manifest-overlap assets. Still NOT_REVIEWED: 10. No status was changed, including non-pilot rows. An authorized human must record a per-asset decision scoped to “KDI AI Search V3 pilot indexing,” including provider restrictions where applicable. Job 6 remains blocked.
