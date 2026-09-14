# Job 3 deep-intelligence schema

Job 3 adds a normalized, empty semantic layer below canonical `assets`. No production media was analyzed. `asset_video_segments` remains the untouched legacy/V2 table; `asset_scenes` is the V3 canonical timeline.

## Model

| Table | Responsibility | Integrity / important links |
|---|---|---|
| `asset_scenes` | Canonical video timeline units | Asset cascade; unique `(asset_id, scene_index)`; valid positive interval; controlled primary ontology FKs |
| `asset_keyframes` | Representative frame metadata | Composite scene/asset FK; timestamp guard; derivative and analysis-run links |
| `scene_people` | Known or anonymous visible participants | Composite scene/asset FK; verified identity requires `people.id`; no biometrics |
| `person_appearances` | Neutral visible appearance, separate from identity | Composite participant/scene/asset and optional keyframe linkage; no race, ethnicity, or inferred nationality |
| `scene_treatments`, `scene_anatomy`, `scene_actions` | Controlled treatment, anatomy, and verb facts | Job 2 ontology FKs; duplicate treatment/anatomy relations blocked; participant consistency enforced |
| `scene_relationships` | Participant interaction | Both participants must belong to the same scene and asset; controlled relationship vocabulary |
| `clinical_observations` | Typed visible/semantic observations | Polymorphic typed value; source and verification state separate; no diagnosis field or implied diagnosis |
| `scene_environment`, `scene_cinematography`, `scene_composition` | One-per-scene production context | Scene PK; composite scene/asset FK; controlled camera vocabulary and bounded scores |
| `marketing_annotations` | Marketing interpretation | Kept separate from literal/clinical facts; controlled role and funnel stage |
| `scene_narratives` | Multiple scene interpretations | Literal, clinical-visual, storytelling, marketing, and emotional types remain distinct |
| `ocr_observations` | Timestamped detected frame text | Conservative access; composite scene/keyframe integrity; no OCR processing in Job 3 |

`asset_transcript_chunks` gained nullable `scene_id`, `speaker_person_id`, `speaker_scene_person_id`, and `analysis_run_id`. Its prior columns, rows, RLS policy, and existing asset/topics indexes remain intact. Composite FKs prevent transcript/scene/speaker mismatches, and a safe owner-only trigger bounds transcript times to the scene.

## Security and lifecycle

All 15 new tables have RLS enabled. PUBLIC, anon, and authenticated have no direct privileges; service-side writes remain available to `service_role`. Thus ordinary clients have no SELECT or write access until per-asset authorization is designed later. The single time-bound helper is SECURITY INVOKER with `search_path=''` and EXECUTE revoked from PUBLIC, anon, authenticated, and service_role; triggers continue to invoke it.

Asset-derived intelligence cascades when its canonical asset/scene is deleted. Controlled ontology records use RESTRICT for required facts and SET NULL for optional summaries. Analysis-run links use SET NULL so human-curated facts survive provenance record cleanup. No vector index was created.

## Index strategy

Indexes cover asset/scene timelines, ontology filters, participants, observation type/verification, marketing role/funnel, transcripts, and OCR. PK/UNIQUE coverage was not duplicated. `(asset_id, scene_index)` and scene narrative/relation unique constraints supply their own indexes.

## Job 4 boundary

All deep-intelligence tables remain empty. Job 4 may design controlled processing and embedding workflows; this job did not extract scenes/keyframes, transcribe, OCR, embed, search, or modify frontend/media.
