import { createHash } from "node:crypto";
import frozen from "../../config/semantic-search/kdi_semantic_search_spec_v1.json";

export const PRODUCTION_INDEXER_VERSION = "kdi_automatic_indexing_pipeline_v1";
export const PRODUCTION_CONFIGURATION_VERSION = "kdi_production_indexing_config_v1";
export const FROZEN_SEMANTIC_SPEC = "semantic_index_v1";
export const FROZEN_SEMANTIC_FINGERPRINT = "ba43dab744dedfd590e81be5c8ec5ec8ab7c0bda79f8aca16c0b24d198294888";
export const EMBEDDING_BUNDLE_VERSION = "kdi_embedding_bundle_v1";

export type EmbeddingFamily = "VISUAL_ASSET" | "TEXT_SEMANTIC";
export type EmbeddingConfig = { family: EmbeddingFamily; provider: string; model: string; modelVersion: string; dimensions: number; preprocessingVersion: string; normalizationVersion: string; activeForNewIndexing: boolean; metric: "cosine"; sourceDocument: string; };
export const PRODUCTION_EMBEDDINGS: readonly EmbeddingConfig[] = [
  { family: "VISUAL_ASSET", provider: "open_clip", model: "ViT-B-32", modelVersion: "laion2b_s34b_b79k", dimensions: 512, preprocessingVersion: "open_clip_preprocess_v1", normalizationVersion: "L2", activeForNewIndexing: true, metric: "cosine", sourceDocument: "canonical search document plus representative visual evidence" },
  { family: "TEXT_SEMANTIC", provider: "sentence_transformers", model: "intfloat/multilingual-e5-small", modelVersion: "hf-main-pinned-runtime-v1", dimensions: 384, preprocessingVersion: "search_text_v1", normalizationVersion: "Unicode NFKC + whitespace v1", activeForNewIndexing: true, metric: "cosine", sourceDocument: "kdi_search_document_v1 normalized search text" },
  { family: "TEXT_SEMANTIC", provider: "ollama", model: "qwen3-embedding:0.6b", modelVersion: "v1", dimensions: 1024, preprocessingVersion: "legacy", normalizationVersion: "legacy", activeForNewIndexing: false, metric: "cosine", sourceDocument: "historical asset_embeddings" },
];

export function selectEmbedding(family: EmbeddingFamily, provider?: string): EmbeddingConfig {
  const candidates = PRODUCTION_EMBEDDINGS.filter(x => x.family === family && x.activeForNewIndexing && (!provider || x.provider === provider));
  if (candidates.length !== 1) throw new Error(`EMBEDDING_CONFIGURATION_AMBIGUOUS:${family}`);
  return candidates[0];
}
export function assertCompatibleVector(a: EmbeddingConfig, b: EmbeddingConfig): void {
  if (a.family !== b.family || a.provider !== b.provider || a.model !== b.model || a.modelVersion !== b.modelVersion || a.dimensions !== b.dimensions) throw new Error("MIXED_EMBEDDING_FAMILY_REJECTED");
}
export function productionConfigurationFingerprint(): string {
  const value = { configurationVersion: PRODUCTION_CONFIGURATION_VERSION, spec: FROZEN_SEMANTIC_SPEC, specFingerprint: FROZEN_SEMANTIC_FINGERPRINT, ontology: frozen.specification.ontology_version, evidence: "phase10_semantic_assertion_evidence_v1", searchDocument: "kdi_search_document_v1", pipeline: PRODUCTION_INDEXER_VERSION, embeddingBundle: EMBEDDING_BUNDLE_VERSION, embeddings: PRODUCTION_EMBEDDINGS };
  return createHash("sha256").update(JSON.stringify(value, Object.keys(value).sort())).digest("hex");
}

export const FROZEN_LAYER_IDS = (frozen.layers as Array<{id:string}>).map(x => x.id);
export const LEGACY_LAYER_COMPATIBILITY = Object.freeze(FROZEN_LAYER_IDS.map((id, i) => ({ frozenLayerId: id, frozenLayerNumber: i + 1, frozenLayerName: (frozen.layers as any[])[i].name, legacyEquivalent: [id], compatibilityStatus: "DETERMINISTIC_EXPLICIT", newWriteTarget: "asset_semantic_layers.layer_id" })));
export function validateFrozenLayerSet(ids: string[]): void { if (ids.length !== 18 || new Set(ids).size !== 18 || ids.some(id => !FROZEN_LAYER_IDS.includes(id))) throw new Error("FROZEN_LAYER_SET_INVALID"); }

export type EnrollmentInput = { assetId: string; contentHash: string; mediaType: "IMAGE" | "VIDEO" | "DOCUMENT"; physicallyAvailable: boolean; unsupported?: boolean; alreadyComplete?: boolean; blockingIntegrityError?: boolean; activeClaim?: boolean; };
export function enrollmentDecision(input: EnrollmentInput) {
  if (!input.assetId || !input.contentHash) throw new Error("CANONICAL_IDENTITY_REQUIRED");
  if (input.unsupported) return { status: "UNSUPPORTED", eligible: false, realAnalysisRequired: false };
  if (input.alreadyComplete) return { status: "COMPLETE", eligible: false, realAnalysisRequired: false };
  const eligible = input.physicallyAvailable && !input.blockingIntegrityError && !input.activeClaim;
  return { status: eligible ? "PENDING_ANALYSIS" : "BLOCKED_BEFORE_ANALYSIS", eligible, realAnalysisRequired: true };
}
