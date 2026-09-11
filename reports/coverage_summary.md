# Normalisation Reconnaissance — Coverage Summary

**Scope:** READ-ONLY analysis of `semantic_assertions.value_text` where
`active AND canonical_concept_code = layer_id` (the placeholder population),
measured against the six seeded ontology tables.
**No writes, no migrations, no assertion changes were made.**
Database verified live via Supabase Management API, project `wcqqjpndlwsvatjuqnol`.

Extractor: `reports/normalization_recon_extract.mjs` (SELECT-only, re-runnable).
Outputs: `mapping_candidates.csv`, `unmapped.csv`, this file.

---

## 0. Baseline (verified live, this session)

| Metric | Value |
|---|---|
| Active assertions total | 20,624 |
| Placeholder rows (`canonical_concept_code = layer_id`) | **20,110** |
| Distinct placeholder `value_text` strings | **15,351** |
| Genuine-code rows (`<> layer_id`) | 514 |

The placeholder rows collapse to 15,351 distinct strings — a **1.31 : 1**
ratio. The task brief expected "~20,110 collapsing to far fewer distinct
strings." That did **not** happen. `value_text` is overwhelmingly free
descriptive prose, not a repeated controlled vocabulary. `predicate` carries
no structure either — it merely repeats `layer_id` on every row.

> Note: your state summary said 20,731 assertions / 20,110 placeholders. Live
> now shows 20,624 active / 20,110 placeholder — the placeholder count matches
> exactly; the small total delta is normal drift and does not affect findings.

---

## 1. The decisive structural fact: only 6 of 18 layers have an ontology

| Bucket | Layers | Placeholder rows | Share |
|---|---|---|---|
| **Ontology-backed** (normalisation applies) | 6 | **6,227** | 31.0% |
| **No ontology target** (descriptive by design) | 12 | **13,883** | 69.0% |

The 12 no-target layers — `SEMANTIC_NARRATIVE`, `GLOBAL_ASSET_UNDERSTANDING`,
`COMPOSITION`, `CINEMATOGRAPHY`, `PERSON_APPEARANCE`, `PEOPLE_ROLES`,
`OCR_VISIBLE_TEXT`, `SPEECH_TRANSCRIPT_AUDIO`, `TEMPORAL_SCENE_STRUCTURE`,
`SEARCH_EMBEDDINGS`, `MARKETING_CONTENT_USAGE`, `ASSET_IDENTITY_PROVENANCE` —
have **no** corresponding controlled vocabulary among the six seeded tables
(`treatments`, `anatomy_terms`, `actions`, `clinical_observation_definitions`,
`locations`, `relationship_types`). Their free text (transcripts, narratives,
OCR dumps, filenames, appearance descriptions) is not something you "map to a
code" — it is content. Treating all 20,110 rows as a single mapping backlog
overstates the problem by ~3×.

**Normalisation, correctly scoped, is a ~6,227-row problem in 6 layers.**

---

## 2. Per-layer auto-map coverage (the 6 ontology-backed layers)

Matching cascade, best-match-wins per distinct value:
`exact` (normalised string equality) → `containment` (ontology term appears as
a whole word, word-boundary regex) → `trigram` (`word_similarity(term, value)
≥ 0.6`). Exact+containment = **high confidence**; trigram-only = low.

| Layer | Rows | High-conf | High % | Trigram-only | Unmapped | Unmapped % | One-to-many rows |
|---|--:|--:|--:|--:|--:|--:|--:|
| ANATOMY | 1,495 | 1,352 | **90.4%** | 36 | 107 | 7.2% | 974 |
| CLINICAL_VISUAL_OBSERVATIONS | 1,433 | 549 | 38.3% | 67 | 817 | 57.0% | 121 |
| ACTIONS_EVENTS | 1,507 | 103 | 6.8% | 167 | 1,237 | 82.1% | 10 |
| ENVIRONMENT | 705 | 101 | 14.3% | 278 | 326 | 46.2% | 18 |
| RELATIONSHIPS | 1,067 | 0 | **0.0%** | 27 | 1,040 | 97.5% | 0 |
| TREATMENT_PROCEDURE | 8 | 1 | 12.5% | 3 | 4 | — | 0 |
| **Total (mappable)** | **6,215** | **2,106** | **33.8%** | 578 | 3,531 | | 1,123 |

(Row counts here exclude NULL `value_text`: 7 NULL in TREATMENT, 3 in
ENVIRONMENT, 2 in CLINICAL — those placeholder rows are literally empty.)

**One-to-many is real and matters.** In ANATOMY, 974 rows already contain ≥2
distinct anatomy codes in one string (e.g. *"Scalp, hairline, ear, and facial
profile visible"* → SCALP + FRONTAL_HAIRLINE + FACE …). Any repair must emit
multiple assertions per source row, not overwrite one code. See
`mapping_candidates.csv` (one row per value×code).

---

## 3. Headline answers to the four questions

### Q1 — What % of the 20,110 auto-maps at high confidence?

**~10.5%** (2,106 rows). Almost all of it is ANATOMY (1,352) plus part of
CLINICAL (549). Including low-confidence trigram matches raises it to ~13.3%
(2,684 rows). The ceiling is low because 69% of rows have no ontology at all
and, among the six that do, only ANATOMY maps cleanly.

Restated on the honest denominator (the 6,227 mappable rows): **33.8%**
auto-map at high confidence.

### Q2 — Which layers map worst, and why?

- **RELATIONSHIPS — 0% auto.** Not because it's hard, but because the eight
  ontology *names* are compound phrases ("Doctor Treating Patient") that never
  appear verbatim; the prose says "practitioner-patient interaction",
  "clinician-patient interaction", "caregiver-patient", "provider-patient".
  These collapse to ~4 concepts. **A ~30-entry synonym dictionary lifts this
  from 0% to near-total.** Worst by string-matching, cheapest by hand.
- **ACTIONS_EVENTS — 6.8%.** Full descriptive sentences ("Clinician positions
  device near patient's face"). The salient verb is embedded/paraphrased and
  usually collapses to a generic (USING_DEVICE); ~1/3 are "No action depicted."
  Needs verb extraction / LLM classification, not string matching.
- **ENVIRONMENT — 14.3%.** **Target mismatch.** `locations` is a room-type
  vocabulary (Clinic, Treatment Room…), but the ENVIRONMENT layer describes
  *backdrops and surfaces*: "blue backdrop" (196), "wall" (148), "studio" (76),
  "drape" (71), "marble" (49). Most ENVIRONMENT prose is not about location.
- **CLINICAL_VISUAL_OBSERVATIONS — 38.3%.** Partially maps; definition labels
  are specific ("Crow's feet visible") while prose is descriptive ("small red
  marks on cheek"). Needs semantic mapping for the tail.
- **Best: ANATOMY — 90.4%.** Anatomical nouns appear literally; containment
  works and naturally yields the multi-code splits.

### Q3 — What ontology terms are missing that the data clearly needs?

Evidence = highest-frequency unmapped tokens (see also `unmapped.csv`).

**`anatomy_terms` (face/scalp-only today; data covers the whole upper body):**
- Missing regions: **HEAD** (180), **EAR/EARS** (226), **JAW** (163; only
  JAWLINE exists), **HAIR** (106; only SCALP exists), **SKIN** (93), **EYE/EYES**
  (72), **MOUTH** (60), **SHOULDER(S)** (81), **ARM** (50), **FOREARM** (42),
  **HAND(S)** (34).
- Missing **aliases** (biggest single lever): singular/plural and synonyms —
  ear/ears, cheek/cheeks, lip/lips, eyebrow→BROW, periorbital→PERIOCULAR.
- View descriptors (profile, posterior, anterior) belong in a viewpoint/
  cinematography layer, not anatomy.

**`locations` / ENVIRONMENT:** needs a *backdrop/setting* vocabulary that does
not exist — e.g. SOLID_COLOUR_BACKDROP, STUDIO_BACKDROP, DRAPED_CLINICAL,
MARBLE_SURFACE, PLAIN_WALL — distinct from physical room type.

**`treatments`:** needs a **Norwood staging scale as values** (Norwood I–VII +
A variants). Today there is only a `NORWOOD_GRADE_VERIFIED` observation
*definition* with no graded values — **and the data contains zero "norwood"
mentions anyway** (see Q4), so this is a data gap before it is an ontology gap.
Also worth structuring: graft count as a numeric.

**`relationship_types`:** codes are adequate; what's missing is an alias table
(like `treatment_aliases`) for the paraphrases above.

### Q4 — Is Treatment recoverable from existing prose, or does it need media re-analysis?

**It needs media re-analysis. This is the expensive fix, not the cheap one.**

- The `TREATMENT_PROCEDURE` layer itself is empty of signal: **15 active
  placeholder rows total** (7 NULL, most of the rest "No treatment depicted").
  Plus 5 genuine-code rows. That is ~20 treatment assertions across 877 assets.
- Searching **every** active assertion's prose for treatment keywords: only
  **223 / 877 assets** contain any treatment-adjacent term, and **183 of those
  are just "hairline"** (an anatomy mention, not a procedure being performed).
  Genuine procedure signal is far thinner:

  | Signal | Assets |
  |---|--:|
  | Hair-transplant (fue/graft/transplant/donor/recipient/implant) | 42 |
  | Energy/laser/HIFU/RF/microneedling | 35 |
  | PRP | 2 |
  | Injectables (botox/filler/dermal) | 2 |
  | **Any real procedure signal (excl. bare "hairline")** | **~tens, not hundreds** |

- **654 / 877 assets have no treatment signal anywhere** in their prose.
- **"norwood" appears literally 0 times** in 20k+ assertions.

The prose describes what a frame *looks like* (anatomy visible, device near
face, clinical backdrop) but rarely names the procedure. You cannot recover
Treatment for the 863/877 UNKNOWN assets by mapping existing text — the
information was never extracted. Recovering it requires re-analysing the media
with a treatment-aware prompt/model. **The 863/877 Treatment-UNKNOWN problem is
an expensive, media-re-analysis problem, not a mechanical mapping problem.**

---

## 4. Verdict: a week of mechanical mapping, or harder?

Both — depending on the layer. Split the ~6,227-row mappable population:

| Track | Layers | ~Rows | Effort |
|---|---|--:|---|
| **Mechanical** (this week) | ANATOMY (90% auto + 1-to-many splitter + ~15 new terms/aliases), RELATIONSHIPS (hand-built synonym dict) | ~2,560 | ≈1 week, high confidence |
| **Semantic / LLM-assisted** | CLINICAL_VISUAL_OBSERVATIONS, ACTIONS_EVENTS, ENVIRONMENT (needs classification + a backdrop vocab for ENV) | ~3,650 | days–weeks, needs review |
| **Media re-analysis** | TREATMENT_PROCEDURE (+ Norwood, marketing) | data absent | expensive; new extraction pass |
| **Out of scope for mapping** | 12 descriptive layers | 13,883 | leave as prose / index for text+vector search |

Bottom line: the normalisation *repair* (ontology mapping) is a ~1-week
mechanical job for ANATOMY + RELATIONSHIPS and a bounded LLM-assisted job for
the three descriptive-clinical layers. But the business-visible symptom —
Treatment/Marketing UNKNOWN on almost every asset — is **not** fixed by any
amount of mapping, because that data does not exist in the prose. That part
requires a fresh, treatment-aware analysis pass over the media.

---

## Files

- `mapping_candidates.csv` — 4,836 rows: `layer_id, value_text, occurrences,
  proposed_code, match_method, similarity_score`. One row per value×code
  (one-to-many preserved). Methods: exact / containment / trigram.
- `unmapped.csv` — 12,926 distinct values with no candidate, ranked by
  frequency: `layer_id, value_text, occurrences, layer_has_ontology`. The
  `layer_has_ontology=false` rows are the 12 descriptive layers (unmapped by
  design); `=true` rows are the actionable gaps in the six ontology-backed
  layers.
