# KDI AI Search V3 — Phase 4 Image Processing

## Status and scope

Phase 4 passes in shadow mode for exactly `DSC03753.JPG` and `DSC08097.JPG`. Phase 5 has not started. No semantic rows, embeddings, search documents, migrations, or source media were changed.

## Locked inputs

- Semantic specification: `semantic_index_v1`
- Specification fingerprint: `ea74ef9c07f8341342817bc924d78fb6ae28049a8a29b6c571172a77c923308c`
- Pilot manifest: `kdi_semantic_pilot_v1`
- Image processor: `kdi_image_analysis_v1`
- Configuration: `kdi_image_analysis_config_v1`
- Configuration fingerprint: `fb5563d46655a8c477802c57cfd52b6392ebb9b64e86f79d82430d5925844f13`

## Processing contract

The processor verifies SHA-256 identity before decoding, reads source metadata, and uses Pillow `ImageOps.exif_transpose` for analysis-only orientation normalization. The source file is never rewritten. `FULL_IMAGE` is always the primary evidence region and spans the complete analysis-oriented dimensions.

Low-cost deterministic brightness, contrast, second-difference sharpness, and directional edge statistics are calculated on a bounded analysis copy. Multi-scale edge/contrast tiles may create generic `OTHER_SALIENT_REGION` candidates. IoU and containment suppression remove duplicates, and no more than two generic crops are retained. Crops remain region evidence linked to the parent asset and are never registered as assets.

No safe person, face/head, anatomy, equipment, or text-region detector exists in the current dependencies. The processor therefore emits none of those region types and makes no corresponding semantic claim. It performs no face recognition, OCR, treatment inference, anatomy inference, embedding generation, or semantic completion.

## Applicability and negative assertions

For both images, Layer 3 and Layer 14 are `NOT_APPLICABLE`. Layer 15 remains `APPLICABLE` with state `UNKNOWN` until Phase 7 OCR. Missing OCR or treatment rows are not interpreted as negative evidence. The Phase 2 unsupported treatment/OCR completion claims and action-representation conflicts are copied into each shadow manifest as `PRESERVED_FOR_LATER_REVIEW`.

## Validation

Automated tests cover source fingerprint enforcement, Pillow loading, normal/portrait/landscape/square images, EXIF rotation without source rewriting, complete full-frame fallback, region coordinates and normalization, redundancy suppression, deterministic UUID5 output, technical metadata, version/fingerprint provenance, invalid/truncated image isolation, correct applicability, negative-assertion safety, and absence of a production write path.

Both pilot images passed functional repeat-run equivalence. Engineering review confirmed identity, orientation, full-frame coverage, coordinates, overlays, contact sheets, and conservative crop counts.

## Preservation

Production counts before and after Phase 4 are identical. Phase 3 remains `PASS`, its processor configuration fingerprint is unchanged, and the known `IMG_1238.MP4` review warning remains open.

## Stop condition

Phase 5 has not started. Phase 4 outputs remain local shadow artifacts only.
