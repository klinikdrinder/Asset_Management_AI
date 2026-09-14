# FIX 2 — Materialization Contract

Implementation: `dashboard/db/people-appearance-materializer.ts`.

The materializer is deterministic and side-effect free. It accepts an explicitly scoped assertion bundle plus exactly one `(asset_id, scene_id, person_id)` context. It normalizes only supported ontology terms, generates stable SHA-256 materialization/evidence keys, carries the lowest source confidence conservatively, and returns proposed person, appearance, and field-evidence records. It performs no database writes.

Rules:

- Callers must split evidence by person before invoking the materializer; asset-wide or multi-person prose must not be silently assigned to one person.
- Output preserves the same asset, scene, and person key across person, appearance, and evidence records.
- Unsupported, empty, or UNKNOWN-only input produces no invented record.
- Exact age and vague age language are ignored; a later approved structured range extractor must provide min/max explicitly.
- Human-approved assertions receive authority 100; ordinary free-text assertions receive 40.
- If an active value has higher authority, the materializer returns no replacement.
- Idempotency keys allow future writers to use conflict-safe inserts without duplication.

FIX 2 includes only the pure transformation contract and a read-only dry-run harness. A future backfill must add a reviewed person-binding stage before any writes.

