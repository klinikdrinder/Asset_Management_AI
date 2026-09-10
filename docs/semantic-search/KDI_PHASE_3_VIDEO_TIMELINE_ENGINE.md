# KDI AI Search V3 — Phase 3 Video Timeline Engine

## Status

Phase 3 is complete in shadow mode. The processor does not write to production semantic tables and does not generate transcripts, OCR, embeddings, semantic labels, or search documents.

## Locked inputs

- Semantic specification: `semantic_index_v1`
- Specification fingerprint: `ea74ef9c07f8341342817bc924d78fb6ae28049a8a29b6c571172a77c923308c`
- Pilot manifest: `kdi_semantic_pilot_v1`
- Timeline processor: `kdi_video_timeline_v1`
- Configuration: `kdi_video_timeline_config_v1`
- Configuration fingerprint: `5f603465f41b03aaf59e1daeb85676cbe521bca9fbd9869ea57584da68dc4363`

## Architecture

FFprobe validates each source before processing. FFmpeg then decodes the complete video to a memory-only 160×90 grayscale raw-frame stream. Every decoded frame contributes visual difference, changed-pixel motion, histogram change, quadrant composition change, brightness, and edge-texture measurements. No large semantic model runs per frame.

Video-relative percentiles and configurable minimums normalize the signals. Debounced hard-cut and persistent soft-transition candidates partition the complete timeline into ordered, gap-free, non-overlapping scenes. Hysteresis merges local change spikes into generic event windows. Adaptive candidate sampling is sparse in stable regions and dense around boundaries and events. Keyframes represent scene start/end state, scene midpoint, boundaries, and event peaks; technical similarity removes redundant candidates while preserving distinct temporal roles.

All identifiers and functional outputs are deterministic for the source fingerprint, processor version, and configuration fingerprint. A failed asset produces an isolated `FAILED` result rather than terminating the library run.

## Timestamp limitation

The raw FFmpeg pipe does not expose individual presentation timestamps. Phase 3 timestamps therefore use decoded frame ordinal divided by the probed average frame rate. All eight pilots are constant-frame-rate according to the probe. A future variable-frame-rate implementation should use per-frame PTS from an appropriate decoder and must version that behavior.

## Pilot outcome

All eight frozen videos completed with 3,824 of 3,824 expected frames decoded and inspected, zero decode failures, and 100% measured decodable-timeline coverage. Shadow output contains 11 scene candidates, 22 non-semantic event candidates, and 44 retained keyframes after 432 redundant candidates were suppressed. Functional repeat-run equivalence passed for all eight videos.

`IMG_1238.MP4` remains flagged `POSSIBLE_UNDER_SEGMENTATION` because a 38.6-second clip with internal change signals produced one stable scene. Its six separately timed event windows and eight retained keyframes preserve the internal changes, but the scene decision should receive human review before ingestion.

## Validation

Synthetic fixtures are generated programmatically with FFmpeg and are not committed as binary media. The suite validates full traversal, monotonic timestamps, scene partitioning, event and keyframe linkage, hard cuts, a short controlled event, gradual transition, static-video false-positive control, continuous-motion robustness, adaptive sampling, redundancy suppression, deterministic repeat output, configuration fingerprinting, source fingerprint preservation, and failure isolation.

The controlled short-event fixture contains one known event. It was detected, retained a representative frame, and therefore achieved 1/1 (100%) controlled-fixture recall. This is not a semantic-event recall measurement for the pilot media.

## Shadow artifacts

Per-asset JSON manifests contain the full lightweight frame-signal series, technical metadata, scenes, events, keyframes, provenance, performance, warnings, and timeline review. Summary JSON/CSV, signal plots, and compact keyframe contact sheets are under `reports/semantic-search/phase3/`.

## Production preservation

Read-only production counts before and after Phase 3 are identical. No migration, semantic write, scene/keyframe replacement, embedding generation, transcript, OCR, search-document rebuild, ranking change, frontend change, or permission change occurred.

## Stop condition

Phase 4 has not started. The two pilot images were not processed.
