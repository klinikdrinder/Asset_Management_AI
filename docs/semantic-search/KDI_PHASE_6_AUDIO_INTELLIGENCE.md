# KDI AI Search V3 — Phase 6 Audio Intelligence

## Status

`PASS` in shadow mode. Exactly eight frozen pilot videos were processed for Layer 14. The two pilot images remain `NOT_APPLICABLE`.

## Pipeline

- Processor: `kdi_audio_intelligence_v1`.
- Configuration: `kdi_audio_intelligence_config_v1`; fingerprint `c90b3d1c7de34af15a93037b4e47229766306f2046de04fbcb89dea87396ba57`.
- Extraction: project-local FFmpeg 9.0 to temporary mono 16 kHz PCM WAV; temporary audio is deleted after each asset.
- Speech candidates: deterministic 30 ms RMS-energy VAD with adaptive noise floor, persistence, and merge controls.
- STT/language: local faster-whisper 1.2.1, multilingual `small`, CPU int8, segment and word timestamps.
- Diarization: unavailable. No approved local diarization model was configured, and the configured OpenAI project had insufficient quota. All speakers remain anonymous and roles remain unknown.
- Transcript embeddings: explicitly deferred. Local Ollama/Qwen embedding service was unreachable and the OpenAI project returned insufficient quota. Exact transcript-search-text fingerprints are present for future selective embedding.

## Authorization and provider handling

All eight live access-control records were rechecked immediately before processing and remained `external_ai_status=ALLOWED`, `review_status=REVIEWED`. Consent, clinical, marketing, viewing, downloading, and external-AI fields were kept separate.

One authorized OpenAI request for IMG_0531 was attempted and rejected with `insufficient_quota` before a transcript was returned. No other pilot audio was transmitted externally. Processing then used the local model exclusively.

## Results

- Speech: YES 4, NO 2, UNKNOWN 2.
- Timestamped transcript candidates: 14; all 14 scene-linked and 6 event-linked by deterministic temporal overlap.
- Search-accepted chunks: 3. Eleven low-confidence or otherwise uncertain chunks are retained for review but excluded from search acceptance.
- One repetitive transcription hallucination candidate was detected. Raw provider output remains traceable; normalized text uses an explicit unclear marker and is excluded from search.
- Canonical spoken topics: none promoted. The resulting visual/audio reconciliation is four `UNRELATED` and four `UNCERTAIN`; no Phase 5 package was modified.
- IMG_1238 remains `REVIEW_NEEDED`; audio did not provide reliable topic-change evidence supporting re-segmentation.

## Validation and safety

Twenty-one targeted Phase 3/5/6 tests pass. They cover extraction configuration, silence, an actual deterministic local single-speaker transcription fixture, separated segments, noise-plus-signal, corrupt/empty audio, provider failure, timestamps, scene/event overlap, unknown speaker fallback, ontology normalization, multilingual preservation, fingerprints, idempotency, authorization gating, Phase 3/5 evidence integrity, and forbidden production paths.

Production counts are identical before and after. No OCR, migration, production transcript insert, production embedding, search-document rebuild, visual-semantic change, or source-media modification occurred.

Phase 6 stops here. Phase 7 OCR has not started.
