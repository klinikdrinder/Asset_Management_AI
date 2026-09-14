# Job 5.2 pilot external-AI approval packet

Purpose for any approval: **KDI AI Search V3 pilot indexing only**. Scope excludes marketing, publication, content generation, arbitrary providers, and future unlimited processing.

For each asset the authoritative reviewer must select APPROVE, DENY, or HOLD and complete reviewer, reason, and date. Blank fields are intentional.

| # | Asset UUID | Filename | Type | Clinical | Consent | Marketing | Restriction | Current | Blocking | Decision | Reviewer | Reason | Date |
|---:|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | `8a34e00e-8f33-4591-8692-fb9358cb72d6` | DSC00365.JPG | image/jpeg | unknown | UNKNOWN | UNKNOWN | DO_NOT_SEND_EXTERNALLY | NOT_REVIEWED | YES | [REQUIRED] | [REQUIRED] | [REQUIRED] | [REQUIRED] |
| 2 | `0260a986-3b66-42c6-9ec6-d6cc50a56584` | DSC05881.JPG | image/jpeg | unknown | UNKNOWN | UNKNOWN | DO_NOT_SEND_EXTERNALLY | NOT_REVIEWED | YES | [REQUIRED] | [REQUIRED] | [REQUIRED] | [REQUIRED] |
| 3 | `7f72217d-3839-4920-86b4-ccc33e9e3d95` | IMG_0531.MP4 | video/mp4 | unknown | UNKNOWN | UNKNOWN | none found | NOT_REVIEWED | NO | [REQUIRED] | [REQUIRED] | [REQUIRED] | [REQUIRED] |
| 4 | `029c7315-b1a6-41f6-bb48-f1a91b492571` | IMG_0588.MP4 | video/mp4 | unknown | UNKNOWN | UNKNOWN | DO_NOT_SEND_EXTERNALLY | NOT_REVIEWED | YES | [REQUIRED] | [REQUIRED] | [REQUIRED] | [REQUIRED] |
| 5 | `930417e8-24c9-4d51-9d30-ce4da96638df` | IMG_0620.MP4 | video/mp4 | unknown | UNKNOWN | UNKNOWN | DO_NOT_SEND_EXTERNALLY | NOT_REVIEWED | YES | [REQUIRED] | [REQUIRED] | [REQUIRED] | [REQUIRED] |
| 6 | `3059f085-aaea-418a-8ef4-a8cba2393065` | IMG_0621.MP4 | video/mp4 | unknown | UNKNOWN | UNKNOWN | DO_NOT_SEND_EXTERNALLY | NOT_REVIEWED | YES | [REQUIRED] | [REQUIRED] | [REQUIRED] | [REQUIRED] |
| 7 | `babae120-9372-42ad-b535-02a3276ea2be` | IMG_1238.MP4 | video/mp4 | unknown | UNKNOWN | UNKNOWN | none found | NOT_REVIEWED | NO | [REQUIRED] | [REQUIRED] | [REQUIRED] | [REQUIRED] |
| 8 | `9a4957bd-61bf-47dd-bd68-1debda5018eb` | IMG_1253.MP4 | video/mp4 | unknown | UNKNOWN | UNKNOWN | low-risk manifest approval false | NOT_REVIEWED | YES | [REQUIRED] | [REQUIRED] | [REQUIRED] | [REQUIRED] |
| 9 | `c86344e9-5b32-4d86-9205-67952d508651` | IMG_3429.MP4 | video/mp4 | unknown | UNKNOWN | UNKNOWN | none found | NOT_REVIEWED | NO | [REQUIRED] | [REQUIRED] | [REQUIRED] | [REQUIRED] |
| 10 | `444da390-0117-4380-8c87-d7c32f2903ff` | IMG_9871.MOV | video/quicktime | unknown | UNKNOWN | UNKNOWN | none found | NOT_REVIEWED | NO | [REQUIRED] | [REQUIRED] | [REQUIRED] | [REQUIRED] |

Manifest recheck found six blocked overlaps; Job 5.1's four-count omitted two manifest members. The stricter corrected result is used here.

No human-decision field has been completed. A decision is valid for application only when the correct asset UUID, explicit APPROVE/DENY/HOLD decision, authorized reviewer identity, decision reason, decision timestamp, and the purpose/scope above are all present. Until then, `external_ai_status` must remain unchanged.
