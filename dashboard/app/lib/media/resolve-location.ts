import "server-only";

import { isUuid } from "../../lib";

// The permanent architecture: an asset's canonical, deliverable Drive file
// always comes from its verified `asset_destinations` row (the copy living
// in the KDI Master Shared Drive), never from a source folder, a cached
// Google URL, or a manually issued token. This module resolves that single
// fact and nothing else - callers (thumbnail/preview/download routes) are
// responsible for permission checks before calling in, and for talking to
// Drive after calling out.
export type MediaSelectionReason =
  | "destination"
  | "source_fallback"
  | "not_found"
  | "inactive_asset"
  | "no_destination"
  | "no_verified_destination_or_fallback";

export type ResolvedMediaLocation = {
  assetId: string;
  driveFileId: string;
  filename: string;
  mime: string;
  extension: string;
  sizeBytes: number;
  /** Cache/versioning identity - changes whenever the destination record is replaced or re-verified. */
  versionTag: string;
  source: "destination" | "source_fallback";
};

type Json = Record<string, unknown>;

const INACTIVE_ASSET_STATUSES = new Set(["FAILED", "MISSING"]);

function text(value: unknown): string {
  return value == null ? "" : String(value);
}
function num(value: unknown): number {
  return value == null ? 0 : Number(value) || 0;
}
function array(value: unknown): Json[] {
  if (Array.isArray(value)) return value as Json[];
  return value && typeof value === "object" ? [value as Json] : [];
}

export function isAssetActive(uploadStatus: unknown): boolean {
  return !INACTIVE_ASSET_STATUSES.has(text(uploadStatus));
}

/**
 * Shape expected from Supabase. `asset_destinations` and `source_files` are
 * PostgREST embeds - both call sites (authenticated production reads via
 * `liveRest`, and the service-role development bypass) already select
 * exactly this shape, so no schema changes are required.
 */
export type ResolvableAssetRow = {
  id: unknown;
  file_name: unknown;
  mime_type: unknown;
  file_extension: unknown;
  size_bytes: unknown;
  upload_status: unknown;
  asset_destinations?: unknown;
  /** Only present/considered when `allowSourceFallback` is true. */
  source_files?: { google_file_id: unknown; file_name: unknown; mime_type: unknown; file_extension: unknown; size_bytes: unknown; trashed: unknown; is_missing: unknown }[];
};

export type ResolveOptions = {
  /**
   * The live application never falls back to an original source file today
   * (`canPreview`/`canDownload` are strictly `Boolean(verifiedDestination)`).
   * This flag exists so a future, explicit product decision can opt in
   * without re-deriving the resolution logic - it defaults to off so no
   * "random historical source" is ever silently served.
   */
  allowSourceFallback?: boolean;
};

export function resolveFromAssetRow(row: ResolvableAssetRow, options: ResolveOptions = {}): { location: ResolvedMediaLocation | null; reason: MediaSelectionReason } {
  const assetId = text(row.id);
  if (!isAssetActive(row.upload_status)) return { location: null, reason: "inactive_asset" };

  const destinations = array(row.asset_destinations);
  const verified = destinations.find((d) => text(d.upload_status) === "VERIFIED" && text(d.destination_google_file_id));
  if (verified) {
    const versionTag = text(verified.verified_at) || text(verified.upload_completed_at) || text(verified.id) || "unversioned";
    return {
      reason: "destination",
      location: {
        assetId,
        driveFileId: text(verified.destination_google_file_id),
        filename: text(verified.destination_filename) || text(row.file_name) || "download",
        mime: text(row.mime_type) || "application/octet-stream",
        extension: text(row.file_extension),
        sizeBytes: num(row.size_bytes),
        versionTag,
        source: "destination",
      },
    };
  }

  if (options.allowSourceFallback && row.source_files?.length) {
    const candidate = row.source_files.find((file) => !file.trashed && !file.is_missing && text(file.google_file_id));
    if (candidate) {
      return {
        reason: "source_fallback",
        location: {
          assetId,
          driveFileId: text(candidate.google_file_id),
          filename: text(candidate.file_name) || text(row.file_name) || "download",
          mime: text(candidate.mime_type) || text(row.mime_type) || "application/octet-stream",
          extension: text(candidate.file_extension) || text(row.file_extension),
          sizeBytes: num(candidate.size_bytes) || num(row.size_bytes),
          versionTag: "source",
          source: "source_fallback",
        },
      };
    }
  }

  return { location: null, reason: destinations.length ? "no_verified_destination_or_fallback" : "no_destination" };
}

export type MediaOperation = "thumbnail" | "preview" | "download";

// Sanitized, structured logging only: asset id (not patient/clinical data)
// and the enumerated reason. Never the Drive file id's neighboring metadata,
// filenames, or anything from asset_semantic_index.
export function logMediaSelection(operation: MediaOperation, assetId: string, reason: MediaSelectionReason) {
  console.log(JSON.stringify({ scope: "media_resolution", operation, assetId, selection: reason }));
}

export async function resolveAssetMediaLocation(
  assetId: string,
  operation: MediaOperation,
  fetchRow: (id: string) => Promise<ResolvableAssetRow | null>,
  options: ResolveOptions = {},
): Promise<ResolvedMediaLocation | null> {
  if (!isUuid(assetId)) return null;
  const row = await fetchRow(assetId);
  if (!row) {
    logMediaSelection(operation, assetId, "not_found");
    return null;
  }
  const { location, reason } = resolveFromAssetRow(row, options);
  logMediaSelection(operation, assetId, reason);
  return location;
}
