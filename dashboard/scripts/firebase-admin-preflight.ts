import nextEnv from "@next/env";

const cwd = process.cwd();
nextEnv.loadEnvConfig(cwd);

function output(result: { credentialResolved: boolean; projectMatched: boolean; initialized: boolean; reachable: boolean; metadataPrevented: boolean }) {
  console.log(`credential_resolved=${result.credentialResolved}`);
  console.log(`project_matched=${result.projectMatched}`);
  console.log(`firebase_admin_initialized=${result.initialized}`);
  console.log(`firebase_auth_api_reachable=${result.reachable}`);
  console.log(`metadata_fallback_prevented=${result.metadataPrevented}`);
}

let credentialResolved = false;
let projectMatched = false;
let initialized = false;
try {
  const credentials = await import("../app/lib/firebase/admin-credentials");
  const admin = await import("../app/lib/firebase/admin");
  const status = credentials.firebaseAdminCredentialPreflight();
  credentialResolved = status.credentialResolved;
  projectMatched = status.projectMatched;
  admin.getFirebaseAdminApp();
  initialized = true;
  const page = await admin.getFirebaseAdminAuth().listUsers(1);
  void page.users;
  output({ credentialResolved: status.credentialResolved, projectMatched: status.projectMatched, initialized: true, reachable: true, metadataPrevented: status.metadataFallbackPrevented });
  console.log("FIREBASE_ADMIN_PREFLIGHT_PASSED");
} catch (error) {
  output({ credentialResolved, projectMatched, initialized, reachable: false, metadataPrevented: true });
  const code = typeof error === "object" && error !== null && "code" in error && typeof error.code === "string"
    ? error.code : "firebase_admin_preflight_failed";
  console.log(code.startsWith("firebase_admin_") ? code : initialized ? "firebase_auth_api_unreachable" : "firebase_admin_preflight_failed");
  process.exitCode = 1;
}
