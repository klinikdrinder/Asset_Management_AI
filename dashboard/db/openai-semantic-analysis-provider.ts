import {
  AUTOMATIC_PIPELINE_VERSION,
  LAYER_IDS,
  SEMANTIC_SPEC_FINGERPRINT,
  SEMANTIC_SPEC_VERSION,
  type DiscoveryEvent,
  type LayerEvaluation,
  type SemanticAnalysisProvider,
  type StructuredSemanticResult,
} from "./automatic-indexing-pipeline";

export const SEMANTIC_ANALYSIS_PROMPT_VERSION = "kdi_semantic_analysis_prompt_v1";
export const OPENAI_ADAPTER_VERSION = "kdi_openai_semantic_analysis_adapter_v1";

export type EvidenceItem = {
  id: string;
  kind: "frame" | "transcript" | "ocr" | "metadata";
  timestampMs?: number;
  endTimestampMs?: number;
  dataUrl?: string;
  text?: string;
  source?: string;
};

export type SemanticEvidencePackage = {
  asset: DiscoveryEvent;
  durationMs?: number;
  items: EvidenceItem[];
};

export type ProviderUsage = {
  requestId: string | null;
  model: string;
  startedAt: string;
  completedAt: string;
  durationMs: number;
  inputTokens: number | null;
  outputTokens: number | null;
  totalTokens: number | null;
  estimatedCost: number | null;
  retries: number;
};

export class OpenAIProviderError extends Error {
  constructor(public readonly code: string, message: string, public readonly retryable = false) {
    super(message);
    this.name = "OpenAIProviderError";
  }
}

const states = ["OBSERVED", "FALSE", "UNKNOWN", "NOT_APPLICABLE"] as const;

export const SEMANTIC_RESULT_SCHEMA = {
  type: "object",
  additionalProperties: false,
  required: ["specVersion", "specFingerprint", "pipelineVersion", "layers"],
  properties: {
    specVersion: { type: "string" },
    specFingerprint: { type: "string" },
    pipelineVersion: { type: "string" },
    layers: {
      type: "array",
      minItems: 18,
      maxItems: 18,
      items: {
        type: "object",
        additionalProperties: false,
        required: ["layerId", "semanticState", "evidence"],
        properties: {
          layerId: { type: "string", enum: LAYER_IDS },
          semanticState: { type: "string", enum: [...states] },
          evidence: {
            type: "array",
            minItems: 1,
            items: { type: "object", additionalProperties: false, required: ["source"], properties: { source: { type: "string" } } },
          },
        },
      },
    },
  },
} as const;

const instruction = `You are the KDI semantic analyzer. Return JSON only matching the supplied schema. Evaluate all 18 canonical layers exactly once. Use only supplied evidence identifiers and timestamps. Describe supported observations only; do not guess identity, treatment, anatomy, role, or intent. Use UNKNOWN when evidence is insufficient and NOT_APPLICABLE only when the modality is genuinely unavailable. Never invent evidence IDs. ${SEMANTIC_ANALYSIS_PROMPT_VERSION}.`;

function validateEvidencePackage(pkg: SemanticEvidencePackage): void {
  if (!pkg.items.length) throw new OpenAIProviderError("EMPTY_EVIDENCE_PACKAGE", "Evidence package is empty");
  const ids = new Set(pkg.items.map((item) => item.id));
  if (ids.size !== pkg.items.length || pkg.items.some((item) => !item.id.trim())) throw new OpenAIProviderError("INVALID_EVIDENCE_PACKAGE", "Evidence identifiers must be unique and non-empty");
  if (pkg.durationMs !== undefined && pkg.items.some((item) => item.timestampMs !== undefined && (item.timestampMs < 0 || item.timestampMs > pkg.durationMs!))) throw new OpenAIProviderError("INVALID_EVIDENCE_TIMESTAMP", "Evidence timestamp is outside the media duration");
}

function validateResult(result: StructuredSemanticResult, pkg: SemanticEvidencePackage): void {
  if (result.specVersion !== SEMANTIC_SPEC_VERSION || result.specFingerprint !== SEMANTIC_SPEC_FINGERPRINT) throw new OpenAIProviderError("SPEC_MISMATCH", "Provider result does not match the locked semantic specification");
  if (result.pipelineVersion !== AUTOMATIC_PIPELINE_VERSION) throw new OpenAIProviderError("PIPELINE_VERSION_MISMATCH", "Provider result does not match the indexing pipeline");
  if (result.layers.length !== 18 || new Set(result.layers.map((layer) => layer.layerId)).size !== 18 || result.layers.some((layer) => !LAYER_IDS.includes(layer.layerId))) throw new OpenAIProviderError("INVALID_LAYER_SET", "Provider did not return exactly the locked 18 layers");
  const ids = new Set(pkg.items.map((item) => item.id));
  for (const layer of result.layers) {
    if (!states.includes(layer.semanticState)) throw new OpenAIProviderError("INVALID_STATE", `Invalid state for ${layer.layerId}`);
    if (!layer.evidence.length || layer.evidence.some((evidence) => !evidence.source || !ids.has(evidence.source))) throw new OpenAIProviderError("INVALID_EVIDENCE_REFERENCE", `Invalid evidence reference for ${layer.layerId}`);
  }
}

export class OpenAISemanticAnalysisProvider implements SemanticAnalysisProvider {
  readonly providerName = "openai";
  readonly adapterVersion = OPENAI_ADAPTER_VERSION;
  lastUsage: ProviderUsage | null = null;
  constructor(private readonly fetchImpl: typeof fetch = fetch) {}

  async analyze(input: { asset: DiscoveryEvent; modalities: string[]; specVersion: string; specFingerprint: string; evidencePackage?: SemanticEvidencePackage }): Promise<StructuredSemanticResult> {
    if (String(process.env.EXTERNAL_AI_ENABLED ?? "false").toLowerCase() !== "true") throw new OpenAIProviderError("EXTERNAL_AI_DISABLED", "External AI is disabled; request blocked before network access");
    const key = process.env.OPENAI_API_KEY?.trim();
    const model = process.env.SEMANTIC_ANALYSIS_MODEL?.trim();
    if (!key) throw new OpenAIProviderError("OPENAI_CREDENTIALS_MISSING", "OPENAI_API_KEY is not configured");
    if (!model) throw new OpenAIProviderError("OPENAI_MODEL_MISSING", "SEMANTIC_ANALYSIS_MODEL is not configured");
    const pkg = input.evidencePackage;
    if (!pkg) throw new OpenAIProviderError("EVIDENCE_PACKAGE_REQUIRED", "A bounded evidence package is required");
    validateEvidencePackage(pkg);
    const content: Array<Record<string, unknown>> = [{ type: "input_text", text: `${instruction}\nAsset metadata: ${JSON.stringify({ filename: pkg.asset.filename, mediaType: pkg.asset.mediaType, fileSize: pkg.asset.fileSize, durationMs: pkg.durationMs, modalities: input.modalities })}\nEvidence manifest: ${JSON.stringify(pkg.items.map(({ id, kind, timestampMs, endTimestampMs, text, source }) => ({ id, kind, timestampMs, endTimestampMs, text, source })))}\nLocked spec: ${input.specVersion} / ${input.specFingerprint}` }];
    for (const item of pkg.items) if (item.kind === "frame" && item.dataUrl) content.push({ type: "input_image", image_url: item.dataUrl, detail: "high" });
    const started = new Date();
    let response: Response;
    try {
      response = await this.fetchImpl("https://api.openai.com/v1/responses", { method: "POST", headers: { authorization: `Bearer ${key}`, "content-type": "application/json" }, body: JSON.stringify({ model, input: [{ role: "user", content }], text: { format: { type: "json_schema", name: "kdi_semantic_result_v1", strict: true, schema: SEMANTIC_RESULT_SCHEMA } } }) });
    } catch (error) { throw new OpenAIProviderError("OPENAI_NETWORK_ERROR", error instanceof Error ? error.message : "OpenAI request failed", true); }
    const completed = new Date();
    const requestId = response.headers.get("x-request-id");
    if (!response.ok) { const retryable = response.status === 408 || response.status === 429 || response.status >= 500; throw new OpenAIProviderError(retryable ? "OPENAI_RETRYABLE_ERROR" : "OPENAI_REQUEST_ERROR", `OpenAI request failed with HTTP ${response.status}`, retryable); }
    const raw: any = await response.json();
    const text = raw.output_text ?? raw.output?.flatMap((item: any) => item.content ?? []).find((item: any) => item.type === "output_text")?.text;
    if (typeof text !== "string") throw new OpenAIProviderError("STRUCTURED_OUTPUT_MISSING", "OpenAI response did not contain structured output");
    let result: StructuredSemanticResult;
    try { result = JSON.parse(text) as StructuredSemanticResult; } catch { throw new OpenAIProviderError("STRUCTURED_OUTPUT_INVALID", "OpenAI structured output was not valid JSON"); }
    validateResult(result, pkg);
    const usage = raw.usage ?? {};
    this.lastUsage = { requestId, model, startedAt: started.toISOString(), completedAt: completed.toISOString(), durationMs: completed.getTime() - started.getTime(), inputTokens: Number.isFinite(usage.input_tokens) ? usage.input_tokens : null, outputTokens: Number.isFinite(usage.output_tokens) ? usage.output_tokens : null, totalTokens: Number.isFinite(usage.total_tokens) ? usage.total_tokens : null, estimatedCost: null, retries: 0 };
    return result;
  }
}
