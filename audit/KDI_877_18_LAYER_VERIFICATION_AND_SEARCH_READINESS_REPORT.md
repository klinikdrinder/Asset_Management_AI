# KDI 877-ASSET SEMANTIC VERIFICATION REPORT

## 1. Executive Answer

- Number of assets audited: **877**
- Number of semantic layers configured: **18**
- Number reported processed: **877 assets × 18 layers**
- Number genuinely verified across ALL applicable 877 assets: **2/18 conceptual layers**; only **4/877 assets** pass all 18 conservative conceptual verification flags
- Number partially verified: **14/18 layers; 873/877 assets** have some but not all conceptual layer verification
- Number not sufficiently verified: **2/18 layers**
- Number of assets genuinely search-ready: **866/877** under the documented general-search evidence rule
- Number marked ready but not genuinely ready: **11**

**Are all 877 assets currently ready for accurate complex natural-language semantic search? NO.** Processing and canonical indexing are nearly complete, but structured People/Appearance coverage is only 10 assets, person-bound retrieval is absent, and the exact complex query fails interpretation. General semantic readiness is 866/877; readiness for the specified human-attribute query is materially weaker.

## 2. 18-Layer Verification Table

The first 16 rows map to the live locked catalog. Requested Safety/Consent and Evidence are implemented outside that catalog; the live catalog instead names positions 17–18 Semantic Narrative and Search & Embeddings. This mismatch is itself an audit finding.

| # | Layer | Processed Assets | Meaningfully Populated | Structurally Verified | Search-Active Assets | Verified Across All Applicable Assets? |
|---:|---|---:|---:|---:|---:|---|
|1|Identity|877|877 via canonical assets|877|877|YES|
|2|Global|877|637|637|637|NO|
|3|Temporal|877|578|578|578|NO|
|4|People|877|562|579 including evidenced unknown/N-A|579 indirect|NO|
|5|Appearance|877|838|842 including evidenced unknown/N-A|842 indirect|NO|
|6|Anatomy|877|806|823|823|NO|
|7|Treatment|877|7|9|9|NO|
|8|Actions|877|744|787|787|NO|
|9|Relationships|877|439|485|485 indirect|NO|
|10|Clinical Visual|877|774|789|789 indirect|NO|
|11|Environment|877|478|498|498 indirect|NO|
|12|Cinematography|877|822|822|822 indirect|NO|
|13|Composition|877|850|850|850 indirect|NO|
|14|Speech|877|60|564 including evidenced unknown/N-A|564 partial|NO|
|15|OCR|877|247|834 including evidenced unknown/N-A|834 partial|NO|
|16|Marketing|877|24|79|0 effective ranking|NO|
|17|Safety / Consent|877|877 classified/internal-use state; consent UNKNOWN|877 for internal authorization, not consent|877 authorization|NO|
|18|Evidence|877|877 with assertion evidence|877|877 indirectly|YES|

## 3. Fully Verified Layers

- **Identity:** all 877 assets have canonical identity and filename/media association.
- **Evidence:** every cohort asset has assertion evidence linked to existing assets; no assertion/scene/keyframe evidence orphan was found.

No assertion-derived semantic content layer is verified across every applicable asset under the conservative structural rule.

## 4. Partially Verified Layers

Global, Temporal, People, Appearance, Anatomy, Actions, Relationships, Clinical Visual, Environment, Cinematography, Composition, Speech, OCR, and Safety/Consent are partial. Reasons include incomplete meaningful coverage, legitimate and suspicious UNKNOWN/default states, sparse normalized tables, missing person binding, indirect-only retrieval, or unknown consent.

## 5. Unverified / Non-Working Layers

- **Treatment:** only 7 meaningful assets and 9 structurally supported assets under the assertion/evidence test; 868 are suspiciously empty/default-only against the recorded applicability.
- **Marketing:** 24 meaningful and 79 structurally supported; no effective production candidate/ranking channel.

These layers exist and are marked processed, but cannot support their intended corpus-wide search behavior.

## 6. People Layer

People assertions are meaningful for 562 assets and structurally supported for 579. The normalized `scene_people` table contains 18 rows across only 10 assets. Person role is populated for those 10; exact age for 0; age min/max for 2; gender presentation for 2. Production does not query `scene_people` directly, so effective support comes from assertions, normalized concepts, documents, and embeddings.

## 7. Appearance Layer

Appearance assertions are meaningful for 838 assets and structurally supported for 842. Normalized `person_appearances` contains 18 rows across only 10 assets. Hair color, length, apparent density, facial hair, wardrobe, and posture are each materially populated for only 2 assets in current normalized rows. Production does not directly query this table.

## 8. Person + Scene Binding

All 10 assets with structured people have valid scene relationships, and their appearance rows bind to valid `scene_people` rows: **10/10 applicable**. This is structurally sound but covers only 10/877 assets. The production reranker has same-scene and same-event bonuses but no same-person constraint, so it cannot guarantee that multiple requested attributes describe one person.

## 9. Video Semantic Coverage

- Cohort videos: **585**
- Videos with scenes: **585/585**
- Videos with keyframes: **585/585**
- Videos with valid scene-bound semantic assertions: **585/585**
- Fully scene-verified under boundary/binding checks: **567/585**
- Partially scene-verified: **18/585**
- Adjacent-scene overlap findings: **18 videos**, one each
- Videos with missing scene semantics: **0**
- Videos with structured People evidence: **8**
- Orphan scenes/keyframes: **0**

## 10. Current Production Search Usage

| Layer | Data Exists | Structured | Production Uses It | Effective Search Support |
|---|---|---|---|---|
| Identity | YES | YES | YES | STRONG |
| Global | YES | PARTIAL | YES | PARTIAL |
| Temporal | YES | YES | PARTIAL | PARTIAL |
| People | YES | 10 assets | INDIRECT | WEAK |
| Appearance | YES | 10 assets | INDIRECT | WEAK |
| Anatomy | YES | PARTIAL | YES | PARTIAL |
| Treatment | YES | SPARSE | PARTIAL | WEAK |
| Actions | YES | PARTIAL | YES | PARTIAL |
| Relationships | YES | SPARSE | INDIRECT | WEAK |
| Clinical Visual | YES | PARTIAL | INDIRECT | PARTIAL |
| Environment | YES | PARTIAL | INDIRECT | PARTIAL |
| Cinematography | YES | PARTIAL | INDIRECT | PARTIAL |
| Composition | YES | PARTIAL | INDIRECT | PARTIAL |
| Speech | YES | YES | PARTIAL | PARTIAL |
| OCR | YES | YES | PARTIAL | PARTIAL |
| Marketing | YES | SPARSE | NO effective rank channel | NONE |
| Safety / Consent | YES | YES | YES, authorization | PARTIAL |
| Evidence | YES | YES | INDIRECT | PARTIAL |

## 11. Search Documents

All 877 cohort assets have one active, READY, non-stale canonical asset document. No duplicate active canonical asset document exists. Versions are 847 `kdi_search_document_v1` and 30 `kdi_search_document_v1_spec_locked`. The preserved 30-row `asset_search_documents` and 20-row `asset_semantic_index` paths are legacy and not used by current production retrieval.

## 12. Embeddings

All 877 cohort assets have an active compatible TEXT_ASSET E5-small 384-dimensional embedding. Canonical VISUAL_ASSET embeddings cover 857; any current canonical visual representation covers 867. Scene visual vectors cover all 585 videos (791 scene rows), and keyframe vectors cover all 585 videos (1,333 rows). Ten READY images lack current canonical visual evidence; historical/stale and legacy vectors are preserved but not counted as current.

The production query encoder and matcher agree on E5 model/version/dimension and OpenCLIP model/version/dimension.

## 13. Complex Query Test

Query: `male patient around 35 with receding hairline wearing blue shirt`

- Parser: **FAIL**
- Structured retrieval: **FAIL**
- Person binding: **FAIL**
- Scene binding: **PARTIAL**
- Age matching: **FAIL**
- Appearance matching: **FAIL**
- Semantic embedding: **PARTIAL** — vectors are generated, but unresolved-only vector candidates are rejected
- Ranking: **FAIL for this query**

**OVERALL: FAIL.** None of the six requested concepts is recognized. `35` is not a result count, but it is also not recognized as age. No fuzzy age, color, hairline, same-person, or required same-scene logic is produced.

## 14. Real Semantic Search Readiness

877 cohort:

- Processing Complete: **877 / 877**
- 18-Layer Structurally Verified Assets: **4 / 877** under the conservative conceptual matrix
- Search Attribute Complete: **875 / 877** (at least one meaningful active assertion and valid video scene evidence where applicable)
- Search Active: **877 / 877** (current canonical document and compatible text embedding)
- Genuinely Search Ready: **866 / 877**
- False Search Ready: **11**

The general readiness rule requires 18 processed layers, meaningful evidence, canonical current document, compatible text embedding, applicable current visual/scene evidence, valid internal-use ACL, and valid scene/keyframes for video. It does not claim that every asset supports every human-attribute query.

## 15. Layer Verification Summary

FULLY VERIFIED LAYERS: **2 / 18**

PARTIALLY VERIFIED LAYERS: **14 / 18**

NOT VERIFIED / NOT EFFECTIVELY SEARCHABLE: **2 / 18**

Effectively used directly or indirectly by production: **17 / 18**; coverage and quality vary sharply.

## 16. Main Reasons Assets Are Not Search Ready

**P0**

- Parser/ontology does not recognize the representative People, Appearance, clothing, hairline, or approximate-age concepts.
- Structured People and Appearance cover only 10 assets and their tables are disconnected from direct retrieval.
- No same-person retrieval invariant exists.

**P1**

- Ten READY images lack current canonical visual evidence; one additional READY video and one of those images lack meaningful active assertions, producing 11 false-ready assets.
- Treatment and Marketing layers are overwhelmingly status-complete but not meaningfully/structurally populated.
- Fuzzy age overlap and requested color/hairline expansion are absent for the tested query.

**P2**

- Eighteen video timelines contain adjacent-scene overlaps.
- Consent is UNKNOWN for all 877, although internal usage is allowed and classification is verified for the cohort.

## 17. Per-Layer Repair Requirement

| Layer | Requirement |
|---|---|
| Identity | NO REPAIR |
| Global | MINOR REPAIR / coverage investigation |
| Temporal | MINOR REPAIR; 18 boundary investigations |
| People | STRUCTURED MATERIALIZATION REQUIRED + RETRIEVAL CONNECTION REQUIRED |
| Appearance | STRUCTURED MATERIALIZATION REQUIRED + RETRIEVAL CONNECTION REQUIRED |
| Anatomy | STRUCTURED MATERIALIZATION REQUIRED for gaps |
| Treatment | RE-ANALYSIS REQUIRED + STRUCTURED MATERIALIZATION REQUIRED |
| Actions | STRUCTURED MATERIALIZATION REQUIRED |
| Relationships | STRUCTURED MATERIALIZATION REQUIRED + person binding |
| Clinical Visual | MANUAL INVESTIGATION / selective materialization |
| Environment | MINOR REPAIR / materialization |
| Cinematography | MINOR REPAIR |
| Composition | MINOR REPAIR |
| Speech | MINOR REPAIR; validate applicable silent assets |
| OCR | MINOR REPAIR; validate legitimate no-text states |
| Marketing | RE-ANALYSIS REQUIRED + RETRIEVAL CONNECTION REQUIRED |
| Safety / Consent | MANUAL INVESTIGATION REQUIRED for UNKNOWN consent |
| Evidence | NO REPAIR for referential integrity; retrieval connection is partial by design |

No repair was performed.

## 18. Final Verdict

**B. 877 ASSETS ARE PROCESSED BUT ONLY 866 ARE GENUINELY SEARCH-READY.** Furthermore, the current system fails the specified complex human-attribute query, so “genuinely search-ready” here means general production corpus readiness, not universal query correctness.

## Required Final Table

| Metric | Result |
|---|---:|
| Assets in audit cohort | 877 / 877 |
| Layers configured | 18 / 18 |
| Layers processed | 18 / 18 |
| Layers genuinely verified | 2 / 18 |
| Layers partially verified | 14 / 18 |
| Layers effectively used by production search | 17 / 18 |
| Processing-complete assets | 877 / 877 |
| Search-attribute-complete assets | 875 / 877 |
| Genuinely search-ready assets | 866 / 877 |
| False-ready assets | 11 |
| Videos with valid scene semantics | 585 / 585 |
| Assets with structured People data | 10 / 877 |
| Assets with structured Appearance data | 10 / 877 |
| Assets with valid person binding | 10 / 10 applicable |
| Assets with valid scene binding | 585 / 585 applicable videos |

## Method and safety

Database work was limited to SELECT/catalog inspection and GET-only PostgREST reads. The current search API was not invoked because it writes search telemetry. Production rows modified: **0**. No secrets are present in the artifacts.
