import test from "node:test";
import assert from "node:assert/strict";
import { rm, writeFile } from "node:fs/promises";
import path from "node:path";
import { readThumbnailCache, thumbnailCacheKey, writeThumbnailCache } from "../app/lib/media/thumbnail-cache";
const env = process.env as Record<string, string | undefined>;

const DEV_CACHE_DIR = path.join(process.cwd(), ".cache", "thumbnails");

test("cache key is derived from asset id + Drive file id + version tag", () => {
  const key = thumbnailCacheKey("asset-1", "drive-file-1", "2026-08-01T00:00:00Z");
  assert.match(key, /^asset-1\/drive-file-1-.*\.jpg$/);
});

test("a changed version tag changes the cache key (destination re-verified/replaced invalidates old entries)", () => {
  const before = thumbnailCacheKey("asset-1", "drive-file-1", "2026-08-01T00:00:00Z");
  const after = thumbnailCacheKey("asset-1", "drive-file-1", "2026-08-02T00:00:00Z");
  assert.notEqual(before, after);
});

test("an unversioned/empty tag still produces a stable, safe key rather than throwing", () => {
  assert.doesNotThrow(() => thumbnailCacheKey("asset-1", "drive-file-1", ""));
  assert.match(thumbnailCacheKey("asset-1", "drive-file-1", ""), /unversioned/);
});

test("path separators in the version tag cannot introduce extra path segments into the storage key", () => {
  const key = thumbnailCacheKey("asset-1", "drive-file-1", "2026-08-01T00:00:00Z/../../etc");
  // The key is always exactly "<assetId>/<driveFileId>-<version>.<ext>" - a
  // slash smuggled in through the version tag must not add a second "/".
  assert.equal(key.indexOf("/"), key.lastIndexOf("/"));
  assert.ok(key.startsWith("asset-1/drive-file-1-"));
});

test("dev filesystem cache: write then read is a hit with the exact bytes and content type", async (t) => {
  const originalEnv = process.env.NODE_ENV;
  env.NODE_ENV = "development";
  t.after(async () => { env.NODE_ENV = originalEnv; await rm(DEV_CACHE_DIR, { recursive: true, force: true }); });
  const assetId = `test-hit-${Date.now()}`, driveFileId = "drive-1", version = "v1";
  await writeThumbnailCache(assetId, driveFileId, version, { bytes: Buffer.from("hello-thumbnail"), contentType: "image/jpeg" });
  const cached = await readThumbnailCache(assetId, driveFileId, version);
  assert.ok(cached);
  assert.equal(cached!.bytes.toString(), "hello-thumbnail");
  assert.equal(cached!.contentType, "image/jpeg");
});

test("dev filesystem cache: a different version tag is a miss (invalidation), not a stale hit", async (t) => {
  const originalEnv = process.env.NODE_ENV;
  env.NODE_ENV = "development";
  t.after(async () => { env.NODE_ENV = originalEnv; await rm(DEV_CACHE_DIR, { recursive: true, force: true }); });
  const assetId = `test-invalidate-${Date.now()}`, driveFileId = "drive-1";
  await writeThumbnailCache(assetId, driveFileId, "v1", { bytes: Buffer.from("old"), contentType: "image/jpeg" });
  const miss = await readThumbnailCache(assetId, driveFileId, "v2");
  assert.equal(miss, null);
});

test("dev filesystem cache: a corrupt (empty) entry is treated as a miss, not a crash", async (t) => {
  const originalEnv = process.env.NODE_ENV;
  env.NODE_ENV = "development";
  t.after(async () => { env.NODE_ENV = originalEnv; await rm(DEV_CACHE_DIR, { recursive: true, force: true }); });
  const assetId = `test-corrupt-${Date.now()}`, driveFileId = "drive-1", version = "v1";
  await writeThumbnailCache(assetId, driveFileId, version, { bytes: Buffer.from("valid"), contentType: "image/jpeg" });
  const key = thumbnailCacheKey(assetId, driveFileId, version);
  const bytesPath = path.join(DEV_CACHE_DIR, key.replace(/\//g, "__"));
  await writeFile(bytesPath, Buffer.alloc(0)); // simulate a truncated/corrupt write
  const recovered = await readThumbnailCache(assetId, driveFileId, version);
  assert.equal(recovered, null);
});

test("dev filesystem cache: a missing entry never throws", async (t) => {
  const originalEnv = process.env.NODE_ENV;
  env.NODE_ENV = "development";
  t.after(() => { env.NODE_ENV = originalEnv; });
  const missing = await readThumbnailCache("no-such-asset", "no-such-file", "v1");
  assert.equal(missing, null);
});
