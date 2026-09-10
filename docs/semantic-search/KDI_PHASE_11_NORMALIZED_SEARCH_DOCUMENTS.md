# KDI Phase 11 Normalized Search Documents

Phase 11 adds versioned, authorization-aware retrieval documents without replacing the canonical 18-layer semantic database. The deployed version is `kdi_search_document_v1`, built by `kdi_search_document_builder_v1` with configuration `kdi_search_document_config_v1`.

## Source and truth contract

Documents use effective canonical assertions and canonical scene, event, narrative, transcript, and OCR records. Signed gold wins over reviewed canonical facts, which win over current AI facts. Legacy `asset_search_documents`, `scene_search_documents`, and AI-profile JSON are comparison inputs only and never fallback truth. `UNKNOWN` and `NOT_APPLICABLE` are omitted from positive retrieval concepts. `FALSE` is stored only as a negative signal and requires the evidence protections supplied by Phase 10.

The current pilot canonical assertion, event, transcript, and OCR sources are empty. The provisional build therefore contains safe metadata documents and valid video timing, but no promoted legacy semantic concepts. All records are `AI_UNREVIEWED`, `human_approved=false`, and have no gold version.

## Storage

- `search_document_build_runs`: one row per builder execution and aggregate counts/errors.
- `search_document_builds`: versioned ASSET, SCENE, and EVENT normalized JSON, natural search text, generated `tsvector`, fingerprints, review state, lifecycle, and supersession.
- `search_document_concepts`: normalized observed/negative concepts with assertion lineage.
- `search_document_evidence`: assertion/evidence and asset/scene/event/keyframe/transcript/OCR references.
- `asset_search_concepts_v2`: canonical source concept table retained for semantic ingestion; Phase 11 does not populate it from legacy facts.

Only one canonical version is active for each asset/scope/version. An identical replay updates run metadata without adding an active duplicate. A changed source fingerprint deactivates and marks the old document stale, inserts a replacement, and preserves supersession history.

## Retrieval contract for Phase 17

Future candidate retrieval may use `search_vector`/`search_text`, filename, media type, document type, concept code/type/state, asset ID, scene/event IDs and timing, accepted OCR/transcript fields, and evidence-linked structured assertions. The GIN full-text index is one channel and does not replace vectors. Phase 11 does not implement retrieval, ranking, parsing, or embedding generation.

## Security

Document, concept, and evidence reads use `private.can_user_view_asset(asset_id)` through RLS. Client writes are revoked. Build-run internals are backend-only. Tests set an authenticated identity with no authorization and verify zero document, full-text, concept, and evidence rows.

## Rebuild triggers

Canonical assertion, gold override, scene/event structure, transcript, OCR, narrative, or relevant ontology display changes alter the source semantic fingerprint and stale affected documents. An embedding-only change does not stale search documents. A later human-gold build uses the same pipeline and creates a new historical version without mutating the AI original.

## Pilot result

The exact ten frozen pilots produced 10 asset documents and 8 valid video-scene documents. The two still images produced no temporal documents. No canonical semantic events existed, so no event documents were generated. IMG_1238 retains `review_required=true` and `under_segmentation_possible=true`; no treatment or M-CURE claim was introduced because canonical OCR is absent.
