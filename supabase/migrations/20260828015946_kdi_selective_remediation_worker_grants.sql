grant select on public.assets,public.asset_ai_profiles,public.asset_semantic_layers,
  public.semantic_assertions,public.semantic_assertion_evidence,
  public.asset_transcript_chunks,public.ocr_observations to service_role;

grant select,insert,update on public.semantic_analysis_runs,public.semantic_narratives,
  public.narrative_claims,public.narrative_claim_evidence,
  public.search_document_build_runs,public.search_document_builds,
  public.search_document_concepts,public.search_document_evidence,
  public.semantic_embeddings,public.semantic_remediation_model_calls to service_role;
