# KDI AI Search V3 — Phase 7 OCR / Visible Text Intelligence

## Status

Phase 7 is **PASS** in shadow mode. The locked `semantic_index_v1` fingerprint is `ea74ef9c07f8341342817bc924d78fb6ae28049a8a29b6c571172a77c923308c`.

## Pipeline

- Processor: `kdi_ocr_intelligence_v1`
- Configuration: `kdi_ocr_intelligence_config_v1`
- Configuration fingerprint: `3749888c499007c0d77a4530ffa069549ba3ad216f3333247fc02c74318fd280`
- Lightweight detector: local OpenCV blackhat/tophat, Sobel, morphology, and adaptive track grouping
- Recognizer: local EasyOCR 1.7.2, English model, CPU, rotation-aware
- Embeddings: deferred because the approved Ollama service remains unavailable and OpenAI quota remains unavailable
- External media transmission: none

Every one of the 3,824 decodable pilot-video frames participated in text-presence detection. Phase 3 keyframes were always added to the recognition candidates. Expensive OCR was limited to the six strongest text tracks per video plus all Phase 3 keyframes. This bounded policy prevents texture false positives from causing unbounded OCR calls. When lower-ranked candidates remain unevaluated and no credible text is found, the asset is `UNKNOWN`, never `FALSE`.

Both pilot images were orientation-normalized for analysis and scanned in full. Their original files were not modified.

## Results

| Asset | Frames scanned | OCR frames | Layer 15 state | Search result |
| --- | ---: | ---: | --- | --- |
| IMG_0531.MP4 | 147/147 | 9 | UNKNOWN | None |
| IMG_1238.MP4 | 1,158/1,158 | 14 | OBSERVED | `M-CURE` accepted; three `~CURE` variants require review |
| IMG_3429.MP4 | 619/619 | 11 | UNKNOWN | None |
| IMG_9871.MOV | 459/459 | 9 | UNKNOWN | None |
| DSC03753.JPG | full image | 1 | FALSE | No credible text after completed full-image scan |
| DSC08097.JPG | full image | 1 | FALSE | No credible text after completed full-image scan |
| IMG_0493.MP4 | 113/113 | 7 | UNKNOWN | None |
| IMG_1148.MP4 | 231/231 | 10 | UNKNOWN | None |
| IMG_2963.MP4 | 387/387 | 10 | UNKNOWN | False-positive mask texture rejected |
| IMG_1160.MP4 | 710/710 | 18 | UNKNOWN | None |

The processor retained 19 OCR observations: one accepted for search, three queued for review, and fifteen rejected as gibberish/noise. All video observations have bounding boxes, normalized coordinates, timestamps, and valid Phase 3 scene links. Nine overlap technical event windows; overlap is recorded only as temporal evidence.

## Legacy image conflict reconciliation

The prior `NO_VISIBLE_TEXT` / legacy-complete claims for DSC03753.JPG and DSC08097.JPG had zero traceable evidence and were not imported. Phase 7 independently completed full-image detection and recognition. Both now have shadow conclusion `FALSE / NO_TEXT_SUPPORTED`. Production legacy records remain unchanged.

## Search and semantic safety

- OCR mentions remain distinct from visual treatment facts.
- `M-CURE` is a visible branding mention, not proof of treatment or procedure.
- Three leading-symbol variants (`~CURE`) require review and are not searchable.
- The `CUF` result on mask texture was rejected by a generic short-token safety rule; no filename-specific semantic rule exists.
- No OCR/visual or OCR/transcript claim was promoted automatically. Reconciliation contains one `UNRELATED` and eighteen `UNCERTAIN` visual relations; all nineteen transcript relations remain `UNCERTAIN`.
- Exact fingerprints exist for accepted OCR search text. OCR embeddings are deferred.

## Validation

Fourteen targeted tests pass, including local clear-text recognition, absent text, rotated text detection, low contrast detection, brief video text, persistent-caption grouping, changing-screen splitting, failure-to-`UNKNOWN`, coordinates, timestamps, scene links, idempotency, and external-media safety.

Production counts before and after are identical. No migration, OCR row, semantic row, search-document row, or embedding row was written.

## Known limitations

- The lightweight detector is deliberately sensitive and produced 6,040 technical tracks on the pilots, many from clinical textures and edges. The bounded recognition policy and `UNKNOWN` fallback prevent these from becoming unsupported negatives or searchable noise.
- Small, blurred, oblique, multilingual, and perspective-distorted text may remain unresolved.
- The local EasyOCR configuration contains only the English recognition model; language is reported conservatively as `ENGLISH_OR_MALAY` or `UNKNOWN_OR_TOKEN`.
- CPU rotation-aware recognition took about 580 seconds for this pilot run.
- OCR embeddings remain deferred pending the approved text-embedding infrastructure.

Phase 8 was not started.
