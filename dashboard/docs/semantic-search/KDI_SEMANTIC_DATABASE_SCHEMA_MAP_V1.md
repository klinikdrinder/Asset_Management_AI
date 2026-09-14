# KDI Semantic Database Schema Map V1

Deployment status: live and validated. All 17 Phase 10 semantic tables have RLS enabled; both semantic views use `security_invoker`.

```text
assets
  ├─ semantic_analysis_runs
  │    ├─ asset_semantic_layers ── semantic_layer_definitions (18 locked rows)
  │    ├─ semantic_assertions
  │    │    └─ semantic_assertion_evidence
  │    ├─ semantic_narratives ── narrative_claims ── narrative_claim_evidence
  │    ├─ asset_search_concepts_v2
  │    ├─ search_document_builds (metadata only)
  │    └─ semantic_embeddings (versioned, mixed-dimension safe)
  │
  ├─ asset_scenes
  │    ├─ asset_events
  │    ├─ asset_keyframes
  │    ├─ scene_people ── person_appearances
  │    ├─ scene_anatomy / scene_treatments / scene_actions
  │    ├─ scene_relationships / clinical_observations
  │    └─ scene_environment / scene_cinematography / scene_composition
  │
  ├─ asset_transcript_chunks
  ├─ ocr_observations
  └─ asset_access_control (authorization boundary)

semantic_review_sessions
  └─ semantic_review_decisions
       └─ semantic_review_revisions (append-only history)

gold_standard_sets
  └─ gold_standard_assets
       └─ gold_standard_assertions (signed revisions immutable)

effective_semantic_assertions (security-invoker precedence view)
current_asset_semantic_state (security-invoker 18-layer summary view)
```

All assertion/evidence foreign keys point back to their asset and, where applicable, scene, event, keyframe, transcript chunk, OCR observation, analysis run, review, or gold revision. Domain tables remain normalized sources; the assertion layer makes their facts consistently searchable and evidence-aware.
