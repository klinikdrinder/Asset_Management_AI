import assert from "node:assert/strict";
import test from "node:test";
import { LAYER_IDS, type DiscoveryEvent } from "../db/automatic-indexing-pipeline";
import { OpenAIProviderError, OpenAISemanticAnalysisProvider, SEMANTIC_RESULT_SCHEMA } from "../db/openai-semantic-analysis-provider";

const asset: DiscoveryEvent = { sourceId: "source-1", sourcePath: "fixture.mp4", filename: "fixture.mp4", contentHash: "hash-1", mediaType: "video/mp4", fileSize: 10, discoveredAt: 0 };
const pkg = { asset, durationMs: 1000, items: [{ id: "frame-1", kind: "frame" as const, timestampMs: 100, dataUrl: "data:image/jpeg;base64,AA==" }] };
const result = { specVersion: "kdi_semantic_18_layer_v1", specFingerprint: "6da50e2153f6fcb6c9ef27c308ad44d0d2024e702e3faad47586b0068ba64fd7", pipelineVersion: "kdi_automatic_indexing_pipeline_v1", layers: LAYER_IDS.map((layerId) => ({ layerId, semanticState: "UNKNOWN" as const, evidence: [{ source: "frame-1" }] })) };

test("external AI gate blocks before network", async () => {
  const old = { enabled: process.env.EXTERNAL_AI_ENABLED, key: process.env.OPENAI_API_KEY, model: process.env.SEMANTIC_ANALYSIS_MODEL };
  process.env.EXTERNAL_AI_ENABLED = "false"; process.env.OPENAI_API_KEY = "test"; process.env.SEMANTIC_ANALYSIS_MODEL = "test-model";
  let calls = 0;
  try { await assert.rejects(() => new OpenAISemanticAnalysisProvider(async () => { calls++; throw new Error("network"); }).analyze({ asset, modalities: ["visual"], specVersion: result.specVersion, specFingerprint: result.specFingerprint, evidencePackage: pkg }), (error: any) => error instanceof OpenAIProviderError && error.code === "EXTERNAL_AI_DISABLED"); assert.equal(calls, 0); }
  finally { process.env.EXTERNAL_AI_ENABLED = old.enabled; process.env.OPENAI_API_KEY = old.key; process.env.SEMANTIC_ANALYSIS_MODEL = old.model; }
});

test("enabled adapter sends bounded multimodal request and validates 18 layers", async () => {
  const old = { enabled: process.env.EXTERNAL_AI_ENABLED, key: process.env.OPENAI_API_KEY, model: process.env.SEMANTIC_ANALYSIS_MODEL };
  process.env.EXTERNAL_AI_ENABLED = "true"; process.env.OPENAI_API_KEY = "test"; process.env.SEMANTIC_ANALYSIS_MODEL = "test-model";
  let body: any;
  try { const provider = new OpenAISemanticAnalysisProvider(async (_url, init) => { body = JSON.parse(String(init?.body)); return new Response(JSON.stringify({ output_text: JSON.stringify(result), usage: { input_tokens: 3, output_tokens: 4, total_tokens: 7 } }), { status: 200, headers: { "x-request-id": "req-test" } }); }); const actual = await provider.analyze({ asset, modalities: ["visual"], specVersion: result.specVersion, specFingerprint: result.specFingerprint, evidencePackage: pkg }); assert.equal(actual.layers.length, 18); assert.equal(body.text.format.type, "json_schema"); assert.deepEqual(body.text.format.schema, SEMANTIC_RESULT_SCHEMA); assert.equal(provider.lastUsage?.requestId, "req-test"); }
  finally { process.env.EXTERNAL_AI_ENABLED = old.enabled; process.env.OPENAI_API_KEY = old.key; process.env.SEMANTIC_ANALYSIS_MODEL = old.model; }
});

test("invalid evidence reference is rejected", async () => {
  const old = { enabled: process.env.EXTERNAL_AI_ENABLED, key: process.env.OPENAI_API_KEY, model: process.env.SEMANTIC_ANALYSIS_MODEL };
  process.env.EXTERNAL_AI_ENABLED = "true"; process.env.OPENAI_API_KEY = "test"; process.env.SEMANTIC_ANALYSIS_MODEL = "test-model";
  try { const invalid = { ...result, layers: result.layers.map((layer) => ({ ...layer, evidence: [{ source: "not-supplied" }] })) }; const provider = new OpenAISemanticAnalysisProvider(async () => new Response(JSON.stringify({ output_text: JSON.stringify(invalid) }), { status: 200 })); await assert.rejects(() => provider.analyze({ asset, modalities: ["visual"], specVersion: result.specVersion, specFingerprint: result.specFingerprint, evidencePackage: pkg }), (error: any) => error instanceof OpenAIProviderError && error.code === "INVALID_EVIDENCE_REFERENCE"); }
  finally { process.env.EXTERNAL_AI_ENABLED = old.enabled; process.env.OPENAI_API_KEY = old.key; process.env.SEMANTIC_ANALYSIS_MODEL = old.model; }
});
