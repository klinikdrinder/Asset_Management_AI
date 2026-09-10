# KDI SEMANTIC SEARCH REPAIR — FIX 1 BASELINE AUDIT

## 1. Status

**PASS_WITH_FINDINGS.** The live production database, schema, current and legacy semantic stores, asset readiness, code path, and representative parser behavior were audited read-only. PASS does not mean search quality is acceptable.

## 2. Database connectivity

- Connected: **YES**
- Production database verified: **YES** — Supabase project `asset_management_ai`, ref `wcqqjpndlwsvatjuqnol`, PostgreSQL 17
- Secrets exposed: **NO**
- Production rows modified: **0**

Only SQL `SELECT`, catalog inspection, and PostgREST GET were used. The production search endpoint was deliberately not called because it records sessions, queries, and results.

## 3. Authoritative asset counts

The authoritative live set is all 881 `assets` rows: 293 images, 585 videos, and 3 other documents (2 PDF, 1 PPTX). All 881 have source, destination, technical metadata, and ACL relationship rows; no broken/orphan source joins were found. `source_files` has 890 rows: 881 TAKE and 9 SKIP. No `duplicate_of_source_file_id` values exist. All source access lifecycle values remain PENDING and all asset upload lifecycle values remain PENDING even though downstream data exists, so these status fields are not reliable readiness authorities. All `assets.master_google_file_id` values are null; the operational master relationship is represented elsewhere (`asset_destinations`/source linkage).

The database has no canonical ordinal on `assets`. The matrix's ordinal is audit-only, deterministically sorted by filename and UUID.

## 4. Current semantic coverage

The locked standard is `asset_semantic_layers` + `semantic_layer_definitions` under the locked semantic specification. Exactly 877 assets have all 18 active layers complete; 4 lack the current corpus.

|#|Layer|Complete|Meaningful|Placeholder-only|Missing|Scene assertions|Asset assertions|With evidence|
|---:|---|---:|---:|---:|---:|---:|---:|---:|
|1|Asset Identity & Provenance|877|857|0|4|770|857|1,627|
|2|Global Asset Understanding|877|637|0|4|534|531|1,065|
|3|Temporal / Scene Structure|877|578|0|4|759|569|1,328|
|4|People & Roles|877|562|17|4|686|505|1,191|
|5|Person Appearance|877|838|4|4|773|833|1,606|
|6|Anatomy|877|806|17|4|760|786|1,546|
|7|Treatment / Procedure|877|7|9|4|7|13|13|
|8|Actions & Events|877|744|43|4|796|757|1,553|
|9|Relationships|877|439|46|4|640|450|1,090|
|10|Clinical Visual Observations|877|774|17|4|731|743|1,472|
|11|Environment|877|478|23|4|325|420|742|
|12|Cinematography|877|822|0|4|762|777|1,539|
|13|Composition|877|850|0|4|779|841|1,620|
|14|Speech / Transcript / Audio|877|60|504|4|736|617|1,353|
|15|OCR / Visible Text|877|247|587|4|726|831|1,557|
|16|Marketing & Content Usage|877|24|55|4|110|66|176|
|17|Semantic Narrative|877|559|0|4|399|491|890|
|18|Search & Embeddings|877|158|0|4|96|148|244|

## 5. Meaningful semantic coverage

Only 875 assets have at least one active OBSERVED assertion with a non-placeholder value; 2 of the 877 complete assets have no meaningful assertion by the strict audit test. Layer-level completeness is much less persuasive: Treatment/Procedure is meaningful for only 7 assets, Speech for 60, Marketing/Usage for 24, and the Search/Embedding semantic layer for 158. COMPLETE therefore means the processor finished, not that useful searchable content exists.

UNKNOWN/NOT_APPLICABLE may be valid only when an applicable domain was genuinely evaluated and carries evidence. This audit preserves those states but does not count them as meaningful values.

## 6. People + Appearance coverage

Structured `scene_people` and `person_appearances` each cover only 10 assets (18 people/18 appearances). The `people` identity table is empty. Active assertions contain person/appearance-like free text or concepts for 850 assets not materialized into structured people rows: **STRUCTURED_MATERIALIZATION_GAP**.

The 18-layer layer names create a misleading impression of structured availability: People & Roles has meaningful assertions for 562 assets and Person Appearance for 838, but production does not query `scene_people` or `person_appearances` directly. Age, gender, hair, wardrobe, posture and identity fields are therefore sparse in structured form and lack a same-person retrieval binding.

## 7. Video scene/keyframe coverage

- Videos: 585
- Videos with ≥1 scene: 585
- Videos with ≥1 keyframe: 585
- Total scenes: 1,102
- Total keyframes: 1,644
- Scenes with zero keyframes: 0
- Videos with scene assertions: 585
- Videos with structured People evidence: 8
- Videos with transcript-linked scenes: 45
- Videos with OCR-linked scenes: 241
- Invalid/reversed boundaries: 0
- Detected adjacent-scene overlaps: 18 across 18 videos
- Orphan scenes/keyframes: 0

Scene/keyframe presence is excellent, but structured people coverage is not. Search can receive scene evidence through assertions/documents/embeddings, but same-scene is only a scoring bonus and not a hard binding.

## 8. Search-document coverage

`search_document_builds` is canonical. It has 1,712 historical/current rows and 877 unique asset documents that are active, READY and not stale: 847 at `kdi_search_document_v1` and 30 at `kdi_search_document_v1_spec_locked`. Four authoritative assets have no canonical document and are the only empty/short cases. No duplicate active asset document was found.

Structural text checks show 144 READY documents without recognizable People terms, 75 without appearance terms, and 783 without recognizable treatment/action terms. These are heuristic absence indicators, not clinical judgments. Twenty samples (10 image/10 video) are recorded without patient-sensitive excerpts.

Legacy systems remain preserved but inactive in production: `asset_search_documents` (30), `scene_search_documents` (20), and `asset_semantic_index` (20).

## 9. Embedding coverage

- Canonical active TEXT_ASSET: 877 assets, E5-small, 384 dimensions
- Historical/stale E5 TEXT_ASSET rows: 10 (plus one stale LOCAL family row)
- Canonical active VISUAL_ASSET: 857 assets, OpenCLIP ViT-B-32, 512 dimensions
- Active VISUAL_SCENE: 791 rows / 585 assets
- Active VISUAL_KEYFRAME: 1,333 rows / 585 assets
- Assets with any canonical active visual representation: 867
- Legacy `asset_visual_embeddings`: 875 assets; not used by canonical search
- Active duplicate entity rows: 9 TEXT_EVENT duplicates by the audit entity key; no duplicate TEXT_ASSET/VISUAL_ASSET/SCENE/KEYFRAME rows

The query encoder declares the same E5/OpenCLIP compatibility as the live matcher. Canonical text rows carry document fingerprints; visual rows do not, which is expected for image/frame source representations but prevents document-version linkage.

## 10. Production search architecture

Canonical route: `POST /api/search` → `interpretQuery` → `classifyRequirements` → `expandQuery` → dual query encoders → multi-channel `retrieveCandidates` → `match_kdi_semantic_search_embeddings` → `kdi_search_ready_assets_v1` gate → `phase18_authorize_candidates_for` → assertion/concept evidence load → deterministic reranker → result-count controller → response mapping.

Production uses canonical docs, canonical embeddings, active semantic assertions, `asset_search_concepts_v2`, ACL authorization, filename, and conditional OCR/transcript literals. It does not directly use structured people/appearance tables or any legacy search corpus. Full source references and weights are in `fix01_production_search_trace.md`.

## 11. Legacy/pilot search architecture

Live legacy RPCs `hybrid_search_assets`, `hybrid_search_assets_v2`, and `hybrid_search_assets_v3` still exist, as do earlier embedding/document tables. Current code does not call them. `/api/search/v3` is only an alias of the canonical route, not a separate engine. Legacy dependency remaining in the active path: **NO**; legacy objects remaining in the database: **YES**.

## 12. Representative query diagnosis

For `male patient around 35 with receding hairline wearing blue shirt`, the live parser recognizes none of MALE, PATIENT, age, RECEDING_HAIRLINE, BLUE, or SHIRT. It does not treat 35 as result count; it classifies 35 as an unclassified exact number. The two clauses remain unresolved. No hard filters, strong requirements, preferences, retrieval text, fuzzy age overlap, color expansion, or hairline ontology expansion result.

Although the original sentence reaches query encoders, the reranker rejects vector-only unresolved candidates. The expected outcome is zero eligible semantic matches. Same-scene coherence exists only as a bonus; same-person binding does not exist, so a future partially parsed query could mix attributes between people or scenes.

## 13. Integrity defects

No referential orphans were detected among assertions, scenes, keyframes, scene people, appearances, documents, or embeddings. No duplicate active canonical asset document exists. Eighteen videos have one adjacent-scene overlap each. Ten stale compatible text vectors and one stale alternate-provider text vector remain preserved and correctly inactive. ACL rows exist for all assets, but consent is UNKNOWN for all; internal usage is ALLOWED for 880 assets, while one PPTX is UNCLASSIFIED/UNKNOWN and already outside the ready corpus. Thirty clinical assets require clinical permission; 20 are not reviewed and 10 reviewed.

## 14. False readiness analysis

Current system `search_ready=true`: **877**. Strict audit genuine SEARCH_READY: **866**. False-ready: **11**.

The 11 consist of 10 READY images lacking any current canonical visual representation (one also lacks meaningful active assertions) plus one READY video lacking meaningful active assertions. This strict count intentionally requires meaningful semantic evidence plus a canonical doc, compatible text vector, applicable canonical visual/scene evidence, ACL presence, and video scene/keyframes. People/Appearance structured materialization is reported separately and is not made a universal hard readiness prerequisite, because many assets may legitimately lack visible people.

## 15. Asset-level repair categories

Categories overlap.

| Category | Assets |
|---|---:|
| No strict readiness repair | 866 |
| Structured metadata materialization needed/assessment | 871 |
| People/Appearance visual re-analysis candidate | up to 871 (must first distinguish no-person assets) |
| Scene/keyframe boundary repair | 18 videos |
| Search document rebuild | 4 |
| Text embedding refresh/backfill | 4 missing; 10 stale historical rows need cleanup policy only |
| Visual embedding backfill | 14 lack any canonical active visual representation; 20 lack VISUAL_ASSET specifically |
| ACL/privacy repair | 1 unclassified asset; consent policy clarification affects all 881 |
| Integrity/manual investigation | 11 false-ready assets plus 18 overlap videos |

## 16. Top search-accuracy blockers

1. **P0 — QUERY_PARSER_DEFECT / ONTOLOGY_GAP:** the representative query's six concepts are all unresolved.
2. **P0 — PRODUCTION_RETRIEVAL_DISCONNECTED / PERSON_BINDING_MISSING:** structured People/Appearance tables cover only 10 assets and are not directly read; no same-person invariant exists.
3. **P0 — AGE_MATCHING_DEFECT:** `around 35` is not recognized as age and no fuzzy range-overlap scoring occurs.
4. **P1 — STRUCTURED_MATERIALIZATION_GAP:** person/appearance information exists in assertions/free text for hundreds of assets but is not normalized into person-bound fields.
5. **P1 — FALSE_SEARCH_READY / VISUAL_EMBEDDING_MISSING:** 11 current READY assets fail the strict evidence definition.
6. **P1 — sparse treatment/action document coverage:** heuristic terms are absent in 783 READY asset documents; structured Treatment/Procedure is meaningful for only 7 assets.
7. **P2 — SCENE_BINDING_MISSING:** 18 video timelines have adjacent overlaps.
8. **P3 — legacy corpus cleanup:** old tables/RPCs remain but are not active dependencies.

## 17. Recommended FIX 2

FIX 2 should repair deterministic query interpretation and ontology coverage for person role, gender presentation, fuzzy age/range overlap, hairline/appearance, clothing type/color, and require same-person/same-scene evidence grouping—while preserving current semantic rows and proving behavior against the frozen Fix 1 matrix before any rebuild.

## 18. Files generated

- `audit/KDI_FIX01_BASELINE_AUDIT_REPORT.md`
- `audit/fix01_schema_inventory.md`
- `audit/fix01_18_layer_coverage.csv`
- `audit/fix01_18_layer_coverage.md`
- `audit/fix01_people_appearance_coverage.csv`
- `audit/fix01_people_appearance_findings.md`
- `audit/fix01_video_scene_integrity.csv`
- `audit/fix01_video_scene_findings.md`
- `audit/fix01_search_document_coverage.csv`
- `audit/fix01_search_document_findings.md`
- `audit/fix01_embedding_inventory.csv`
- `audit/fix01_embedding_findings.md`
- `audit/fix01_production_search_trace.md`
- `audit/fix01_representative_query_diagnostic.md`
- `audit/fix01_integrity_exceptions.csv`
- `audit/fix01_integrity_findings.md`
- `audit/fix01_asset_readiness_matrix.csv`
- `audit/fix01_live_summary.json`

## Audit readiness rule

`AUDIT_PROCESSING_COMPLETE` requires 18 active complete layer rows. `AUDIT_SEARCH_ATTRIBUTE_COMPLETE` requires at least one meaningful active OBSERVED assertion and, for video, a scene. `AUDIT_SEARCH_READY` requires both, an active non-stale READY asset document, compatible active TEXT_ASSET embedding, applicable current canonical visual evidence, an ACL row, and for videos both scene and keyframe coverage. UNKNOWN/NOT_VISIBLE alone is never meaningful; the full layer CSV separately preserves justified evaluated unknown counts/evidence.
