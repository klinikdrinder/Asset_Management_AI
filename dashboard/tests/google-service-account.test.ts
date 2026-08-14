import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { GoogleServiceAccountError, resolveGoogleServiceAccount, resolveKdiMasterDriveId } from "../app/lib/google/service-account";

const validKey = "-----BEGIN PRIVATE KEY-----\\nMIIFAKEKEYDATA\\n-----END PRIVATE KEY-----\\n";

test("missing credentials fail closed with a sanitized code, not a stack trace", () => {
  assert.throws(() => resolveGoogleServiceAccount({} as unknown as NodeJS.ProcessEnv), (error: unknown) => {
    assert.ok(error instanceof GoogleServiceAccountError);
    assert.equal(error.code, "google_service_account_credentials_unavailable");
    return true;
  });
});

test("env key-pair credentials are read and escaped newlines are decoded", () => {
  const account = resolveGoogleServiceAccount({ GOOGLE_DRIVE_SERVICE_ACCOUNT_EMAIL: "svc@kdi-media-library.iam.gserviceaccount.com", GOOGLE_DRIVE_SERVICE_ACCOUNT_PRIVATE_KEY: validKey } as unknown as NodeJS.ProcessEnv);
  assert.equal(account.clientEmail, "svc@kdi-media-library.iam.gserviceaccount.com");
  assert.ok(account.privateKey.includes("\n"), "escaped \\n sequences must become real newlines");
  assert.ok(!account.privateKey.includes("\\n"), "no literal backslash-n should remain");
});

test("a private key missing the PEM header is rejected before use", () => {
  assert.throws(() => resolveGoogleServiceAccount({ GOOGLE_DRIVE_SERVICE_ACCOUNT_EMAIL: "svc@example.iam.gserviceaccount.com", GOOGLE_DRIVE_SERVICE_ACCOUNT_PRIVATE_KEY: "not-a-real-key" } as unknown as NodeJS.ProcessEnv), (error: unknown) => {
    assert.ok(error instanceof GoogleServiceAccountError);
    assert.equal(error.code, "google_service_account_private_key_malformed");
    return true;
  });
});

test("malformed inline service-account JSON fails closed", () => {
  assert.throws(() => resolveGoogleServiceAccount({ GOOGLE_DRIVE_SERVICE_ACCOUNT_CREDENTIALS_JSON: "{not json" } as unknown as NodeJS.ProcessEnv), (error: unknown) => {
    assert.ok(error instanceof GoogleServiceAccountError);
    assert.equal(error.code, "google_service_account_credentials_malformed");
    return true;
  });
});

test("inline JSON missing required service-account fields fails closed", () => {
  assert.throws(() => resolveGoogleServiceAccount({ GOOGLE_DRIVE_SERVICE_ACCOUNT_CREDENTIALS_JSON: JSON.stringify({ type: "service_account" }) } as unknown as NodeJS.ProcessEnv), (error: unknown) => {
    assert.ok(error instanceof GoogleServiceAccountError);
    assert.equal(error.code, "google_service_account_credentials_incomplete");
    return true;
  });
});

test("a nonexistent credentials file path fails closed rather than throwing a raw fs error", () => {
  assert.throws(() => resolveGoogleServiceAccount({ GOOGLE_DRIVE_SERVICE_ACCOUNT_CREDENTIALS_PATH: "C:/nonexistent/does-not-exist.json" } as unknown as NodeJS.ProcessEnv), (error: unknown) => {
    assert.ok(error instanceof GoogleServiceAccountError);
    assert.equal(error.code, "google_service_account_credentials_unavailable");
    return true;
  });
});

test("GOOGLE_APPLICATION_CREDENTIALS is honored as a fallback file path, matching the repository's existing convention", () => {
  const source = readFileSync("app/lib/google/service-account.ts", "utf8");
  assert.match(source, /GOOGLE_APPLICATION_CREDENTIALS/);
});

test("KDI_MASTER_DRIVE_ID is required and validated independently of credentials", () => {
  assert.throws(() => resolveKdiMasterDriveId({} as unknown as NodeJS.ProcessEnv), (error: unknown) => {
    assert.ok(error instanceof GoogleServiceAccountError);
    assert.equal(error.code, "kdi_master_drive_id_unavailable");
    return true;
  });
  assert.equal(resolveKdiMasterDriveId({ KDI_MASTER_DRIVE_ID: " abc123 " } as unknown as NodeJS.ProcessEnv), "abc123");
});

test("no credential path in this module ever begins with NEXT_PUBLIC_", () => {
  const source = readFileSync("app/lib/google/service-account.ts", "utf8");
  assert.doesNotMatch(source, /NEXT_PUBLIC_/);
  assert.match(source, /server-only/);
});
