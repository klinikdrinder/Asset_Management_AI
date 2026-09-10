import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

// dashboard/tests -> dashboard -> repository root
const here = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(here, "..", "..");
const OLD_ROOT = "D:\\Asset_Management_AI";

function read(rel: string) {
  return readFileSync(path.join(repoRoot, ...rel.split("/")), "utf8");
}

// Active runtime files that previously hard-coded the old-PC D: project root.
const ACTIVE_FILES = [
  "scripts/run-repository-maintenance.ps1",
  "scripts/install-kdi-repository-maintenance-task.ps1",
  "scripts/run-semantic-worker.ps1",
  "scripts/deploy_step10_legacy_status_fix.py",
  "src/kdi_media/google_drive.py",
  "dashboard/app/lib/firebase/admin-credentials.ts",
  "dashboard/app/auth/callback/diagnostics.ts",
];

test("no active runtime file references the old-PC D: project root", () => {
  for (const rel of ACTIVE_FILES) {
    assert.ok(!read(rel).includes(OLD_ROOT), `${rel} must not reference ${OLD_ROOT}`);
  }
});

test("maintenance and worker scripts derive the project root dynamically", () => {
  for (const rel of [
    "scripts/run-repository-maintenance.ps1",
    "scripts/install-kdi-repository-maintenance-task.ps1",
    "scripts/run-semantic-worker.ps1",
  ]) {
    assert.ok(read(rel).includes("$PSScriptRoot"), `${rel} must derive its root from $PSScriptRoot`);
  }
});

test("firebase admin credential fallback is repository-relative, not drive-absolute", () => {
  const src = read("dashboard/app/lib/firebase/admin-credentials.ts");
  assert.ok(src.includes('path.resolve(cwd, "..", ".secrets", "firebase-admin.json")'), "must resolve the approved fallback relative to cwd");
  assert.ok(!/[A-Za-z]:\\\\Asset_Management_AI/.test(src), "must not embed an absolute drive project root");
});

test("auth diagnostics default log dir is process-relative", () => {
  const src = read("dashboard/app/auth/callback/diagnostics.ts");
  assert.ok(src.includes("process.cwd()"), "diagnostics must default its log dir to process.cwd()");
  assert.ok(!/[A-Za-z]:\\\\Asset_Management_AI/.test(src), "must not embed an absolute drive project root");
});

test("google drive credential default derives project root from module location", () => {
  const src = read("src/kdi_media/google_drive.py");
  assert.ok(src.includes("parents[2]"), "google_drive must derive the project root from __file__");
  assert.ok(src.includes("GOOGLE_DRIVE_SERVICE_ACCOUNT_CREDENTIALS_PATH"), "the env override must be honored ahead of the default");
});
