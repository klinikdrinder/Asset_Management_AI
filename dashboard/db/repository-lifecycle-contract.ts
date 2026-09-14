import { createHash } from "node:crypto";

export const REPOSITORY_LIFECYCLE_VERSION = "kdi_repository_lifecycle_v1";
export const MASTER_RECONCILIATION_VERSION = "kdi_master_reconciliation_v1";
export type FileChange = "NEW" | "CHANGED" | "UNCHANGED" | "INACCESSIBLE" | "REMOVED_FROM_SOURCE";
export type MasterState = "PRESENT" | "MISSING" | "INACCESSIBLE" | "MOVED_OR_RENAMED" | "CHANGED" | "VERIFICATION_REQUIRED";
export type Cohort = { cohortId: string; baselineFingerprint: string; baselineAssetCount: number; status: "FROZEN"; membershipImmutable: true; postBaselinePolicy: "ENROLL_SEPARATELY" };
export const ORIGINAL_ROLLOUT_COHORT: Cohort = { cohortId: "kdi_semantic_rollout_881_v1", baselineFingerprint: "22ef81db0394b3f0efb4164b741017faad248cedccee92bb30a5118528623faa", baselineAssetCount: 881, status: "FROZEN", membershipImmutable: true, postBaselinePolicy: "ENROLL_SEPARATELY" };

export function classifySource(previous: { hash?: string; accessible?: boolean } | undefined, current: { hash?: string; accessible?: boolean } | undefined): FileChange {
  if (!current) return previous ? "REMOVED_FROM_SOURCE" : "NEW";
  if (current.accessible === false) return "INACCESSIBLE";
  if (!previous) return "NEW";
  if (previous.hash && current.hash && previous.hash === current.hash) return "UNCHANGED";
  return "CHANGED";
}
export function reconcileMaster(expectedHash: string, observed: { exists: boolean; accessible?: boolean; hash?: string; pathChanged?: boolean }): MasterState {
  if (!observed.exists) return "MISSING";
  if (observed.accessible === false) return "INACCESSIBLE";
  if (observed.pathChanged && observed.hash === expectedHash) return "MOVED_OR_RENAMED";
  if (observed.hash && observed.hash !== expectedHash) return "CHANGED";
  return observed.hash ? "PRESENT" : "VERIFICATION_REQUIRED";
}
export function stableIdentity(assetId: string, contentHash: string, providerId?: string): string { return createHash("sha256").update([assetId, contentHash, providerId ?? ""].join("\u001f")).digest("hex"); }
export function isInOriginalCohort(assetId: string, baselineIds: ReadonlySet<string>): boolean { return baselineIds.has(assetId); }
export function searchAvailability(input: { semanticReady: boolean; masterState: MasterState; authorized: boolean }): boolean { return input.semanticReady && input.masterState === "PRESENT" && input.authorized; }
export function changedContentPolicy(): { oldSemantics: "PRESERVE_HISTORY"; newContent: "NEW_IDENTITY_OR_VERSION"; staleOldRepresentations: true } { return { oldSemantics: "PRESERVE_HISTORY", newContent: "NEW_IDENTITY_OR_VERSION", staleOldRepresentations: true }; }

export type RepositoryRecord = { assetId: string; contentHash: string; providerId?: string; path: string; sourceHash?: string; masterHash?: string; masterExists?: boolean; masterAccessible?: boolean; masterPathChanged?: boolean };
export class RepositoryLifecycleSynchronizer {
  reconcileSource(previous: RepositoryRecord | undefined, current: RepositoryRecord | undefined) { return classifySource(previous && { hash: previous.sourceHash ?? previous.contentHash, accessible: true }, current && { hash: current.sourceHash ?? current.contentHash, accessible: true }); }
  reconcileMaster(record: RepositoryRecord) { return reconcileMaster(record.contentHash, { exists: record.masterExists !== false, accessible: record.masterAccessible, hash: record.masterHash, pathChanged: record.masterPathChanged }); }
  shouldQueueSemantic(record: RepositoryRecord, state: "PENDING_ANALYSIS" | "COMPLETE" | "UNSUPPORTED" | "BLOCKED_BEFORE_ANALYSIS") { return state === "PENDING_ANALYSIS" && this.reconcileMaster(record) === "PRESENT"; }
}
