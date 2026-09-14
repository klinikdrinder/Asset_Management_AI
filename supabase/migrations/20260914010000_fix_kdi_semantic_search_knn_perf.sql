-- Fix match_kdi_semantic_search_embeddings: candidate-first KNN, enrich-after.
--
-- The prior version scored every compatible embedding (parameterized predicates disqualified the
-- partial HNSW index), materialized the join-heavy `canonical` CTE (5 LEFT JOINs) over all rows, and
-- then joined the aggregating view `kdi_search_ready_assets_v1` to the full scored set. The planner
-- nested-looped that view, so TEXT_ASSET (877 rows) took ~22.8s / 8.8M buffers and tripped the API
-- role's statement timeout, while the vector scan itself is ~16ms.
--
-- This version selects the nearest `fetchk` candidates FIRST (materialized), then enriches and applies
-- the search-ready view to that small set. The per-family branches use literal predicates and the
-- index's exact cast expression ((embedding)::public.vector(N) <=> ...), so the partial HNSW indexes
-- (semantic_embeddings_hnsw_e5_384_idx / _openclip_512_idx) are eligible; at small N the planner may
-- still choose the btree top-N, which is equally cheap. Branching by dimension also avoids casting a
-- 384-d query vector to vector(512) (which would error). Output columns and semantics are unchanged.

CREATE OR REPLACE FUNCTION public.match_kdi_semantic_search_embeddings(
  query_embedding vector, requested_representation text, requested_provider text, requested_model text,
  requested_model_version text, requested_dimension integer, result_limit integer DEFAULT 25,
  minimum_similarity real DEFAULT 0)
RETURNS TABLE(embedding_id uuid, asset_id uuid, filename text, representation_type text, raw_similarity real,
  scene_id uuid, event_id uuid, keyframe_id uuid, transcript_chunk_id bigint, ocr_observation_id uuid,
  time_start numeric, time_end numeric, source_document_id text, embedding_family text,
  embedding_dimension integer, evidence_source text)
LANGUAGE plpgsql STABLE SET search_path TO '' AS $function$
DECLARE
  k int      := greatest(1, least(coalesce(result_limit, 25), 100));
  fetchk int := least(greatest(k * 8, 200), 500);   -- over-fetch before ready/similarity filtering
  minsim real := greatest(-1, least(coalesce(minimum_similarity, 0), 1))::real;
BEGIN
  IF public.vector_dims(query_embedding) <> requested_dimension THEN RETURN; END IF;

  IF requested_provider = 'sentence_transformers' AND requested_model = 'intfloat/multilingual-e5-small'
     AND requested_dimension = 384 THEN
    RETURN QUERY
    WITH knn AS MATERIALIZED (
      SELECT e.id AS eid, e.asset_id AS aid, e.representation_type AS rep, e.scene_id AS sid, e.event_id AS evid,
             e.keyframe_id AS kid, e.transcript_chunk_id AS tid, e.ocr_observation_id AS oid,
             coalesce(e.metadata->>'source_unit_id', e.source_document_fingerprint) AS sdoc,
             'semantic_embeddings'::text AS esrc,
             (1 - ((e.embedding)::public.vector(384) OPERATOR(public.<=>) (query_embedding)::public.vector(384)))::real AS sim
      FROM public.semantic_embeddings e
      WHERE e.active AND NOT e.stale AND e.dimensions = 384
        AND e.provider = 'sentence_transformers' AND e.model = 'intfloat/multilingual-e5-small'
        AND e.representation_type = requested_representation AND e.model_version = requested_model_version
      ORDER BY (e.embedding)::public.vector(384) OPERATOR(public.<=>) (query_embedding)::public.vector(384)
      LIMIT fetchk
    )
    SELECT n.eid, a.id, a.file_name, n.rep, n.sim, n.sid, n.evid, n.kid, n.tid, n.oid,
           coalesce(tc.start_seconds, kf.timestamp_seconds, o.timestamp_seconds, ev.start_time, sc.start_seconds)::numeric,
           coalesce(tc.end_seconds, o.end_time, ev.end_time, sc.end_seconds)::numeric,
           n.sdoc, concat_ws(':', requested_provider, requested_model, requested_model_version), requested_dimension, n.esrc
    FROM knn n
    JOIN public.assets a ON a.id = n.aid
    JOIN public.kdi_search_ready_assets_v1 r ON r.asset_id = n.aid AND r.search_ready
    LEFT JOIN public.asset_scenes sc ON sc.id = n.sid
    LEFT JOIN public.asset_events ev ON ev.id = n.evid
    LEFT JOIN public.asset_keyframes kf ON kf.id = n.kid
    LEFT JOIN public.asset_transcript_chunks tc ON tc.id = n.tid
    LEFT JOIN public.ocr_observations o ON o.id = n.oid
    WHERE n.sim >= minsim
    ORDER BY n.sim DESC, n.eid
    LIMIT k;

  ELSIF requested_provider = 'open_clip' AND requested_model = 'ViT-B-32' AND requested_dimension = 512 THEN
    RETURN QUERY
    WITH knn AS MATERIALIZED (
      ( SELECT e.id AS eid, e.asset_id AS aid, e.representation_type AS rep, e.scene_id AS sid, e.event_id AS evid,
               e.keyframe_id AS kid, e.transcript_chunk_id AS tid, e.ocr_observation_id AS oid,
               coalesce(e.metadata->>'source_unit_id', e.source_document_fingerprint) AS sdoc,
               'semantic_embeddings'::text AS esrc,
               (1 - ((e.embedding)::public.vector(512) OPERATOR(public.<=>) (query_embedding)::public.vector(512)))::real AS sim
        FROM public.semantic_embeddings e
        WHERE e.active AND NOT e.stale AND e.dimensions = 512
          AND e.provider = 'open_clip' AND e.model = 'ViT-B-32'
          AND e.representation_type = requested_representation AND e.model_version = requested_model_version
        ORDER BY (e.embedding)::public.vector(512) OPERATOR(public.<=>) (query_embedding)::public.vector(512)
        LIMIT fetchk )
      UNION ALL
      ( SELECT v.id, v.asset_id, 'VISUAL_ASSET'::text, NULL::uuid, NULL::uuid, NULL::uuid, NULL::bigint, NULL::uuid,
               v.source_fingerprint, 'derived_legacy_visual_projection'::text,
               (1 - ((v.embedding)::public.vector(512) OPERATOR(public.<=>) (query_embedding)::public.vector(512)))::real
        FROM public.asset_visual_embeddings v
        WHERE requested_representation = 'VISUAL_ASSET' AND requested_model_version = 'laion2b_s34b_b79k'
          AND v.model_provider = 'open_clip' AND v.model_name = 'ViT-B-32'
          AND v.model_version = 'laion2b_s34b_b79k' AND v.embedding_dimensions = 512
        ORDER BY (v.embedding)::public.vector(512) OPERATOR(public.<=>) (query_embedding)::public.vector(512)
        LIMIT fetchk )
    )
    SELECT n.eid, a.id, a.file_name, n.rep, n.sim, n.sid, n.evid, n.kid, n.tid, n.oid,
           coalesce(tc.start_seconds, kf.timestamp_seconds, o.timestamp_seconds, ev.start_time, sc.start_seconds)::numeric,
           coalesce(tc.end_seconds, o.end_time, ev.end_time, sc.end_seconds)::numeric,
           n.sdoc, concat_ws(':', requested_provider, requested_model, requested_model_version), requested_dimension, n.esrc
    FROM knn n
    JOIN public.assets a ON a.id = n.aid
    JOIN public.kdi_search_ready_assets_v1 r ON r.asset_id = n.aid AND r.search_ready
    LEFT JOIN public.asset_scenes sc ON sc.id = n.sid
    LEFT JOIN public.asset_events ev ON ev.id = n.evid
    LEFT JOIN public.asset_keyframes kf ON kf.id = n.kid
    LEFT JOIN public.asset_transcript_chunks tc ON tc.id = n.tid
    LEFT JOIN public.ocr_observations o ON o.id = n.oid
    WHERE n.sim >= minsim
    ORDER BY n.sim DESC, n.eid
    LIMIT k;

  ELSE
    -- Generic fallback for any other embedding identity: still candidate-first (no fixed-dim cast, so
    -- no HNSW, but bounded work), preserving correctness for future families.
    RETURN QUERY
    WITH knn AS MATERIALIZED (
      SELECT e.id AS eid, e.asset_id AS aid, e.representation_type AS rep, e.scene_id AS sid, e.event_id AS evid,
             e.keyframe_id AS kid, e.transcript_chunk_id AS tid, e.ocr_observation_id AS oid,
             coalesce(e.metadata->>'source_unit_id', e.source_document_fingerprint) AS sdoc,
             'semantic_embeddings'::text AS esrc,
             (1 - (e.embedding OPERATOR(public.<=>) query_embedding))::real AS sim
      FROM public.semantic_embeddings e
      WHERE e.active AND NOT e.stale AND e.representation_type = requested_representation
        AND e.provider = requested_provider AND e.model = requested_model
        AND e.model_version = requested_model_version AND e.dimensions = requested_dimension
        AND public.vector_dims(e.embedding) = requested_dimension
      ORDER BY e.embedding OPERATOR(public.<=>) query_embedding
      LIMIT fetchk
    )
    SELECT n.eid, a.id, a.file_name, n.rep, n.sim, n.sid, n.evid, n.kid, n.tid, n.oid,
           coalesce(tc.start_seconds, kf.timestamp_seconds, o.timestamp_seconds, ev.start_time, sc.start_seconds)::numeric,
           coalesce(tc.end_seconds, o.end_time, ev.end_time, sc.end_seconds)::numeric,
           n.sdoc, concat_ws(':', requested_provider, requested_model, requested_model_version), requested_dimension, n.esrc
    FROM knn n
    JOIN public.assets a ON a.id = n.aid
    JOIN public.kdi_search_ready_assets_v1 r ON r.asset_id = n.aid AND r.search_ready
    LEFT JOIN public.asset_scenes sc ON sc.id = n.sid
    LEFT JOIN public.asset_events ev ON ev.id = n.evid
    LEFT JOIN public.asset_keyframes kf ON kf.id = n.kid
    LEFT JOIN public.asset_transcript_chunks tc ON tc.id = n.tid
    LEFT JOIN public.ocr_observations o ON o.id = n.oid
    WHERE n.sim >= minsim
    ORDER BY n.sim DESC, n.eid
    LIMIT k;
  END IF;
END
$function$;
