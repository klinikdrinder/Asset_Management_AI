# Job 5.3 replacement candidate review

Status: **READ-ONLY DISCOVERY COMPLETE — HUMAN DECISIONS REQUIRED**

Purpose: `KDI AI Search V3 pilot indexing only`.

No replacement has been approved, no authorization row has been modified, and no media/frame/AI/embedding operation was performed.

## Screening method

The live 881-asset library was joined read-only against sources, active source folders, verified master destinations, access control, visual embeddings, and semantic metadata. Candidates had to be supported image/video assets with accessible, non-missing sources, verified master references, no usage restriction, and `external_ai_status=NOT_REVIEWED`.

All 37 unique asset IDs found in `data/semantic_pilot_manifest.json` or `data/semantic_pilot_low_risk_manifest.json` were excluded because those v1 manifests record `approved_for_external_ai=false`. The original ten pilot assets were also excluded. No other authoritative external-AI deny source was found in the Job 5.1–5.3 evidence set.

Eligible technical pool: 793 assets (245 images, 548 videos). Selection was deterministic from generic camera filenames and file-size quantiles; it did not use content, patient identity, or protected characteristics. The selected candidates are 12 distinct asset IDs with 12 distinct content hashes.

Video duration is `NOT RECORDED`: the current database and stored Drive metadata snapshots do not contain a duration field. No media probing was performed to derive it.

## Primary candidates

| # | Asset ID | Filename | Type / ext | Size | Duration | Visual | Semantic | Clinical | Consent | Marketing | External AI | Restriction / deny | Technical suitability |
|---:|---|---|---|---:|---|---|---|---|---|---|---|---|---|
| 1 | `37838d30-a0ce-4f90-8cc3-c986db0aaa65` | DSC03753.JPG | image/jpeg / jpg | 4,082,854 B | N/A | YES | NO | UNCLASSIFIED / unknown | UNKNOWN | UNKNOWN | NOT_REVIEWED | NO / NO | verified medium-size image with visual-search coverage |
| 2 | `6215ad8b-12be-4a8e-bc49-f6b3dcf55c21` | DSC08097.JPG | image/jpeg / jpg | 7,247,810 B | N/A | YES | NO | UNCLASSIFIED / unknown | UNKNOWN | UNKNOWN | NOT_REVIEWED | NO / NO | verified larger image with visual-search coverage |
| 3 | `64712c6a-c02c-46e9-9f73-16786109468b` | IMG_0493.MP4 | video/mp4 / mp4 | 1,661,286 B | NOT RECORDED | YES | NO | UNCLASSIFIED / unknown | UNKNOWN | UNKNOWN | NOT_REVIEWED | NO / NO | verified small video with visual-search coverage |
| 4 | `47611c6d-7923-42a4-87b6-c2a416a90f5c` | IMG_1148.MP4 | video/mp4 / mp4 | 3,324,705 B | NOT RECORDED | YES | NO | UNCLASSIFIED / unknown | UNKNOWN | UNKNOWN | NOT_REVIEWED | NO / NO | verified medium-small video with visual-search coverage |
| 5 | `bfae6c51-5d71-47ae-a3e1-6d07092b8896` | IMG_2963.MP4 | video/mp4 / mp4 | 5,942,390 B | NOT RECORDED | YES | NO | UNCLASSIFIED / unknown | UNKNOWN | UNKNOWN | NOT_REVIEWED | NO / NO | verified medium video with visual-search coverage |
| 6 | `753eb5f3-82c7-4148-a226-d5b960fd8619` | IMG_1160.MP4 | video/mp4 / mp4 | 10,918,586 B | NOT RECORDED | YES | NO | UNCLASSIFIED / unknown | UNKNOWN | UNKNOWN | NOT_REVIEWED | NO / NO | verified larger video with visual-search coverage |

## Backup candidates

| # | Asset ID | Filename | Type / ext | Size | Duration | Visual | Semantic | Clinical | Consent | Marketing | External AI | Restriction / deny | Technical suitability |
|---:|---|---|---|---:|---|---|---|---|---|---|---|---|---|
| 7 | `e686d1a9-bf33-4abd-9a53-024ded4d4073` | DSC03759.JPG | image/jpeg / jpg | 4,425,603 B | N/A | YES | NO | UNCLASSIFIED / unknown | UNKNOWN | UNKNOWN | NOT_REVIEWED | NO / NO | verified alternate medium-size image |
| 8 | `033b5509-1675-4a9a-a12f-d0e874278c3f` | DSC08943.JPG | image/jpeg / jpg | 12,862,963 B | N/A | YES | NO | UNCLASSIFIED / unknown | UNKNOWN | UNKNOWN | NOT_REVIEWED | NO / NO | verified alternate large image |
| 9 | `c507ee4a-3df5-4701-8363-827263a294de` | IMG_0612.MP4 | video/mp4 / mp4 | 2,328,335 B | NOT RECORDED | YES | NO | UNCLASSIFIED / unknown | UNKNOWN | UNKNOWN | NOT_REVIEWED | NO / NO | verified alternate small video |
| 10 | `61c9dd6c-b5e4-4435-9d68-2beb3e91db70` | IMG_0611.MP4 | video/mp4 / mp4 | 4,381,362 B | NOT RECORDED | YES | NO | UNCLASSIFIED / unknown | UNKNOWN | UNKNOWN | NOT_REVIEWED | NO / NO | verified alternate medium-small video |
| 11 | `2d766a56-3364-4a52-8e5c-c40c8f4a49fa` | IMG_1156.MP4 | video/mp4 / mp4 | 7,245,334 B | NOT RECORDED | YES | NO | UNCLASSIFIED / unknown | UNKNOWN | UNKNOWN | NOT_REVIEWED | NO / NO | verified alternate medium video |
| 12 | `42418c66-d0f4-4131-83fd-9b262b81525d` | IMG_1149.MP4 | video/mp4 / mp4 | 20,144,716 B | NOT RECORDED | YES | NO | UNCLASSIFIED / unknown | UNKNOWN | UNKNOWN | NOT_REVIEWED | NO / NO | verified alternate large video |

Candidate status is not authorization. Each selected replacement still requires an explicit APPROVE decision and reason from the validated reviewer.
