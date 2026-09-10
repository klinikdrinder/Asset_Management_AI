import { createHash } from "node:crypto";
import type { SupabaseClient } from "@supabase/supabase-js";

export const SEMANTIC_STATES = ["OBSERVED", "FALSE", "UNKNOWN", "NOT_APPLICABLE"] as const;
export const EVIDENCE_TYPES = ["ASSET_LEVEL", "SCENE_LEVEL", "EVENT_LEVEL", "KEYFRAME_LEVEL", "TRANSCRIPT", "OCR", "HUMAN_REVIEW"] as const;
export const ORIGINS = ["AI_MODEL", "DETERMINISTIC_PROCESSOR", "DATABASE_METADATA", "HUMAN_REVIEW"] as const;
export type SemanticState = typeof SEMANTIC_STATES[number];

type Row = Record<string, unknown>;
function fingerprint(value: unknown) { return createHash("sha256").update(JSON.stringify(value)).digest("hex"); }

export class SemanticRepository {
  constructor(private readonly db: SupabaseClient) {}

  async createAnalysisRun(input: Row) {
    const row = { semantic_spec_version: "semantic_index_v1", ontology_version: "KDI_SEMANTIC_V2", status: "QUEUED", ...input };
    return this.one(this.db.from("semantic_analysis_runs").upsert(row, { onConflict: "asset_id,run_type,source_fingerprint,processor_version,configuration_fingerprint" }).select().single());
  }

  async upsertLayerStatus(input: Row) {
    return this.one(this.db.from("asset_semantic_layers").upsert(input, { onConflict: "asset_id,layer_id,analysis_run_id" }).select().single());
  }

  async insertAssertions(rows: Row[]) {
    const normalized = rows.map((row) => ({ ...row, idempotency_key: row.idempotency_key ?? fingerprint(row) }));
    return this.many(this.db.from("semantic_assertions").upsert(normalized, { onConflict: "idempotency_key", ignoreDuplicates: true }).select());
  }

  async attachEvidence(rows: Row[]) { return this.many(this.db.from("semantic_assertion_evidence").insert(rows).select()); }
  async writeSceneSemantics(rows: Row[]) { return this.many(this.db.from("asset_scenes").upsert(rows, { onConflict: "asset_id,scene_index" }).select()); }
  async writeEventSemantics(rows: Row[]) { return this.many(this.db.from("asset_events").insert(rows).select()); }
  async writeTranscriptChunks(rows: Row[]) { return this.many(this.db.from("asset_transcript_chunks").insert(rows).select()); }
  async writeOcrObservations(rows: Row[]) { return this.many(this.db.from("ocr_observations").insert(rows).select()); }
  async writeNarratives(rows: Row[]) { return this.many(this.db.from("semantic_narratives").insert(rows).select()); }
  async recordReviewDecision(decision: Row) { return this.one(this.db.from("semantic_review_decisions").insert(decision).select().single()); }

  async resolveEffectiveSemantics(assetId: string) {
    return this.many(this.db.from("effective_semantic_assertions").select("*").eq("asset_id", assetId));
  }

  async markDownstreamStale(assetId: string, changed: "SOURCE"|"OCR"|"TRANSCRIPT"|"ONTOLOGY"|"EMBEDDING") {
    const scopes: Record<typeof changed, string[]> = {
      SOURCE: ["ASSET","SCENE","EVENT","TRANSCRIPT","OCR","NARRATIVE"], OCR: ["OCR","NARRATIVE"],
      TRANSCRIPT: ["TRANSCRIPT","NARRATIVE"], ONTOLOGY: ["ASSET","SCENE","EVENT","NARRATIVE"], EMBEDDING: [],
    };
    const embeddingQuery = this.db.from("semantic_embeddings").update({ stale: true }).eq("asset_id", assetId);
    const documentQuery = this.db.from("search_document_builds").update({ status: "STALE" }).eq("asset_id", assetId);
    const assertions = scopes[changed].length
      ? this.db.from("semantic_assertions").update({ active: false }).eq("asset_id", assetId).in("subject_type", scopes[changed])
      : Promise.resolve({ error: null });
    const results = await Promise.all([embeddingQuery, documentQuery, assertions]);
    const error = results.find((result) => result.error)?.error;
    if (error) throw error;
  }

  private async one(query: PromiseLike<{ data: unknown; error: unknown }>) { const { data, error } = await query; if (error) throw error; return data; }
  private async many(query: PromiseLike<{ data: unknown; error: unknown }>) { const { data, error } = await query; if (error) throw error; return data ?? []; }
}
