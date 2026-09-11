/**
 * Pre-generate 400px WebP thumbnails for the whole library so the grid never waits on a cold
 * Google Drive fetch, and so bytes can be served from Supabase Storage (see the signed-URL path
 * in media-service). Reuses the existing Drive client + location resolver + cache-key convention;
 * the only new step is sharp resize -> WebP.
 *
 * Runtime prerequisites (this box may lack them — the script fails loudly if so):
 *   - Google Drive service-account creds (GOOGLE_DRIVE_SERVICE_ACCOUNT_* / GOOGLE_APPLICATION_CREDENTIALS)
 *   - SUPABASE_SERVICE_ROLE_KEY (present in dashboard/.env.local)
 *
 * Usage (from dashboard/):
 *   Dry run (default, no writes):  cross-env NODE_OPTIONS=--conditions=react-server tsx scripts/backfill-thumbnails.ts
 *   Apply (mass writes+uploads):   ... tsx scripts/backfill-thumbnails.ts --apply
 *   Limit for a canary:            ... tsx scripts/backfill-thumbnails.ts --apply --limit=20
 *
 * --apply performs ~1 upload + 1 asset_derivatives insert per asset. Per owner rule, only run
 * --apply after an approved dry run.
 */
import { readFileSync } from "node:fs";
import { createHash } from "node:crypto";
import path from "node:path";
import sharp from "sharp";
import { createClient } from "@supabase/supabase-js";
import { resolveFromAssetRow, type ResolvableAssetRow, type ResolvedMediaLocation } from "../app/lib/media/resolve-location";
import { getDriveFileMetadata, fetchDriveThumbnailLinkBytes, downloadDriveFile } from "../app/lib/google/drive-client";
import { extractPosterFrame } from "../app/lib/media/video-poster";
import { thumbnailCacheKey } from "../app/lib/media/thumbnail-cache";

const BUCKET = "media-thumbnails";
const THUMB_PX = 400;
const VIDEO_PROBE_RANGE = "bytes=0-6291455";
const CONCURRENCY = 4;

// Standalone scripts do not get Next's .env.local; load it so the service key + any Drive vars
// are available in process.env before we construct clients.
function loadEnvLocal() {
  try {
    const text = readFileSync(path.join(process.cwd(), ".env.local"), "utf8");
    for (const line of text.split(/\r?\n/)) {
      const m = /^([A-Z0-9_]+)=(.*)$/.exec(line.trim());
      if (m && !(m[1] in process.env)) process.env[m[1]] = m[2];
    }
  } catch { /* rely on the ambient environment */ }
}

const argv = process.argv.slice(2);
const APPLY = argv.includes("--apply");
const LIMIT = Number((argv.find((a) => a.startsWith("--limit=")) ?? "").split("=")[1]) || Infinity;

const sha256 = (buf: Buffer) => createHash("sha256").update(buf).digest("hex");
// Drive thumbnailLink usually ends in "=sNNN"; request a larger source so the 400px WebP is crisp.
const upsize = (link: string) => (/=s\d+(-c)?$/.test(link) ? link.replace(/=s\d+(-c)?$/, "=s800") : link);

const ASSET_SELECT =
  "id,file_name,mime_type,file_extension,size_bytes,upload_status," +
  "asset_destinations!inner(id,destination_google_file_id,destination_filename,upload_status,verified_at,upload_completed_at)";

async function sourceBytes(location: ResolvedMediaLocation): Promise<Buffer | null> {
  const meta = await getDriveFileMetadata(location.driveFileId, "thumbnailLink,mimeType", undefined).catch(() => null);
  if (meta?.thumbnailLink) {
    const resp = await fetchDriveThumbnailLinkBytes(upsize(meta.thumbnailLink)).catch(() => null);
    if (resp?.ok) return Buffer.from(await resp.arrayBuffer());
  }
  if (location.mime.startsWith("video/")) {
    const resp = await downloadDriveFile(location.driveFileId, { range: VIDEO_PROBE_RANGE, timeoutMs: 30_000 }).catch(() => null);
    if (resp) { const frame = await extractPosterFrame(Buffer.from(await resp.arrayBuffer())); if (frame) return frame; }
  }
  return null;
}

async function mapWithConcurrency<T>(items: T[], limit: number, fn: (item: T) => Promise<void>) {
  let i = 0;
  await Promise.all(Array.from({ length: Math.min(limit, items.length) }, async () => {
    while (i < items.length) { const idx = i++; await fn(items[idx]); }
  }));
}

async function main() {
  loadEnvLocal();
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL, key = process.env.SUPABASE_SERVICE_ROLE_KEY;
  if (!url || !key) throw new Error("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY missing");
  const supa = createClient(url, key, { auth: { persistSession: false } });

  const { data: assetRows, error } = await supa.from("assets").select(ASSET_SELECT).eq("asset_destinations.upload_status", "VERIFIED");
  if (error) throw error;
  const rows = (assetRows ?? []) as unknown as ResolvableAssetRow[];

  const { data: existing } = await supa.from("asset_derivatives").select("asset_id").eq("derivative_type", "THUMBNAIL").eq("generation_status", "READY");
  const done = new Set((existing ?? []).map((r) => String(r.asset_id)));

  const candidates = rows
    .filter((r) => { const m = String(r.mime_type ?? ""); return m.startsWith("image/") || m.startsWith("video/"); })
    .map((r) => resolveFromAssetRow(r).location)
    .filter((l): l is ResolvedMediaLocation => !!l && !done.has(l.assetId))
    .slice(0, LIMIT);

  console.log(`[thumbnails] verified assets=${rows.length} already-done=${done.size} to-generate=${candidates.length} mode=${APPLY ? "APPLY" : "DRY-RUN"}`);
  if (!APPLY) {
    console.log(`[thumbnails] DRY RUN — no uploads or DB writes. Sample asset ids:`);
    candidates.slice(0, 10).forEach((l) => console.log(`  ${l.assetId} (${l.mime})`));
    console.log(`[thumbnails] re-run with --apply to generate (needs Drive creds + owner approval).`);
    return;
  }

  let ok = 0, failed = 0;
  await mapWithConcurrency(candidates, CONCURRENCY, async (location) => {
    try {
      const src = await sourceBytes(location);
      if (!src) { failed++; console.warn(`[thumbnails] no source for ${location.assetId}`); return; }
      const webp = await sharp(src).rotate().resize(THUMB_PX, THUMB_PX, { fit: "inside", withoutEnlargement: false }).webp({ quality: 80 }).toBuffer();
      const dims = await sharp(webp).metadata();
      const key = thumbnailCacheKey(location.assetId, location.driveFileId, location.versionTag, "webp");
      const up = await supa.storage.from(BUCKET).upload(key, webp, { contentType: "image/webp", upsert: true });
      if (up.error) throw up.error;
      const ins = await supa.from("asset_derivatives").insert({
        asset_id: location.assetId, derivative_type: "THUMBNAIL", storage_provider: "SUPABASE_STORAGE",
        storage_bucket: BUCKET, storage_path: key, mime_type: "image/webp", file_extension: "webp",
        file_size_bytes: webp.length, width: dims.width ?? THUMB_PX, height: dims.height ?? THUMB_PX,
        content_hash: sha256(webp), generation_status: "READY",
      });
      if (ins.error) throw ins.error;
      ok++;
    } catch (e) { failed++; console.warn(`[thumbnails] failed ${location.assetId}: ${e instanceof Error ? e.message : e}`); }
  });
  console.log(`[thumbnails] done ok=${ok} failed=${failed}`);
}

main().catch((e) => { console.error(e); process.exit(1); });
