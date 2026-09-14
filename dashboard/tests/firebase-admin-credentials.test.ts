import test from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, mkdirSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { FirebaseAdminCredentialError, createExplicitFirebaseAdminCredential, resolveFirebaseAdminCredentialPath } from "../app/lib/firebase/admin-credentials";
import { FIREBASE_PROJECT_ID } from "../app/lib/firebase/config";

const emptyEnv = {} as NodeJS.ProcessEnv;
function safeCode(code: string) { return (error: unknown) => error instanceof FirebaseAdminCredentialError && error.code === code; }

// Synthetic, non-secret service-account JSON (fake key material) whose project_id
// matches the app. These tests never require a real credential file and never
// depend on any machine-specific absolute path.
const validAccount = JSON.stringify({
  type: "service_account",
  project_id: FIREBASE_PROJECT_ID,
  client_email: `ci@${FIREBASE_PROJECT_ID}.iam.gserviceaccount.com`,
  private_key: "-----BEGIN PRIVATE KEY-----\\nFAKE_TEST_KEY\\n-----END PRIVATE KEY-----\\n",
});

function tmpFile(name: string, content: string) {
  const dir = mkdtempSync(path.join(tmpdir(), "kdi-admin-test-"));
  const file = path.join(dir, name);
  writeFileSync(file, content, "utf8");
  return { dir, file };
}

test("absolute configured credential resolves to itself", () => {
  const { file } = tmpFile("firebase-admin.json", validAccount);
  assert.equal(resolveFirebaseAdminCredentialPath({ env: { GOOGLE_APPLICATION_CREDENTIALS: file }, fallbackPaths: [] }), path.resolve(file));
});

test("relative configured credential resolves from cwd (drive-agnostic)", () => {
  const { dir } = tmpFile("firebase-admin.json", validAccount);
  const resolved = resolveFirebaseAdminCredentialPath({ env: { GOOGLE_APPLICATION_CREDENTIALS: "firebase-admin.json" }, cwd: dir, fallbackPaths: [] });
  assert.equal(resolved, path.join(dir, "firebase-admin.json"));
  assert.ok(!resolved.includes("D:\\Asset_Management_AI"), "resolution must not reference the old D: project root");
});

test("approved fallback resolves repository-relative from cwd, never drive D:", () => {
  // Emulate the package layout: <root>/.secrets/firebase-admin.json with cwd =
  // <root>/dashboard. approvedCandidates uses path.resolve(cwd,"..",".secrets",…).
  const root = mkdtempSync(path.join(tmpdir(), "kdi-root-"));
  const dashboard = path.join(root, "dashboard");
  const secrets = path.join(root, ".secrets");
  mkdirSync(dashboard, { recursive: true });
  mkdirSync(secrets, { recursive: true });
  const file = path.join(secrets, "firebase-admin.json");
  writeFileSync(file, validAccount, "utf8");
  const resolved = resolveFirebaseAdminCredentialPath({ env: emptyEnv, cwd: dashboard });
  assert.equal(resolved, file);
  assert.ok(!resolved.includes("D:\\Asset_Management_AI"), "resolved path must not reference the old D: project root");
});

test("invalid configured path fails closed", () => {
  const { dir } = tmpFile("real.json", validAccount);
  assert.throws(() => resolveFirebaseAdminCredentialPath({ env: { GOOGLE_APPLICATION_CREDENTIALS: "missing.json" }, cwd: dir, fallbackPaths: [] }), safeCode("firebase_admin_credentials_unavailable"));
});

test("missing configured and fallback paths fail closed", () => assert.throws(() => resolveFirebaseAdminCredentialPath({ env: emptyEnv, fallbackPaths: [] }), safeCode("firebase_admin_credentials_unavailable")));

test("empty, malformed and incomplete credentials fail safely", () => {
  const cases = [["empty.json", "", "firebase_admin_credentials_malformed"], ["malformed.json", "not-json", "firebase_admin_credentials_malformed"], ["incomplete.json", "{}", "firebase_admin_credentials_incomplete"]] as const;
  for (const [name, content, code] of cases) {
    const { file } = tmpFile(name, content);
    assert.throws(() => createExplicitFirebaseAdminCredential({ env: { GOOGLE_APPLICATION_CREDENTIALS: file }, fallbackPaths: [] }), safeCode(code));
  }
});

test("credential and environment project mismatches fail safely", () => {
  const { file } = tmpFile("firebase-admin.json", validAccount);
  assert.throws(() => createExplicitFirebaseAdminCredential({ env: { GOOGLE_APPLICATION_CREDENTIALS: file }, expectedProjectId: "mismatch" }), safeCode("firebase_admin_project_mismatch"));
  assert.throws(() => createExplicitFirebaseAdminCredential({ env: { GOOGLE_APPLICATION_CREDENTIALS: file, FIREBASE_PROJECT_ID: "mismatch" } }), safeCode("firebase_admin_project_mismatch"));
});
