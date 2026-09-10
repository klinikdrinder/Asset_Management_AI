export const MAINTAINER_VERSION = "kdi_semantic_database_maintainer_v1";
export const MAINTAINER_INSTRUCTION_VERSION = "kdi_semantic_database_maintainer_v1";
export type MaintainerMode = "READ_ONLY" | "CONTROLLED_WRITE";
export type FindingCategory = "DATA_QUALITY" | "MISSING_DATA" | "EVIDENCE" | "SEARCH_INDEX" | "EMBEDDING" | "VERSION_DRIFT" | "DATABASE_INTEGRITY" | "AUTHORIZATION" | "CONSENT" | "PERFORMANCE" | "OPERATIONS" | "LEGACY_ARCHITECTURE";
export type Severity = "P0" | "P1" | "P2" | "P3";
export type MaintenanceActionType = "QUEUE_REINDEX" | "REBUILD_SEARCH_DOCUMENT" | "REBUILD_EMBEDDING" | "REVALIDATE_READINESS" | "CLEAR_FALSE_SEARCH_READY" | "MARK_REPRESENTATION_STALE" | "RETRY_FAILED_JOB" | "CREATE_REVIEW_FINDING";
export type MaintainerAsset = { assetId: string; filename?: string; contentHash?: string | null; status: "COMPLETE" | "PENDING_ANALYSIS" | "UNSUPPORTED" | "PARTIAL_LEGACY"; layers?: number; complete?: boolean; searchReady?: boolean; sourceResolvable?: boolean; backlogPresent?: boolean; visualEmbedding?: boolean; semanticStateValues?: string[]; specFingerprint?: string; systemFingerprint?: string; staleSearchDocument?: boolean; staleEmbedding?: boolean; orphan?: boolean; failedJob?: boolean; stuckJob?: boolean };
export type MaintainerDataset = { assets: MaintainerAsset[]; expectedSpecFingerprint: string; expectedSystemFingerprint: string; backlogIds: string[] };
export type MaintenanceFinding = { findingId: string; assetId?: string; category: FindingCategory; severity: Severity; status: "OPEN" | "INFORMATIONAL" | "RESOLVED"; summary: string; details: string; references: string[]; detectedAt: string; detectorVersion: string; recommendedAction: string; automaticRepairAllowed: boolean; repairActionType?: MaintenanceActionType; resolvedAt?: string };
export type DatabaseHealthSnapshot = { totalAssets: number; completeV1: number; pendingAnalysis: number; unsupported: number; searchReady: number; falseSearchReady: number; falseComplete: number; missingHash: number; missingProvenance: number; orphanRecords: number; staleSearchDocuments: number; staleEmbeddings: number; failedJobs: number; stuckJobs: number; duplicateActiveVersions: number; backlogCount: number; backlogDuplicates: number; aclAnomalies: number; consentAnomalies: number; pendingIsHealthy: true; findings: MaintenanceFinding[] };
export type MaintenanceActionRequest = { actionType: MaintenanceActionType; assetId?: string; findingId?: string; requestedBy: string };

export const MAINTENANCE_TOOL_DEFINITIONS = [
  "get_database_health", "get_asset_semantic_health", "list_maintenance_findings", "find_stale_search_documents", "find_stale_embeddings", "find_invalid_lineage", "find_failed_jobs", "find_false_search_ready", "create_maintenance_finding", "queue_asset_for_reindex", "queue_search_document_rebuild", "queue_embedding_rebuild",
] as const;

export const MAINTAINER_INSTRUCTION_CONTRACT = `You are the KDI Semantic Database Maintainer (${MAINTAINER_INSTRUCTION_VERSION}). Use only approved KDI maintenance tools. Treat PENDING_ANALYSIS as healthy waiting state, never UNKNOWN, COMPLETE, or SEARCH_READY. Prefer deterministic database evidence. Never execute arbitrary SQL, modify semantic truth, weaken ACL, approve consent, or claim an action succeeded without backend confirmation.`;

const now = () => new Date().toISOString();
const id = (prefix: string, text: string) => `${prefix}-${text.replace(/[^a-zA-Z0-9]/g, "").slice(0, 24)}`;

export class KDISemanticDatabaseMaintainer {
  readonly mode: MaintainerMode;
  private readonly findings: MaintenanceFinding[] = [];
  constructor(private readonly dataset: MaintainerDataset, mode: MaintainerMode = "READ_ONLY") { this.mode = mode; }

  getDatabaseHealth(): DatabaseHealthSnapshot {
    const assets = this.dataset.assets;
    const pending = assets.filter((a) => a.status === "PENDING_ANALYSIS");
    const complete = assets.filter((a) => a.status === "COMPLETE");
    const unsupported = assets.filter((a) => a.status === "UNSUPPORTED");
    const falseReady = assets.filter((a) => a.searchReady && a.status !== "COMPLETE");
    const falseComplete = assets.filter((a) => a.complete && a.status !== "COMPLETE");
    const missingHash = assets.filter((a) => !a.contentHash).length;
    const missingProvenance = assets.filter((a) => a.sourceResolvable === false).length;
    const orphan = assets.filter((a) => a.orphan).length;
    const staleDocs = assets.filter((a) => a.staleSearchDocument).length;
    const staleEmbeddings = assets.filter((a) => a.staleEmbedding).length;
    const failedJobs = assets.filter((a) => a.failedJob).length;
    const stuckJobs = assets.filter((a) => a.stuckJob).length;
    for (const asset of assets) this.detectAsset(asset);
    return { totalAssets: assets.length, completeV1: complete.length, pendingAnalysis: pending.length, unsupported: unsupported.length, searchReady: assets.filter((a) => a.searchReady).length, falseSearchReady: falseReady.length, falseComplete: falseComplete.length, missingHash, missingProvenance, orphanRecords: orphan, staleSearchDocuments: staleDocs, staleEmbeddings, failedJobs, stuckJobs, duplicateActiveVersions: 0, backlogCount: this.dataset.backlogIds.length, backlogDuplicates: this.dataset.backlogIds.length - new Set(this.dataset.backlogIds).size, aclAnomalies: 0, consentAnomalies: 0, pendingIsHealthy: true, findings: this.listMaintenanceFindings() };
  }

  getAssetSemanticHealth(assetId: string) {
    const asset = this.dataset.assets.find((candidate) => candidate.assetId === assetId);
    if (!asset) throw new Error("ASSET_NOT_FOUND");
    return { assetId: asset.assetId, filename: asset.filename ?? null, processingStatus: asset.status, layers: asset.layers ?? 0, complete: asset.complete ?? asset.status === "COMPLETE", searchReady: asset.searchReady ?? false, contentHashPresent: Boolean(asset.contentHash), provenancePresent: asset.sourceResolvable !== false, backlogPresent: asset.backlogPresent ?? this.dataset.backlogIds.includes(asset.assetId), visualEmbeddingPresent: asset.visualEmbedding ?? false, staleSearchDocument: asset.staleSearchDocument ?? false, staleEmbedding: asset.staleEmbedding ?? false, semanticStates: asset.semanticStateValues ?? [], findings: this.listMaintenanceFindings().filter((finding) => finding.assetId === asset.assetId) };
  }

  listMaintenanceFindings() { return [...this.findings]; }
  findFalseSearchReady() { return this.dataset.assets.filter((asset) => asset.searchReady && asset.status !== "COMPLETE"); }
  findStaleSearchDocuments() { return this.dataset.assets.filter((asset) => asset.staleSearchDocument); }
  findStaleEmbeddings() { return this.dataset.assets.filter((asset) => asset.staleEmbedding); }
  findFailedJobs() { return this.dataset.assets.filter((asset) => asset.failedJob || asset.stuckJob); }

  requestMaintenanceAction(request: MaintenanceActionRequest) {
    if (!request.requestedBy) throw new Error("REQUESTED_BY_REQUIRED");
    if (!MAINTENANCE_TOOL_DEFINITIONS.includes(this.toolFor(request.actionType) as never)) throw new Error("UNAPPROVED_MAINTENANCE_ACTION");
    if (request.actionType === "CLEAR_FALSE_SEARCH_READY" || request.actionType === "QUEUE_REINDEX" || request.actionType === "REBUILD_SEARCH_DOCUMENT" || request.actionType === "REBUILD_EMBEDDING" || request.actionType === "RETRY_FAILED_JOB" || request.actionType === "MARK_REPRESENTATION_STALE") {
      if (this.mode === "READ_ONLY") return { status: "REJECTED_READ_ONLY", actionId: id("action", `${request.actionType}-${request.assetId ?? "database"}`) };
    }
    return { status: "ACCEPTED_FOR_BACKEND_VALIDATION", actionId: id("action", `${request.actionType}-${request.assetId ?? "database"}`) };
  }

  toolDefinitions() { return MAINTENANCE_TOOL_DEFINITIONS.map((name) => ({ name, description: `Controlled KDI ${name.replaceAll("_", " ").toLowerCase()} tool; no arbitrary SQL.` })); }
  auditLogContract() { return { actionId: "", findingId: null, assetId: null, actionType: "", requestedBy: "", provider: null, model: null, previousStateHash: "", newStateHash: "", startedAt: "", completedAt: "", status: "", error: null }; }
  private toolFor(action: MaintenanceActionType) { return action === "QUEUE_REINDEX" ? "queue_asset_for_reindex" : action === "REBUILD_SEARCH_DOCUMENT" ? "queue_search_document_rebuild" : action === "REBUILD_EMBEDDING" ? "queue_embedding_rebuild" : action === "CREATE_REVIEW_FINDING" ? "create_maintenance_finding" : action === "RETRY_FAILED_JOB" ? "queue_asset_for_reindex" : action === "MARK_REPRESENTATION_STALE" ? "create_maintenance_finding" : action === "CLEAR_FALSE_SEARCH_READY" ? "create_maintenance_finding" : "get_database_health"; }
  private detectAsset(asset: MaintainerAsset) {
    if (!asset.contentHash) this.add(asset, "MISSING_DATA", "P1", "Missing content hash", "Canonical asset has no content hash.", "Provide a verified ingestion hash.");
    if (asset.sourceResolvable === false) this.add(asset, "MISSING_DATA", "P1", "Missing provenance", "Canonical asset source cannot be resolved.", "Repair source provenance before analysis.");
    if (asset.searchReady && asset.status !== "COMPLETE") this.add(asset, "SEARCH_INDEX", "P1", "False SEARCH_READY", "Readiness is asserted without current complete semantics.", "Revalidate readiness; no automatic semantic repair.");
    if (asset.complete && asset.status !== "COMPLETE") this.add(asset, "DATA_QUALITY", "P1", "False COMPLETE", "Completeness flag conflicts with operational state.", "Revalidate completeness.");
    if (asset.staleSearchDocument) this.add(asset, "SEARCH_INDEX", "P2", "Stale search document", "Search representation is stale.", "Queue a controlled search-document rebuild.");
    if (asset.staleEmbedding) this.add(asset, "EMBEDDING", "P2", "Stale embedding", "Embedding lineage is stale.", "Queue a controlled embedding rebuild.");
    if (asset.orphan) this.add(asset, "DATABASE_INTEGRITY", "P1", "Orphan semantic record", "Semantic record has no valid parent.", "Create a review finding; do not delete automatically.");
    if (asset.failedJob || asset.stuckJob) this.add(asset, "OPERATIONS", "P2", "Failed or stuck indexing job", "Indexing job requires operational review.", "Inspect retry and lease history.");
    if (asset.specFingerprint && asset.specFingerprint !== this.dataset.expectedSpecFingerprint) this.add(asset, "VERSION_DRIFT", "P1", "Invalid spec fingerprint", "Asset lineage does not match the locked spec.", "Revalidate lineage before processing.");
    if (asset.systemFingerprint && asset.systemFingerprint !== this.dataset.expectedSystemFingerprint) this.add(asset, "VERSION_DRIFT", "P1", "Invalid system fingerprint", "Asset lineage does not match the accepted system.", "Revalidate lineage before processing.");
  }
  private add(asset: MaintainerAsset, category: FindingCategory, severity: Severity, summary: string, details: string, recommendedAction: string) { const findingId=id("finding",`${asset.assetId}-${summary}`); if (this.findings.some((finding) => finding.findingId === findingId)) return; this.findings.push({ findingId, assetId: asset.assetId, category, severity, status: "OPEN", summary, details, references: [`assets:${asset.assetId}`], detectedAt: now(), detectorVersion: MAINTAINER_VERSION, recommendedAction, automaticRepairAllowed: false }); }
}
