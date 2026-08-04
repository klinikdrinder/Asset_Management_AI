import test from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { FirebaseAdminCredentialError, createExplicitFirebaseAdminCredential, resolveFirebaseAdminCredentialPath } from "../app/lib/firebase/admin-credentials";

const approved = "C:\\Users\\Public\\Asset_Management_AI\\.secrets\\firebase-admin.json";
const emptyEnv = {} as NodeJS.ProcessEnv;
function safeCode(code: string) { return (error: unknown) => error instanceof FirebaseAdminCredentialError && error.code === code; }

test("absolute configured credential resolves", () => assert.equal(resolveFirebaseAdminCredentialPath({ env: { GOOGLE_APPLICATION_CREDENTIALS: approved }, fallbackPaths: [] }), approved));
test("relative configured credential resolves from cwd", () => assert.equal(resolveFirebaseAdminCredentialPath({ env: { GOOGLE_APPLICATION_CREDENTIALS: ".secrets\\firebase-admin.json" }, cwd: "C:\\Users\\Public\\Asset_Management_AI", fallbackPaths: [] }), approved));
test("approved fallback resolves without terminal environment", () => assert.equal(resolveFirebaseAdminCredentialPath({ env: emptyEnv }), approved));
test("invalid configured path fails closed", () => assert.throws(() => resolveFirebaseAdminCredentialPath({ env: { GOOGLE_APPLICATION_CREDENTIALS: "missing.json" }, fallbackPaths: [approved] }), safeCode("firebase_admin_credentials_unavailable")));
test("missing configured and fallback paths fail closed", () => assert.throws(() => resolveFirebaseAdminCredentialPath({ env: emptyEnv, fallbackPaths: [] }), safeCode("firebase_admin_credentials_unavailable")));

test("empty malformed and incomplete credentials fail safely", () => {
  const dir = mkdtempSync(path.join(tmpdir(), "kdi-admin-test-"));
  const cases = [["empty.json", "", "firebase_admin_credentials_malformed"], ["malformed.json", "not-json", "firebase_admin_credentials_malformed"], ["incomplete.json", "{}", "firebase_admin_credentials_incomplete"]] as const;
  for (const [name, content, code] of cases) {
    const file = path.join(dir, name); writeFileSync(file, content, "utf8");
    assert.throws(() => createExplicitFirebaseAdminCredential({ env: { GOOGLE_APPLICATION_CREDENTIALS: file }, fallbackPaths: [] }), safeCode(code));
  }
});

test("credential and environment project mismatches fail safely", () => {
  assert.throws(() => createExplicitFirebaseAdminCredential({ env: { GOOGLE_APPLICATION_CREDENTIALS: approved }, expectedProjectId: "mismatch" }), safeCode("firebase_admin_project_mismatch"));
  assert.throws(() => createExplicitFirebaseAdminCredential({ env: { GOOGLE_APPLICATION_CREDENTIALS: approved, FIREBASE_PROJECT_ID: "mismatch" } }), safeCode("firebase_admin_project_mismatch"));
});
