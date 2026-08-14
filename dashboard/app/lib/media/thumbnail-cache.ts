import "server-only";

import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { createServiceClient } from "../supabase/service";

// Durable thumbnail cache. Keyed by asset id + destination Drive file id +
// a version tag (the destination's verified_at/upload_completed_at
// timestamp) so a re-verified or replaced destination invalidates old
// thumbnails automatically, while repeated page loads for an unchanged
// asset never re-hit Google Drive.
//
// Production persists into Supabase Storage (already the project's storage
// mechanism - see assets.storage_bucket/storage_path - so this reuses it
// rather than adding new infrastructure). Local development uses a
// filesystem cache under dashboard/.cache/thumbnails so engineers are not
// forced to touch shared Storage just to run `npm run dev`.
const BUCKET = "media-thumbnails";
const DEV_CACHE_DIR = path.join(/*turbopackIgnore: true*/ process.cwd(), ".cache", "thumbnails");

export type CachedThumbnail = { bytes: Buffer; contentType: string };

export function thumbnailCacheKey(assetId: string, driveFileId: string, versionTag: string, extension = "jpg"): string {
  const safeVersion = versionTag.replace(/[^a-zA-Z0-9_.:-]/g, "_").slice(0, 80) || "unversioned";
  const safeExt = extension.replace(/[^a-z0-9]/gi, "").toLowerCase() || "jpg";
  return `${assetId}/${driveFileId}-${safeVersion}.${safeExt}`;
}

function devCachePaths(key: string) {
  const base = path.join(/*turbopackIgnore: true*/ DEV_CACHE_DIR, key.replace(/\//g, "__"));
  return { bytesPath: base, metaPath: `${base}.meta.json` };
}

async function readDevCache(key: string): Promise<CachedThumbnail | null> {
  const { bytesPath, metaPath } = devCachePaths(key);
  try {
    const [bytes, metaRaw] = await Promise.all([readFile(/*turbopackIgnore: true*/ bytesPath), readFile(/*turbopackIgnore: true*/ metaPath, "utf8")]);
    if (!bytes.length) return null;
    const meta = JSON.parse(metaRaw) as { contentType?: unknown };
    return { bytes, contentType: typeof meta.contentType === "string" && meta.contentType ? meta.contentType : "image/jpeg" };
  } catch {
    // Missing file, unreadable file, or corrupt JSON - all treated as a
    // plain cache miss so the caller re-fetches and repairs the entry.
    return null;
  }
}

async function writeDevCache(key: string, value: CachedThumbnail): Promise<void> {
  const { bytesPath, metaPath } = devCachePaths(key);
  try {
    await mkdir(/*turbopackIgnore: true*/ DEV_CACHE_DIR, { recursive: true });
    await writeFile(/*turbopackIgnore: true*/ bytesPath, value.bytes);
    await writeFile(/*turbopackIgnore: true*/ metaPath, JSON.stringify({ contentType: value.contentType }));
  } catch {
    // Best-effort: a cache write failure must never fail the request.
  }
}

let bucketEnsured = false;
async function ensureBucket(): Promise<void> {
  if (bucketEnsured) return;
  try {
    await createServiceClient().storage.createBucket(BUCKET, { public: false, fileSizeLimit: "6MB" });
  } catch {
    // Already exists (or transient) - either way, proceed and let the
    // subsequent read/write call report its own real error if any.
  }
  bucketEnsured = true;
}

async function readProdCache(key: string): Promise<CachedThumbnail | null> {
  try {
    const { data, error } = await createServiceClient().storage.from(BUCKET).download(key);
    if (error || !data) return null;
    const bytes = Buffer.from(await data.arrayBuffer());
    if (!bytes.length) return null;
    return { bytes, contentType: data.type || "image/jpeg" };
  } catch {
    return null;
  }
}

async function writeProdCache(key: string, value: CachedThumbnail): Promise<void> {
  try {
    await ensureBucket();
    await createServiceClient().storage.from(BUCKET).upload(key, value.bytes, { contentType: value.contentType, upsert: true });
  } catch {
    // Best-effort: a cache write failure must never fail the request, and a
    // Drive-side transient error must never be written to cache in the
    // first place (callers only call writeThumbnailCache after a
    // successful fetch), so failures here simply mean "try again next time".
  }
}

function isDevCache(): boolean {
  return process.env.NODE_ENV === "development";
}

export async function readThumbnailCache(assetId: string, driveFileId: string, versionTag: string, extension = "jpg"): Promise<CachedThumbnail | null> {
  const key = thumbnailCacheKey(assetId, driveFileId, versionTag, extension);
  return isDevCache() ? readDevCache(key) : readProdCache(key);
}

export async function writeThumbnailCache(assetId: string, driveFileId: string, versionTag: string, value: CachedThumbnail, extension = "jpg"): Promise<void> {
  const key = thumbnailCacheKey(assetId, driveFileId, versionTag, extension);
  return isDevCache() ? writeDevCache(key, value) : writeProdCache(key, value);
}
