# FIX 2 — People and Appearance Ontology

Canonical source: `config/semantic-search/kdi_people_appearance_ontology_v1.json`.

The file locks all requested vocabularies for role, gender presentation, hair color/length/density/hairline, clothing color/type, posture, and visibility. Numeric apparent-age ranges remain arbitrary min/max values, not fixed buckets. `NAVY`, `BLUE`, and `LIGHT_BLUE` remain distinct stored values even though a later retrieval layer may relate them.

The synonym map covers the requested foundations: male/man/gentleman; patient/client; doctor/physician/clinician; receding and frontal hairline phrases; blue/navy/light-blue clothing phrases; shirt/top; and posture variants. This ontology is intentionally marked `parser_connected: false`: FIX 2 does not change query parsing or production ranking.

Unknown values are never expanded into invented facts. Gender presentation is only materialized from explicit evidence. Apparent age is never inferred from exact-age wording or vague descriptions such as “young.”

## Provenance priority

1. Human review — 100
2. High-confidence structured visual analysis — 80
3. Verified structured assertion — 60
4. Free-text AI assertion — 40
5. Unknown — 0

Lower-ranked materialization is not permitted to overwrite a higher-ranked active value.

