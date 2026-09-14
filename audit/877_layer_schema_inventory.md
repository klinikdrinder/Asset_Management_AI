# KDI 877-cohort layer schema inventory

Live cohort: 877 current `kdi_search_ready_assets_v1` rows (290 images, 585 videos, 2 other). Exact live counts were obtained using SELECT/GET only.

| Object | Type | Rows | Asset / scene / person relationship | Active/version mechanism | Production use |
|---|---|---:|---|---|---|
| `assets` | table | 881 (877 cohort) | PK asset ID | canonical row | YES: filename/media metadata |
| `semantic_specifications` | table | 1 | specification authority | LOCKED/version/fingerprint | Indirect |
| `semantic_layer_definitions` | table | 18 | layer catalog | `active`, spec version | Readiness/audit |
| `asset_semantic_layers` | table | 15,822 | asset + layer + run | `active`, `superseded_by`, semantic spec | Readiness/audit |
| `semantic_analysis_runs` | table | 2,722 | run → asset | processor/model/version/status | Provenance |
| `semantic_assertions` | table | 20,731 | asset; optional scene/event/keyframe/person subject | `active`, `superseded_by`, spec/ontology | YES, direct retrieval/reranking |
| `semantic_assertion_evidence` | table | 21,141 | assertion + asset; optional scene/event/keyframe/time | run/source fingerprint | Indirect; not directly loaded by reranker |
| `asset_scenes` | table | 1,102 | scene → asset | `canonical_active`, semantic version | PARTIAL via assertions/docs/vectors |
| `asset_keyframes` | table | 1,644 | keyframe → asset + scene + time | semantic version/run | PARTIAL via visual vectors |
| `scene_people` | table | 18 | person occurrence → asset + scene; 10 assets | run/provenance | NO direct production read |
| `person_appearances` | table | 18 | appearance → scene person + asset + scene | run/provenance | NO direct production read |
| `people` | table | 0 | canonical identity | active/verified | NO |
| `scene_anatomy` | table | 22 | asset + scene + anatomy | run/provenance | NO direct; assertion/doc derivation may be used |
| `scene_treatments` | table | 1 | treatment → asset + scene | run/provenance | NO direct |
| `scene_actions` | table | 14 | action → asset + scene/person | run/provenance | NO direct |
| `scene_relationships` | table | 7 | participant scene-person links | run/provenance | NO direct |
| `clinical_observations` | table | 12 | asset/scene/keyframe/person | run/verification | NO direct |
| `scene_environment` | table | 10 | asset + scene | run/provenance | NO direct |
| `scene_cinematography` | table | 10 | asset + scene | run/provenance | NO direct |
| `scene_composition` | table | 10 | asset + scene | run/provenance | NO direct |
| `asset_transcript_chunks` | table | 98 | asset + optional scene/time/speaker | search status/model/version | PARTIAL: explicit transcript literals |
| `ocr_observations` | table | 1,213 | asset + optional scene/keyframe/time | search status/model/version | PARTIAL: explicit OCR literals |
| `marketing_annotations` | table | 10 | asset | review/provenance | NO direct ranking |
| `asset_access_control` | table | 881 (877 cohort) | PK/FK asset | classification/review/usage state | YES through authorization RPC |
| `search_document_builds` | table | 1,712 | asset; optional scene/event | active/stale/status/version/supersession | YES |
| `asset_search_concepts_v2` | table | 270 | asset; optional scene/event/assertion | review/run | YES |
| `semantic_embeddings` | table | 7,295 | asset/scene/event/keyframe/text entity | active/stale/model/version/dimension | YES through matcher RPC |
| `kdi_search_ready_assets_v1` | view | 881 (877 true) | asset readiness rollup | derived | YES: mandatory candidate gate |
| `asset_search_documents` | legacy table | 30 | asset | build status/version | NO |
| `asset_semantic_index` | legacy table | 20 | asset | indexing status/version | NO |
| `asset_visual_embeddings` | legacy table | 875 | asset | model/version | NO |

Live search functions: `match_kdi_semantic_search_embeddings` (current vector matcher), `phase18_authorize_candidates_for` (current authorization), plus unused legacy `hybrid_search_assets`, v2, and v3 RPCs. Current source calls the first two, not the legacy hybrid RPCs.

Important catalog mismatch: the live locked catalog calls layers 17 and 18 `SEMANTIC_NARRATIVE` and `SEARCH_EMBEDDINGS`. The requested conceptual Safety/Consent and Evidence domains live instead in `asset_access_control` and `semantic_assertion_evidence`. This report presents the requested 18 conceptual domains while retaining the actual catalog mapping.
