import test from "node:test";
import assert from "node:assert/strict";
import { classifyDriveStatus, DriveApiError, fetchDriveThumbnailLinkBytes } from "../app/lib/google/drive-client";

test("Drive HTTP statuses are classified into stable, sanitized error codes", () => {
  assert.equal(classifyDriveStatus(401), "drive_unauthorized");
  assert.equal(classifyDriveStatus(403), "drive_forbidden");
  assert.equal(classifyDriveStatus(404), "drive_not_found");
  assert.equal(classifyDriveStatus(429), "drive_rate_limited");
  assert.equal(classifyDriveStatus(500), "drive_upstream_error");
  assert.equal(classifyDriveStatus(503), "drive_upstream_error");
  assert.equal(classifyDriveStatus(418), "drive_error");
});

test("DriveApiError carries the original HTTP status alongside the sanitized code", () => {
  const error = new DriveApiError(429, "drive_rate_limited");
  assert.equal(error.status, 429);
  assert.equal(error.code, "drive_rate_limited");
  assert.equal(error.name, "DriveApiError");
});

test("a thumbnailLink that is not a genuine googleusercontent.com HTTPS URL is rejected before any fetch, closing off SSRF via a spoofed link", async () => {
  await assert.rejects(fetchDriveThumbnailLinkBytes("http://googleusercontent.com/evil"), (error: unknown) => error instanceof DriveApiError);
  await assert.rejects(fetchDriveThumbnailLinkBytes("https://evil.example.com/lh3.googleusercontent.com"), (error: unknown) => error instanceof DriveApiError);
  await assert.rejects(fetchDriveThumbnailLinkBytes("not-a-url"), (error: unknown) => error instanceof DriveApiError);
});
