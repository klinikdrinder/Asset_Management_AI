export async function register() {
  if (process.env.NEXT_RUNTIME !== "nodejs" || process.env.NEXT_PHASE === "phase-production-build") return;
  try {
    const credentials = await import("./app/lib/firebase/admin-credentials");
    const admin = await import("./app/lib/firebase/admin");
    const status = credentials.firebaseAdminCredentialPreflight();
    admin.getFirebaseAdminApp();
    const page = await admin.getFirebaseAdminAuth().listUsers(1);
    void page.users;
    console.info("firebase_admin_runtime_preflight", {
      credentialResolved: status.credentialResolved,
      projectMatched: status.projectMatched,
      firebaseAdminInitialized: true,
      firebaseAuthApiReachable: true,
      metadataFallbackPrevented: status.metadataFallbackPrevented,
    });
  } catch (error) {
    const code = typeof error === "object" && error !== null && "code" in error && typeof error.code === "string"
      ? error.code : "firebase_admin_runtime_preflight_failed";
    console.error("firebase_admin_runtime_preflight", { code: code.startsWith("firebase_admin_") ? code : "firebase_admin_runtime_preflight_failed" });
    throw new Error("firebase_admin_runtime_preflight_failed");
  }
}
