import "server-only";
import { AuthenticationRequired, AuthorizationDenied, requireDownloadPermission, requireStaffOrAdmin } from "./auth";
import { isLibraryDevBypassEnabled } from "./lib/library/dev-bypass";
import { liveRest } from "./lib/library/live-transport";
import { DriveApiError, downloadDriveFile, fetchDriveThumbnailLinkBytes, getDriveFileMetadata } from "./lib/google/drive-client";
import { GoogleServiceAccountError } from "./lib/google/service-account";
import { isValidRangeHeader } from "./lib/media/range";
import { resolveAssetMediaLocation, type MediaOperation, type ResolvableAssetRow, type ResolvedMediaLocation } from "./lib/media/resolve-location";
import { readThumbnailCache, writeThumbnailCache } from "./lib/media/thumbnail-cache";
import { extractPosterFrame } from "./lib/media/video-poster";
import { createServiceClient } from "./lib/supabase/service";

// Everything below resolves an asset's canonical Google Drive file id through
// resolveAssetMediaLocation() (asset -> verified asset_destinations row ->
// destination_google_file_id in KDI Master) and then talks to Drive only
// through the server-side service-account client in lib/google. No OAuth
// refresh token, no manually copied access token, and no Drive URL is ever
// returned to the browser.

const DESTINATION_SELECT = "id,destination_google_file_id,destination_filename,upload_status,verified_at,upload_completed_at";
const ASSET_SELECT = `id,file_name,mime_type,file_extension,size_bytes,upload_status,asset_destinations!inner(${DESTINATION_SELECT})`;

async function fetchProductionAssetRow(assetId: string): Promise<ResolvableAssetRow | null> {
  const response = await liveRest(`assets?select=${ASSET_SELECT}&id=eq.${assetId}&asset_destinations.upload_status=eq.VERIFIED&limit=1`);
  const rows = (await response.json()) as ResolvableAssetRow[];
  return rows[0] ?? null;
}

async function fetchDevAssetRow(assetId: string): Promise<ResolvableAssetRow | null> {
  const { data, error } = await createServiceClient().from("assets").select(ASSET_SELECT).eq("id", assetId).eq("asset_destinations.upload_status", "VERIFIED").maybeSingle();
  if (error || !data) return null;
  return data as unknown as ResolvableAssetRow;
}

export async function authorizedMedia(assetId: string, operation: MediaOperation, download = false) {
  const user = download ? await requireDownloadPermission() : await requireStaffOrAdmin();
  const location = await resolveAssetMediaLocation(assetId, operation, fetchProductionAssetRow);
  if (!location) throw new Error("Not found");
  if (download) {
    const { data: allowed, error } = await createServiceClient().rpc("can_user_download_asset_for", {
      p_user_id: user.userId,
      p_asset_id: assetId,
    });
    if (error || allowed !== true) throw new AuthorizationDenied("Access denied");
  }
  return { location, user };
}

async function devAuthorizedMedia(assetId: string, operation: MediaOperation): Promise<ResolvedMediaLocation> {
  if (!isLibraryDevBypassEnabled()) throw new Error("Not found");
  const location = await resolveAssetMediaLocation(assetId, operation, fetchDevAssetRow);
  if (!location) throw new Error("Not found");
  return location;
}

export function safeDownloadName(extension: string, kind = "media") {
  const ext = extension.replace(/[^a-z0-9]/gi, "").toLowerCase().slice(0, 10);
  return `KDI-${kind}${ext ? `.${ext}` : ""}`;
}

function sanitizeRange(range: string | null | undefined, operation: MediaOperation, assetId: string): string | null {
  if (!range) return null;
  if (!isValidRangeHeader(range)) {
    console.warn(JSON.stringify({ scope: "media_error", operation, assetId, failureStage: "invalid_range" }));
    return null;
  }
  return range;
}

export async function fetchDriveMedia(assetId: string, range?: string | null, clientSignal?: AbortSignal, download = false) {
  const operation: MediaOperation = download ? "download" : "preview";
  const { location, user } = await authorizedMedia(assetId, operation, download);
  const upstream = await downloadDriveFile(location.driveFileId, { range: sanitizeRange(range, operation, assetId), clientSignal });
  return { record: location, user, upstream };
}

export async function fetchDevDriveMedia(assetId: string, range?: string | null, clientSignal?: AbortSignal) {
  const location = await devAuthorizedMedia(assetId, "preview");
  const upstream = await downloadDriveFile(location.driveFileId, { range: sanitizeRange(range, "preview", assetId), clientSignal });
  return { record: location, upstream };
}

// ---- Thumbnails -----------------------------------------------------------

const THUMBNAIL_FIELDS = "thumbnailLink,modifiedTime";
const MAX_THUMBNAIL_BYTES = 5_000_000;
const VIDEO_POSTER_PROBE_RANGE = "bytes=0-6291455";

type ThumbnailBytes = { bytes: Buffer; contentType: string };

// Reads the destination file's thumbnailLink from Drive metadata and fetches
// it server-side immediately - the temporary Google URL never leaves this
// function, only the resulting image bytes do.
async function generateDriveThumbnail(location: ResolvedMediaLocation, clientSignal?: AbortSignal): Promise<ThumbnailBytes | null> {
  const metadata = await getDriveFileMetadata(location.driveFileId, THUMBNAIL_FIELDS, clientSignal);
  if (!metadata.thumbnailLink) return null;
  const response = await fetchDriveThumbnailLinkBytes(metadata.thumbnailLink, clientSignal);
  const contentType = (response.headers.get("content-type") || "").toLowerCase();
  if (!contentType.startsWith("image/")) return null;
  const bytes = Buffer.from(await response.arrayBuffer());
  if (!bytes.length || bytes.length > MAX_THUMBNAIL_BYTES) return null;
  return { bytes, contentType };
}

// Fallback for videos Drive did not generate a thumbnail for: pull a small
// leading byte range (not the whole file) and extract one frame with
// ffmpeg. Silently unavailable (never a hard failure) when ffmpeg is not
// installed on the host.
async function generateVideoPosterFallback(location: ResolvedMediaLocation, clientSignal?: AbortSignal): Promise<ThumbnailBytes | null> {
  const upstream = await downloadDriveFile(location.driveFileId, { range: VIDEO_POSTER_PROBE_RANGE, clientSignal, timeoutMs: 30_000 });
  const bytes = Buffer.from(await upstream.arrayBuffer());
  const frame = await extractPosterFrame(bytes);
  return frame ? { bytes: frame, contentType: "image/jpeg" } : null;
}

async function generateThumbnail(location: ResolvedMediaLocation, clientSignal?: AbortSignal): Promise<ThumbnailBytes> {
  let generated: ThumbnailBytes | null = null;
  try { generated = await generateDriveThumbnail(location, clientSignal); }
  catch (error) { if (!location.mime.startsWith("video/")) throw error; }
  if (!generated && location.mime.startsWith("video/")) {
    try { generated = await generateVideoPosterFallback(location, clientSignal); } catch { generated = null; }
  }
  if (!generated) throw new Error("Thumbnail unavailable");
  return generated;
}

function thumbnailEtag(location: ResolvedMediaLocation): string {
  return `"${location.assetId}-${location.driveFileId}-${location.versionTag}"`.replace(/\s+/g, "_");
}

export type ThumbnailResult = { status: 200; bytes: Buffer; contentType: string; etag: string } | { status: 304; etag: string };

async function resolveThumbnailResult(location: ResolvedMediaLocation, ifNoneMatch: string | null | undefined, clientSignal?: AbortSignal): Promise<ThumbnailResult> {
  if (!location.mime.startsWith("image/") && !location.mime.startsWith("video/")) throw new Error("Thumbnail unavailable");
  const etag = thumbnailEtag(location);
  if (ifNoneMatch && ifNoneMatch === etag) return { status: 304, etag };
  const cached = await readThumbnailCache(location.assetId, location.driveFileId, location.versionTag);
  if (cached) return { status: 200, etag, ...cached };
  const generated = await generateThumbnail(location, clientSignal);
  await writeThumbnailCache(location.assetId, location.driveFileId, location.versionTag, generated);
  return { status: 200, etag, ...generated };
}

export async function fetchDriveThumbnail(assetId: string, clientSignal?: AbortSignal, ifNoneMatch?: string | null) {
  const { location } = await authorizedMedia(assetId, "thumbnail");
  return resolveThumbnailResult(location, ifNoneMatch, clientSignal);
}

export async function fetchDevDriveThumbnail(assetId: string, clientSignal?: AbortSignal, ifNoneMatch?: string | null) {
  const location = await devAuthorizedMedia(assetId, "thumbnail");
  return resolveThumbnailResult(location, ifNoneMatch, clientSignal);
}

// ---- Response helpers -------------------------------------------------------

export function thumbnailHeaders(etag: string, contentType: string) {
  return new Headers({ "Cache-Control": "private, max-age=3600, stale-while-revalidate=86400", "Content-Type": contentType, "X-Content-Type-Options": "nosniff", ETag: etag });
}

export function mediaErrorResponse(error: unknown, context: { operation?: MediaOperation; assetId?: string } = {}) {
  const respond = (status: number, message: string) => new Response(message, { status, headers: { "Cache-Control": "private, no-store" } });
  if (error instanceof AuthenticationRequired) return respond(401, "Authentication required");
  if (error instanceof AuthorizationDenied) return respond(403, "Access denied");
  if (error instanceof GoogleServiceAccountError) {
    console.error(JSON.stringify({ scope: "media_error", ...context, failureStage: "credentials", code: error.code }));
    return respond(503, "Media service is temporarily unavailable");
  }
  if (error instanceof DriveApiError) {
    console.error(JSON.stringify({ scope: "media_error", ...context, failureStage: "drive_api", driveStatus: error.status, code: error.code }));
    if (error.code === "drive_not_found") return respond(404, "Media unavailable");
    if (error.code === "drive_rate_limited") return respond(429, "Media temporarily unavailable, please retry");
    if (error.code === "drive_request_timeout") return respond(504, "Media request timed out");
    return respond(502, "Media unavailable");
  }
  console.error(JSON.stringify({ scope: "media_error", ...context, failureStage: "resolution", message: error instanceof Error ? error.message : "unknown" }));
  return respond(404, "Media unavailable");
}

export function mediaHeaders(record: { mime: string; extension: string; filename?: string }, upstream: Response, disposition: "inline" | "attachment") {
  const original = (record.filename || "").replace(/[\r\n"\\]/g, "_").replace(/[^\x20-\x7e]/g, "_").slice(0, 180);
  const fallback = safeDownloadName(record.extension, disposition === "inline" ? "preview" : "download");
  const filename = original || fallback;
  const headers = new Headers({
    "Content-Type": record.mime || upstream.headers.get("content-type") || "application/octet-stream",
    "Content-Disposition": `${disposition}; filename="${filename}"`,
    "Cache-Control": "private, no-store",
    "X-Content-Type-Options": "nosniff",
    "Accept-Ranges": upstream.headers.get("accept-ranges") || "bytes",
  });
  for (const header of ["content-length", "content-range"]) {
    const value = upstream.headers.get(header);
    if (value) headers.set(header, value);
  }
  return headers;
}
