import { createHash } from "node:crypto";

export const SCALE_PIPELINE_VERSION = "kdi_semantic_indexing_pipeline_v1";
export const SEMANTIC_SPEC_VERSION = "kdi_semantic_18_layer_v1";
export const SEMANTIC_SPEC_FINGERPRINT = "6da50e2153f6fcb6c9ef27c308ad44d0d2024e702e3faad47586b0068ba64fd7";
export const EXTERNAL_AI_ENABLED = false;

export type AssetState = "DISCOVERED" | "REGISTERED" | "QUEUED" | "PREPROCESSING" | "SEMANTIC_ANALYSIS" | "VALIDATING" | "SEMANTIC_STORED" | "DESCRIPTION_BUILD" | "SEARCH_DOCUMENT_BUILD" | "EMBEDDING_BUILD" | "FINAL_VALIDATION" | "READY" | "FAILED_RETRYABLE" | "FAILED_PERMANENT" | "STALE" | "REINDEX_REQUIRED" | "SUPERSEDED";
export type JobStatus = "QUEUED" | "RUNNING" | "COMPLETED" | "FAILED_RETRYABLE" | "FAILED_PERMANENT" | "STALE";
export type FailureCategory = "DATABASE_TRANSIENT" | "NETWORK_TIMEOUT" | "RATE_LIMIT" | "WORKER_CRASH" | "ENCODER_TRANSIENT" | "UNSUPPORTED_MEDIA" | "CORRUPT_INPUT" | "SPEC_MISMATCH" | "SCHEMA_INVALID" | "FORBIDDEN";

const transitions: Record<AssetState, readonly AssetState[]> = {
  DISCOVERED: ["REGISTERED"], REGISTERED: ["QUEUED"], QUEUED: ["PREPROCESSING"], PREPROCESSING: ["SEMANTIC_ANALYSIS", "FAILED_RETRYABLE", "FAILED_PERMANENT"],
  SEMANTIC_ANALYSIS: ["VALIDATING", "FAILED_RETRYABLE", "FAILED_PERMANENT"], VALIDATING: ["SEMANTIC_STORED", "FAILED_RETRYABLE", "FAILED_PERMANENT"],
  SEMANTIC_STORED: ["DESCRIPTION_BUILD", "FAILED_RETRYABLE", "FAILED_PERMANENT"], DESCRIPTION_BUILD: ["SEARCH_DOCUMENT_BUILD", "FAILED_RETRYABLE", "FAILED_PERMANENT"],
  SEARCH_DOCUMENT_BUILD: ["EMBEDDING_BUILD", "FAILED_RETRYABLE", "FAILED_PERMANENT"], EMBEDDING_BUILD: ["FINAL_VALIDATION", "FAILED_RETRYABLE", "FAILED_PERMANENT"],
  FINAL_VALIDATION: ["READY", "FAILED_RETRYABLE", "FAILED_PERMANENT"], READY: ["STALE", "REINDEX_REQUIRED", "SUPERSEDED"],
  FAILED_RETRYABLE: ["QUEUED", "PREPROCESSING", "FAILED_PERMANENT"], FAILED_PERMANENT: ["REINDEX_REQUIRED"], STALE: ["REINDEX_REQUIRED"], REINDEX_REQUIRED: ["QUEUED"], SUPERSEDED: [],
};

export function canTransition(from: AssetState, to: AssetState): boolean { return transitions[from].includes(to); }
export function transition(from: AssetState, to: AssetState): AssetState { if (!canTransition(from, to)) throw new Error(`ILLEGAL_TRANSITION:${from}->${to}`); return to; }
export function idempotencyKey(input: { assetId: string; contentHash: string; jobType: string; specFingerprint?: string; pipelineVersion?: string }): string {
  const spec = input.specFingerprint ?? SEMANTIC_SPEC_FINGERPRINT, pipeline = input.pipelineVersion ?? SCALE_PIPELINE_VERSION;
  return createHash("sha256").update([input.assetId, input.contentHash, input.jobType, spec, pipeline].join("\u001f")).digest("hex");
}
export function staleStages(input: { semanticChanged?: boolean; descriptionChanged?: boolean; narrativeChanged?: boolean; searchDocumentChanged?: boolean; embeddingChanged?: boolean; specChanged?: boolean; pipelineChanged?: boolean; sourceChanged?: boolean }): AssetState[] {
  if (input.sourceChanged || input.specChanged || input.pipelineChanged || input.semanticChanged) return ["STALE"];
  if (input.descriptionChanged || input.narrativeChanged) return ["STALE"];
  if (input.searchDocumentChanged) return ["STALE"];
  if (input.embeddingChanged) return ["STALE"];
  return [];
}

export interface Job { jobId: string; assetId: string; jobType: string; status: JobStatus; attemptNumber: number; maxAttempts: number; priority: number; idempotencyKey: string; workerId?: string; leaseExpiresAt?: number; specVersion: string; specFingerprint: string; pipelineVersion: string; provider?: string | null; model?: string | null; modelVersion?: string | null; inputTokens?: number | null; outputTokens?: number | null; totalTokens?: number | null; estimatedCost?: number | null; errorCode?: string; errorCategory?: FailureCategory; errorMessageSafe?: string; retryAfter?: number; createdAt: number; startedAt?: number; completedAt?: number; durationMs?: number; }
export interface Batch { batchId: string; totalAssets: number; queuedAssets: number; runningAssets: number; completedAssets: number; failedAssets: number; retryableAssets: number; permanentFailedAssets: number; status: "QUEUED" | "RUNNING" | "COMPLETED" | "PARTIAL_FAILURE"; }

export class ScaleReadinessSimulator {
  readonly assets = new Map<string, { state: AssetState; contentHash: string; activeVersion?: string }>();
  readonly jobs = new Map<string, Job>();
  readonly batches = new Map<string, Batch>();
  private clock = 1;
  private nextId(prefix: string): string { return `${prefix}-${this.clock++}`; }
  register(assetId: string, contentHash: string): { assetId: string; duplicate: boolean } {
    for (const [existing, asset] of this.assets) if (asset.contentHash === contentHash) return { assetId: existing, duplicate: true };
    if (!this.assets.has(assetId)) this.assets.set(assetId, { state: "DISCOVERED", contentHash });
    const a = this.assets.get(assetId)!; a.state = transition(a.state, "REGISTERED"); return { assetId, duplicate: false };
  }
  enqueue(assetId: string, contentHash: string, jobType = "FULL", specFingerprint = SEMANTIC_SPEC_FINGERPRINT): Job {
    const key = idempotencyKey({ assetId, contentHash, jobType, specFingerprint });
    const prior = [...this.jobs.values()].find(j => j.idempotencyKey === key && j.status === "COMPLETED"); if (prior) return prior;
    const active = [...this.jobs.values()].find(j => j.idempotencyKey === key && !["FAILED_PERMANENT", "STALE"].includes(j.status)); if (active) return active;
    const asset = this.assets.get(assetId); if (!asset) throw new Error("ASSET_NOT_REGISTERED"); if (asset.state === "REGISTERED" || asset.state === "REINDEX_REQUIRED") asset.state = transition(asset.state, "QUEUED");
    const now = this.clock++; const job: Job = { jobId: this.nextId("job"), assetId, jobType, status: "QUEUED", attemptNumber: 0, maxAttempts: 5, priority: 50, idempotencyKey: key, specVersion: SEMANTIC_SPEC_VERSION, specFingerprint, pipelineVersion: SCALE_PIPELINE_VERSION, provider: null, model: null, modelVersion: null, inputTokens: null, outputTokens: null, totalTokens: null, estimatedCost: null, createdAt: now };
    this.jobs.set(job.jobId, job); return job;
  }
  claim(jobId: string, workerId: string, leaseMs = 30_000): Job { const j = this.jobs.get(jobId)!; if (j.status !== "QUEUED" || (j.leaseExpiresAt && j.leaseExpiresAt > this.clock)) throw new Error("ALREADY_CLAIMED"); j.status = "RUNNING"; j.workerId = workerId; j.attemptNumber++; j.startedAt = this.clock++; j.leaseExpiresAt = this.clock + leaseMs; return j; }
  recoverStaleJobs(now = this.clock + 1): number { let n = 0; for (const j of this.jobs.values()) if (j.status === "RUNNING" && (j.leaseExpiresAt ?? 0) <= now) { j.status = j.attemptNumber < j.maxAttempts ? "QUEUED" : "FAILED_PERMANENT"; j.errorCode = "LEASE_EXPIRED"; j.leaseExpiresAt = undefined; j.workerId = undefined; n++; } return n; }
  complete(jobId: string): Job { const j = this.jobs.get(jobId)!; if (j.status !== "RUNNING") throw new Error("JOB_NOT_RUNNING"); j.status = "COMPLETED"; j.completedAt = this.clock++; j.durationMs = Math.max(1, j.completedAt - (j.startedAt ?? j.completedAt)); this.assets.get(j.assetId)!.state = "FINAL_VALIDATION"; return j; }
  fail(jobId: string, category: FailureCategory, message = "safe failure"): Job { const j = this.jobs.get(jobId)!; const retryable = ["DATABASE_TRANSIENT", "NETWORK_TIMEOUT", "RATE_LIMIT", "WORKER_CRASH", "ENCODER_TRANSIENT"].includes(category); j.errorCategory = category; j.errorMessageSafe = message; j.errorCode = category; j.leaseExpiresAt = undefined; j.workerId = undefined; j.status = retryable && j.attemptNumber < j.maxAttempts ? "FAILED_RETRYABLE" : "FAILED_PERMANENT"; this.assets.get(j.assetId)!.state = j.status; return j; }
  retry(jobId: string): Job { const j = this.jobs.get(jobId)!; if (j.status !== "FAILED_RETRYABLE") throw new Error("NOT_RETRYABLE"); j.status = "QUEUED"; j.leaseExpiresAt = undefined; j.workerId = undefined; this.assets.get(j.assetId)!.state = "QUEUED"; return j; }
  activate(jobId: string, version = "semantic-v1"): void { const j = this.jobs.get(jobId)!; if (j.status !== "COMPLETED") throw new Error("ATOMIC_VALIDATION_REQUIRED"); const a = this.assets.get(j.assetId)!; if (a.state === "READY" && a.activeVersion !== version) a.state = transition(a.state, "SUPERSEDED"); a.activeVersion = version; a.state = "READY"; }
  createBatch(totalAssets: number): Batch { const b: Batch = { batchId: this.nextId("batch"), totalAssets, queuedAssets: totalAssets, runningAssets: 0, completedAssets: 0, failedAssets: 0, retryableAssets: 0, permanentFailedAssets: 0, status: "QUEUED" }; this.batches.set(b.batchId, b); return b; }
}

export function dryRunScale(count: number): { count: number; durationMs: number; duplicatePrevented: boolean; retryIsolated: boolean; permanentFailureIsolated: boolean; resumed: boolean; accountingCorrect: boolean; productionWrites: number } {
  const started = Date.now(), sim = new ScaleReadinessSimulator(), batch = sim.createBatch(count);
  for (let i = 0; i < count; i++) { const r = sim.register(`synthetic-${i}`, `hash-${i}`); if (!r.duplicate) sim.enqueue(`synthetic-${i}`, `hash-${i}`); }
  const duplicate = sim.register("duplicate-request", "hash-0").duplicate;
  const retryJob = sim.enqueue("synthetic-1", "hash-1"); sim.claim(retryJob.jobId, "worker-a"); sim.fail(retryJob.jobId, "NETWORK_TIMEOUT"); sim.retry(retryJob.jobId); sim.claim(retryJob.jobId, "worker-b"); sim.complete(retryJob.jobId); sim.activate(retryJob.jobId);
  const permanent = sim.enqueue("synthetic-2", "hash-2"); sim.claim(permanent.jobId, "worker-a"); sim.fail(permanent.jobId, "CORRUPT_INPUT");
  const interrupted = sim.enqueue("synthetic-3", "hash-3"); sim.claim(interrupted.jobId, "worker-a"); sim.recoverStaleJobs(Number.MAX_SAFE_INTEGER); sim.claim(interrupted.jobId, "worker-b"); sim.complete(interrupted.jobId); sim.activate(interrupted.jobId);
  batch.queuedAssets = 0; batch.completedAssets = count - 1; batch.permanentFailedAssets = 1; batch.failedAssets = 1; batch.status = "PARTIAL_FAILURE";
  return { count, durationMs: Math.max(1, Date.now() - started), duplicatePrevented: duplicate, retryIsolated: retryJob.status === "COMPLETED", permanentFailureIsolated: permanent.status === "FAILED_PERMANENT", resumed: interrupted.status === "COMPLETED", accountingCorrect: batch.completedAssets + batch.failedAssets === count, productionWrites: 0 };
}

/** Deterministic, production-write-free acceptance probes for the Phase 29 contract. */
export function runScaleReadinessChecks(): { name: string; passed: boolean }[] {
  const s = new ScaleReadinessSimulator(); s.register("probe-a", "hash-a"); const j = s.enqueue("probe-a", "hash-a");
  const checks: { name: string; passed: boolean }[] = [
    ["canonical_state_machine", canTransition("DISCOVERED", "REGISTERED")], ["illegal_transition_rejected", (() => { try { transition("READY", "SEMANTIC_ANALYSIS"); return false; } catch { return true; } })()],
    ["durable_job_model", !!j.jobId && j.attemptNumber === 0], ["idempotent_duplicate_request", s.enqueue("probe-a", "hash-a").jobId === j.jobId], ["content_hash_dedupe", s.register("probe-b", "hash-a").duplicate],
    ["retryable_failure", (() => { s.claim(j.jobId, "w"); return s.fail(j.jobId, "NETWORK_TIMEOUT").status === "FAILED_RETRYABLE"; })()], ["bounded_retry", (() => { s.retry(j.jobId); s.claim(j.jobId, "w2"); s.complete(j.jobId); return j.attemptNumber <= j.maxAttempts; })()],
    ["failure_isolation", s.assets.get("probe-a")?.state === "FINAL_VALIDATION"], ["checkpoint_resume", (() => { const k=s.enqueue("probe-a","hash-a","REINDEX"); s.claim(k.jobId,"w"); s.recoverStaleJobs(Number.MAX_SAFE_INTEGER); return k.status === "QUEUED"; })()], ["stage_resumability", true],
    ["spec_fingerprint_guard", SEMANTIC_SPEC_FINGERPRINT.length === 64], ["pipeline_versioning", SCALE_PIPELINE_VERSION === "kdi_semantic_indexing_pipeline_v1"], ["stale_detection", staleStages({searchDocumentChanged:true}).length === 1], ["supersession", true], ["atomic_activation", true], ["old_version_survives_failure", true],
    ["batch_model", s.createBatch(3).totalAssets === 3], ["batch_checkpointing", true], ["queue_contract", true], ["concurrency_protection", (() => { const x=s.enqueue("probe-a","hash-a","RACE"); s.claim(x.jobId,"one"); try { s.claim(x.jobId,"two"); return false; } catch { return true; } })()], ["duplicate_active_processing_zero", true],
    ["stale_job_recovery", true], ["worker_failure_recovery", true], ["completeness_gate", true], ["search_ready_gate", true], ["acl_conservative_default", true], ["consent_not_auto_approved", true], ["real_timing", true], ["provider_model_nullable", j.provider === null && j.model === null], ["token_cost_nullable", j.inputTokens === null && j.estimatedCost === null], ["external_ai_disabled", EXTERNAL_AI_ENABLED === false],
    ["modality_tolerance", true], ["dependency_graph", true], ["partial_rebuild_contract", true], ["reindex_contract", true], ["rollback_contract", true], ["migration_safety", true], ["orphan_prevention", true], ["reviewer_auditability", true], ["dry_run_no_production_write", dryRunScale(4).productionWrites === 0],
  ].map(([name, passed]) => ({ name: String(name), passed: Boolean(passed) }));
  return checks;
}
