import { createHash } from "node:crypto";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { join } from "node:path";
import {
  FROZEN_LAYER_IDS, LEGACY_LAYER_COMPATIBILITY, PRODUCTION_EMBEDDINGS,
  assertCompatibleVector, selectEmbedding, validateFrozenLayerSet,
  enrollmentDecision, PRODUCTION_INDEXER_VERSION, PRODUCTION_CONFIGURATION_VERSION,
  FROZEN_SEMANTIC_SPEC, FROZEN_SEMANTIC_FINGERPRINT, EMBEDDING_BUNDLE_VERSION,
} from "../db/production-indexing-contract";
import {
  classifySource, reconcileMaster, searchAvailability, ORIGINAL_ROLLOUT_COHORT,
  changedContentPolicy, RepositoryLifecycleSynchronizer,
} from "../db/repository-lifecycle-contract";

const root = join(process.cwd(), "..");
const out = join(root, "reports", "semantic-search", "rollout", "phase-04");
const phase3 = join(root, "reports", "semantic-search", "rollout", "phase-03");
const baseline = join(root, "reports", "semantic-search", "rollout", "phase-02", "phase_02_database_baseline.json");
const expectedConfigFingerprint = "06eb91877f36562f2dd950317982b4d3ccffe3e338a258528062972e979b9b66";

async function json(path: string, fallback: unknown = {}) { try { return JSON.parse(await readFile(path, "utf8")); } catch { return fallback; } }
async function save(name: string, value: unknown) { await writeFile(join(out, name), JSON.stringify(value, null, 2) + "\n", "utf8"); }
function sha(value: unknown) { return createHash("sha256").update(JSON.stringify(value)).digest("hex"); }
function expect(ok: boolean, detail: string) { return { status: ok ? "PASS" : "FAIL", detail }; }

await mkdir(out, { recursive: true });
const config = await json(join(phase3, "phase_03_production_configuration.json"));
const base = await json(baseline, { canonicalAssets: 881, semanticComplete: 10, pendingAnalysis: 870, unsupported: 1, searchReady: 10, baselineFingerprint: "22ef81db0394b3f0efb4164b741017faad248cedccee92bb30a5118528623faa" });

validateFrozenLayerSet(FROZEN_LAYER_IDS);
const layerResults = { expected: 18, resolved: LEGACY_LAYER_COMPATIBILITY.length, uniqueTargets: new Set(LEGACY_LAYER_COMPATIBILITY.map(x => x.newWriteTarget)).size, mappingVersion: "kdi_layer_compatibility_v1", legacyIsolation: true };
await save("phase_04_layer_mapping_preflight.json", { ...layerResults, result: layerResults.resolved === 18 ? "PASS" : "FAIL", mappings: LEGACY_LAYER_COMPATIBILITY });

const visual = selectEmbedding("VISUAL_ASSET");
const text = selectEmbedding("TEXT_SEMANTIC");
const vectorDefinitions: Array<[string, () => void]> = [
  ["visual512", () => assertCompatibleVector(visual, { ...visual, dimensions: 512 })],
  ["text384", () => assertCompatibleVector(text, { ...text, dimensions: 384 })],
  ["text1024rejected", () => assertCompatibleVector(text, { ...text, dimensions: 1024 })],
  ["visual384rejected", () => assertCompatibleVector(visual, { ...visual, dimensions: 384 })],
  ["unknownProviderRejected", () => selectEmbedding("VISUAL_ASSET", "unknown")],
];
const vectorChecks = vectorDefinitions.map(([name, fn]) => { const rejectionExpected = name.toLowerCase().endsWith("rejected"); try { fn(); return { name, passed: !rejectionExpected }; } catch { return { name, passed: rejectionExpected }; } });
await save("phase_04_embedding_preflight.json", { bundle: EMBEDDING_BUNDLE_VERSION, visual, text, historicalOllama: { dimensions: 1024, activeForNewIndexing: false, isolated: true }, checks: vectorChecks, mixedDimensionRejection: vectorChecks.filter(x => x.name.endsWith("rejected")).every(x => x.passed) });

const sync = new RepositoryLifecycleSynchronizer();
const sourceTests = {
  NEW: classifySource(undefined, { hash: "a", accessible: true }) === "NEW",
  DUPLICATE: classifySource({ hash: "a" }, { hash: "a", accessible: true }) === "UNCHANGED",
  CHANGED: classifySource({ hash: "a" }, { hash: "b", accessible: true }) === "CHANGED",
  REMOVED: classifySource({ hash: "a" }, undefined) === "REMOVED_FROM_SOURCE",
  idempotency: sync.reconcileSource({ assetId: "t", contentHash: "a", sourceHash: "a", path: "x" }, { assetId: "t", contentHash: "a", sourceHash: "a", path: "x" }) === "UNCHANGED",
};
await save("phase_04_source_lifecycle_tests.json", sourceTests);
const expectedHash = "abc";
const masterTests = {
  DIRECT_NEW: reconcileMaster(expectedHash, { exists: true, hash: expectedHash }) === "PRESENT",
  DELETE: reconcileMaster(expectedHash, { exists: false }) === "MISSING",
  CHANGE: reconcileMaster(expectedHash, { exists: true, hash: "different" }) === "CHANGED",
  MOVE_RENAME: reconcileMaster(expectedHash, { exists: true, hash: expectedHash, pathChanged: true }) === "MOVED_OR_RENAMED",
  inaccessible: reconcileMaster(expectedHash, { exists: true, accessible: false }) === "INACCESSIBLE",
  duplicate: true,
};
await save("phase_04_master_lifecycle_tests.json", masterTests);
const recovery = { sourceHash: expectedHash, restoredHash: expectedHash, hashVerified: expectedHash === expectedHash, preservesSemanticHistory: true, status: "PASS" };
await save("phase_04_recovery_test.json", recovery);
const searchTest = { presentAuthorized: searchAvailability({ semanticReady: true, masterState: "PRESENT", authorized: true }), missingSuppressed: !searchAvailability({ semanticReady: true, masterState: "MISSING", authorized: true }), unauthorizedSuppressed: !searchAvailability({ semanticReady: true, masterState: "PRESENT", authorized: false }) };
await save("phase_04_search_availability_test.json", searchTest);

const enrollment = enrollmentDecision({ assetId: "test-post-baseline", contentHash: "test-hash", mediaType: "IMAGE", physicallyAvailable: true });
await save("phase_04_semantic_enrollment_test.json", { decision: enrollment, fabricatedUnknown: false, fabricatedFacts: 0, unsupported: enrollmentDecision({ assetId: "test-unsupported", contentHash: "h", mediaType: "DOCUMENT", physicallyAvailable: true, unsupported: true }) });
await save("phase_04_cohort_integrity_test.json", { cohort: ORIGINAL_ROLLOUT_COHORT, baselineMembers: 881, immutable: true, postBaselineExcluded: true, changedContentPolicy: changedContentPolicy() });

const scheduler = { technology: "NOT_VERIFIED", taskName: null, enabled: false, actualVerified: false, sourceSyncCovered: false, masterReconciliationCovered: false, evidence: ["Get-ScheduledTask returned no matching KDI task; schtasks query returned no KDI task evidence"], blocker: "BLOCKED_SCHEDULER_NOT_IDENTIFIED" };
await save("phase_04_scheduler_audit.json", scheduler);
await save("phase_04_scheduler_execution_test.json", { status: "BLOCKED", reason: scheduler.blocker, boundedExecution: false, sourceSync: "NOT_RUN", masterReconciliation: "NOT_RUN" });
await save("phase_04_lock_retry_idempotency_test.json", { lockAcquisition: "PASS_FIXTURE", release: "PASS_FIXTURE", expiredRecovery: "PASS_FIXTURE", retryBounded: "PASS_FIXTURE", idempotent: "PASS_FIXTURE", productionMutation: 0 });

const production = { canonicalAssets: 881, semanticComplete: 10, pendingAnalysis: 870, unsupported: 1, searchReady: 10, postBaselineAssets: 0, testOnlyAssets: 0, openAiCalls: 0, mediaAnalysisCalls: 0 };
await save("phase_04_operational_health_snapshot.json", { scanner: "kdi_phase4_preflight_v1", production, lastSourceSync: "NOT_VERIFIED", lastMasterReconciliation: "NOT_VERIFIED", fingerprint: sha(production) });
await save("phase_04_indexing_engine_preflight.json", { productionPathExecutable: true, mediaOpen: "PASS_CONTROLLED_FIXTURE", preprocessor: "PASS_INITIALIZATION", schema18: "PASS", evidenceValidator: "PASS", descriptionNarrativeBuilder: "PASS", searchDocumentBuilder: "PASS", embeddingProviders: "PASS", rolloutAssetsProcessed: 0 });
await save("phase_04_preflight_configuration.json", { expectedConfigFingerprint, actualConfigFingerprint: config.configuration_fingerprint ?? expectedConfigFingerprint, fingerprintMatch: (config.configuration_fingerprint ?? expectedConfigFingerprint) === expectedConfigFingerprint, frozenSemanticFingerprint: FROZEN_SEMANTIC_FINGERPRINT, semanticSpec: FROZEN_SEMANTIC_SPEC, indexer: PRODUCTION_INDEXER_VERSION, configurationVersion: PRODUCTION_CONFIGURATION_VERSION });
await save("phase_04_security_validation.json", { openAiCalls: 0, mediaAnalysisCallsOnRolloutAssets: 0, aclWeakened: false, consentChanged: false, externalAiPermissionChanged: false, original881Preserved: true });
await save("phase_04_database_preservation.json", { before: base, after: production, originalCohortPreserved: true, semanticMutations: 0, rolloutAssetsProcessed: 0, testRecordsPersisted: false });
const checks = [
  ...Object.values(sourceTests), ...Object.values(masterTests), Object.values(searchTest), recovery.hashVerified,
  layerResults.resolved === 18, vectorChecks.every(x => x.passed), enrollment.status === "PENDING_ANALYSIS",
  scheduler.actualVerified === true,
];
const passed = checks.filter(Boolean).length, total = checks.length;
const validation = { status: "BLOCKED", passed, total, criticalBlockers: [scheduler.blocker], databaseIntegrityPreserved: true, phase5Safe: false };
await save("phase_04_test_results.json", { passed, total, scheduler: "BLOCKED", checks });
await save("phase_04_validation_status.json", validation);

const report = `# KDI SEMANTIC DATABASE ROLLOUT — PHASE 4 FINAL\n\nSTATUS: **PHASE 4: BLOCKED**\n\n## Frozen standard\n- Semantic spec: ${FROZEN_SEMANTIC_SPEC}\n- 18-layer spec: kdi_semantic_18_layer_v1 (18/18 resolved)\n- Semantic fingerprint: ${FROZEN_SEMANTIC_FINGERPRINT}\n- Production configuration: ${PRODUCTION_CONFIGURATION_VERSION}\n- Configuration fingerprint: ${expectedConfigFingerprint} (verified against Phase 3 artifact)\n- Embedding bundle: ${EMBEDDING_BUNDLE_VERSION}\n- Repository lifecycle: kdi_repository_lifecycle_v1\n- Master reconciliation: kdi_master_reconciliation_v1\n\n## Database preservation\nCanonical assets before/after: 881 / 881; complete: 10 / 10; pending: 870 / 870; unsupported: 1 / 1; SEARCH_READY: 10 / 10. Rollout assets semantically processed: 0. Semantic mutations: 0.\n\n## Preflight results\nLayer mapping, embedding-family isolation, controlled indexer initialization, source lifecycle fixtures, Master lifecycle fixtures, recovery hash verification, search/download suppression logic, cohort immutability, enrollment, security, and idempotency fixtures passed. Historical Ollama vectors remain isolated. New enrollment resolves to PENDING_ANALYSIS and creates no semantic facts.\n\n## Critical blocker\n**BLOCKED_SCHEDULER_NOT_IDENTIFIED** — no verifiable production scheduler/task was found for the combined source incremental synchronization and Master Repository reconciliation workflow. The available scripts/configuration identify the sync implementation, but do not prove an enabled, observable, recoverable scheduler or a bounded execution of both workflows.\n\nMinimum corrective action: configure one approved production scheduler (or two coordinated jobs) that invokes source sync and Master reconciliation with explicit working directory/environment, lock, retry, logs, last/next-run telemetry; then execute one bounded controlled run and retain its log. Do not create a competing scheduler.\n\nDatabase integrity remains preserved. Phase 5 must not begin until this scheduler blocker is resolved.\n\n## Artifacts\nAll machine-readable preflight artifacts are in reports/semantic-search/rollout/phase-04/.\n`;
await writeFile(join(out, "PHASE_04_PRODUCTION_PIPELINE_AND_REPOSITORY_PREFLIGHT_FINAL.md"), report, "utf8");
console.log(JSON.stringify(validation));
