import test from "node:test";
import assert from "node:assert/strict";
import { isAssetActive, resolveAssetMediaLocation, resolveFromAssetRow, type ResolvableAssetRow } from "../app/lib/media/resolve-location";

const VERIFIED_ASSET_ID = "11111111-1111-4111-8111-111111111111";

function baseRow(overrides: Partial<ResolvableAssetRow> = {}): ResolvableAssetRow {
  return {
    id: VERIFIED_ASSET_ID,
    file_name: "photo.jpg",
    mime_type: "image/jpeg",
    file_extension: "jpg",
    size_bytes: 12345,
    upload_status: "UPLOADED",
    asset_destinations: [],
    ...overrides,
  };
}

test("a verified destination is the canonical selection", () => {
  const { location, reason } = resolveFromAssetRow(baseRow({
    asset_destinations: [{ upload_status: "VERIFIED", destination_google_file_id: "drive-file-1", destination_filename: "photo.jpg", verified_at: "2026-08-01T00:00:00Z" }],
  }));
  assert.equal(reason, "destination");
  assert.equal(location?.source, "destination");
  assert.equal(location?.driveFileId, "drive-file-1");
  assert.equal(location?.versionTag, "2026-08-01T00:00:00Z");
});

test("an unverified destination alone is not selected", () => {
  const { location, reason } = resolveFromAssetRow(baseRow({
    asset_destinations: [{ upload_status: "UPLOADED", destination_google_file_id: "drive-file-1" }],
  }));
  assert.equal(location, null);
  assert.equal(reason, "no_verified_destination_or_fallback");
});

test("no destination row at all is reported distinctly from an unverified one", () => {
  const { location, reason } = resolveFromAssetRow(baseRow({ asset_destinations: [] }));
  assert.equal(location, null);
  assert.equal(reason, "no_destination");
});

test("an inactive (failed/missing) asset is rejected before any destination is considered", () => {
  for (const uploadStatus of ["FAILED", "MISSING"]) {
    const { location, reason } = resolveFromAssetRow(baseRow({
      upload_status: uploadStatus,
      asset_destinations: [{ upload_status: "VERIFIED", destination_google_file_id: "drive-file-1" }],
    }));
    assert.equal(location, null, uploadStatus);
    assert.equal(reason, "inactive_asset", uploadStatus);
  }
  assert.equal(isAssetActive("FAILED"), false);
  assert.equal(isAssetActive("MISSING"), false);
  assert.equal(isAssetActive("UPLOADED"), true);
  assert.equal(isAssetActive(undefined), true);
});

test("source fallback is only used when explicitly enabled, and never for an inactive or trashed candidate", () => {
  const row = baseRow({
    asset_destinations: [],
    source_files: [{ google_file_id: "src-1", file_name: "orig.jpg", mime_type: "image/jpeg", file_extension: "jpg", size_bytes: 999, trashed: false, is_missing: false }],
  });
  const withoutFallback = resolveFromAssetRow(row);
  assert.equal(withoutFallback.location, null);
  assert.equal(withoutFallback.reason, "no_destination");

  const withFallback = resolveFromAssetRow(row, { allowSourceFallback: true });
  assert.equal(withFallback.location?.source, "source_fallback");
  assert.equal(withFallback.location?.driveFileId, "src-1");
  assert.equal(withFallback.reason, "source_fallback");

  const trashedRow = baseRow({ asset_destinations: [], source_files: [{ google_file_id: "src-1", file_name: "orig.jpg", mime_type: null, file_extension: null, size_bytes: null, trashed: true, is_missing: false }] });
  assert.equal(resolveFromAssetRow(trashedRow, { allowSourceFallback: true }).location, null);
});

test("a VERIFIED destination always wins over an available source fallback", () => {
  const row = baseRow({
    asset_destinations: [{ upload_status: "VERIFIED", destination_google_file_id: "drive-file-1" }],
    source_files: [{ google_file_id: "src-1", file_name: "orig.jpg", mime_type: "image/jpeg", file_extension: "jpg", size_bytes: 1, trashed: false, is_missing: false }],
  });
  const { location } = resolveFromAssetRow(row, { allowSourceFallback: true });
  assert.equal(location?.source, "destination");
  assert.equal(location?.driveFileId, "drive-file-1");
});

test("resolveAssetMediaLocation rejects non-UUID input before ever calling fetchRow", async () => {
  let called = false;
  const location = await resolveAssetMediaLocation("not-a-uuid", "thumbnail", async () => { called = true; return null; });
  assert.equal(location, null);
  assert.equal(called, false);
});

test("resolveAssetMediaLocation returns null for a removed/unknown asset without throwing", async () => {
  const location = await resolveAssetMediaLocation(VERIFIED_ASSET_ID, "download", async () => null);
  assert.equal(location, null);
});

test("resolveAssetMediaLocation surfaces the resolved destination end to end", async () => {
  const location = await resolveAssetMediaLocation(VERIFIED_ASSET_ID, "preview", async (id) => {
    assert.equal(id, VERIFIED_ASSET_ID);
    return baseRow({ asset_destinations: [{ upload_status: "VERIFIED", destination_google_file_id: "drive-file-9" }] });
  });
  assert.equal(location?.driveFileId, "drive-file-9");
});
