# Job 5.1 pilot asset identification

## Result

The exact previously instantiated ten-asset pilot is reproducibly identified by the ten live `asset_ai_profiles` rows, all with `analysis_version = pilot_v1`. This is stronger evidence of the pilot actually used than the two repository candidate manifests: `data/semantic_pilot_manifest.json` (20 candidates) and `data/semantic_pilot_low_risk_manifest.json` (17 candidates). Neither manifest defines a competing exact ten-asset set, and both explicitly deny external-AI approval for every entry.

| # | asset_id | file_name | media_type | AI profile | clinical/sensitive | external AI | access-control | authoritative membership evidence |
|---:|---|---|---|---|---|---|---|---|
| 1 | `8a34e00e-8f33-4591-8692-fb9358cb72d6` | DSC00365.JPG | image/jpeg | pending / pilot_v1 | UNCLASSIFIED; is_clinical NULL; GENERAL | NOT_REVIEWED | NOT_REVIEWED | live `asset_ai_profiles` |
| 2 | `0260a986-3b66-42c6-9ec6-d6cc50a56584` | DSC05881.JPG | image/jpeg | pending / pilot_v1 | UNCLASSIFIED; is_clinical NULL; GENERAL | NOT_REVIEWED | NOT_REVIEWED | live `asset_ai_profiles` |
| 3 | `7f72217d-3839-4920-86b4-ccc33e9e3d95` | IMG_0531.MP4 | video/mp4 | pending / pilot_v1 | UNCLASSIFIED; is_clinical NULL; GENERAL | NOT_REVIEWED | NOT_REVIEWED | live `asset_ai_profiles` |
| 4 | `029c7315-b1a6-41f6-bb48-f1a91b492571` | IMG_0588.MP4 | video/mp4 | pending / pilot_v1 | UNCLASSIFIED; is_clinical NULL; GENERAL | NOT_REVIEWED | NOT_REVIEWED | live `asset_ai_profiles` |
| 5 | `930417e8-24c9-4d51-9d30-ce4da96638df` | IMG_0620.MP4 | video/mp4 | pending / pilot_v1 | UNCLASSIFIED; is_clinical NULL; GENERAL | NOT_REVIEWED | NOT_REVIEWED | live `asset_ai_profiles` |
| 6 | `3059f085-aaea-418a-8ef4-a8cba2393065` | IMG_0621.MP4 | video/mp4 | pending / pilot_v1 | UNCLASSIFIED; is_clinical NULL; GENERAL | NOT_REVIEWED | NOT_REVIEWED | live `asset_ai_profiles` |
| 7 | `babae120-9372-42ad-b535-02a3276ea2be` | IMG_1238.MP4 | video/mp4 | pending / pilot_v1 | UNCLASSIFIED; is_clinical NULL; GENERAL | NOT_REVIEWED | NOT_REVIEWED | live `asset_ai_profiles` |
| 8 | `9a4957bd-61bf-47dd-bd68-1debda5018eb` | IMG_1253.MP4 | video/mp4 | pending / pilot_v1 | UNCLASSIFIED; is_clinical NULL; GENERAL | NOT_REVIEWED | NOT_REVIEWED | live `asset_ai_profiles` |
| 9 | `c86344e9-5b32-4d86-9205-67952d508651` | IMG_3429.MP4 | video/mp4 | pending / pilot_v1 | UNCLASSIFIED; is_clinical NULL; GENERAL | NOT_REVIEWED | NOT_REVIEWED | live `asset_ai_profiles` |
| 10 | `444da390-0117-4380-8c87-d7c32f2903ff` | IMG_9871.MOV | video/quicktime | pending / pilot_v1 | UNCLASSIFIED; is_clinical NULL; GENERAL | NOT_REVIEWED | NOT_REVIEWED | live `asset_ai_profiles` |

Pilot membership is identified 10/10. Membership is not approval.
